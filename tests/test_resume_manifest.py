"""Task-2 contract tests: manifest state machine + resume-from-last-good-stage.

Proves the six 00-04 Task-2 behaviors (CONTRACT-07 / XFN-03, Pitfall 9 / T-00-09):
  1. a fresh manifest has all stages pending
  2. marking a stage done records input_hash + output_hash + completed_at
  3. identical re-run inputs -> cache HIT (stage reusable, not re-run)
  4. changed upstream input_hash -> cache MISS -> stage + ALL downstream -> pending
  5. cache key is content-hash based, NOT file existence (a present file whose
     content hashes differently is a miss)
  6. an artifact failing schema re-validation -> cache miss even if hashes matched

The negative cases (4, 5, 6) are the RED-discriminating assertions: each proves the
resume logic genuinely catches a stale/changed/invalid artifact rather than blindly
trusting "the file is there".
"""

import json

from manifest.manifest import (
    DONE,
    PENDING,
    STAGE_ORDER,
    Manifest,
    content_hash,
)

# A tiny valid utci_grid artifact (mirrors the conftest master-lattice fixture)
# used for the schema-revalidation behavior (#6).
_VALID_UTCI = {
    "schema_version": "1.0.0",
    "crs": {"epsg": 32631, "units": "metre"},
    "lattice": {
        "origin_x_m": 0.0,
        "origin_y_m": 0.0,
        "cell_size_m": 10.0,
        "cols": 1,
        "rows": 1,
    },
    "cells": [{"x_m": 5.0, "y_m": 5.0, "utci_c": 34.0, "baseline_utci_c": 34.5}],
}


def _write_artifact(directory, name, obj):
    """Write obj to <directory>/<name> (creating the dir) and return (path, hash)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path, content_hash(obj)


# ── behavior 1: fresh manifest is all pending ────────────────────────────────


def test_fresh_manifest_all_pending(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    assert [m.status(s) for s in STAGE_ORDER] == [PENDING] * len(STAGE_ORDER)
    # No hashes recorded yet.
    for s in STAGE_ORDER:
        assert m.stage(s)["input_hash"] is None
        assert m.stage(s)["output_hash"] is None


# ── behavior 2: mark_done records the hashes + completed_at ───────────────────


def test_mark_done_records_hashes_and_timestamp(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    inputs = {"brief": "festival A"}
    in_hash = content_hash(inputs)
    path, out_hash = _write_artifact(tmp_path / "proj-1", "utci_grid.json", _VALID_UTCI)
    m.mark_done("utci_grid", "utci_grid.json", in_hash, out_hash)
    st = m.stage("utci_grid")
    assert st["status"] == DONE
    assert st["input_hash"] == in_hash
    assert st["output_hash"] == out_hash
    assert st["completed_at"] is not None


# ── behavior 3: identical inputs -> cache HIT ────────────────────────────────


def test_identical_inputs_cache_hit(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    proj = tmp_path / "proj-1"
    proj.mkdir(parents=True, exist_ok=True)
    inputs = {"date": "2026-07-01", "capacity": 50000}
    in_hash = content_hash(inputs)
    _, out_hash = _write_artifact(proj, "utci_grid.json", _VALID_UTCI)
    m.mark_done("utci_grid", "utci_grid.json", in_hash, out_hash)
    # Same inputs -> same hash -> reusable (and re-validates against the contract).
    assert m.is_reusable("utci_grid", content_hash(inputs), "utci_grid") is True


# ── behavior 4: changed input -> miss + downstream invalidation ──────────────


def test_changed_input_invalidates_stage_and_downstream(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    proj = tmp_path / "proj-1"
    proj.mkdir(parents=True, exist_ok=True)
    in_hash = content_hash({"capacity": 50000})
    _, out_hash = _write_artifact(proj, "utci_grid.json", _VALID_UTCI)
    m.mark_done("utci_grid", "utci_grid.json", in_hash, out_hash)
    # Mark a couple of downstream stages done too, to prove they get invalidated.
    m.mark_done("crowd_grid", "crowd_grid.json", "h1", "h2")
    m.mark_done("structure_zones", "structure_zones.json", "h3", "h4")

    # The brief changed -> utci_grid's current input hash differs -> cache MISS.
    changed_input = content_hash({"capacity": 80000})
    assert m.is_reusable("utci_grid", changed_input, "utci_grid") is False

    # The caller invalidates this stage and ALL downstream -> pending.
    invalidated = m.invalidate_from("utci_grid")
    # utci_grid is at index 1; everything from it onward is downstream.
    assert invalidated == list(STAGE_ORDER[STAGE_ORDER.index("utci_grid"):])
    assert "crowd_grid" in invalidated and "structure_zones" in invalidated
    assert "render" in invalidated  # the last stage is downstream too
    for s in invalidated:
        assert m.status(s) == PENDING
        assert m.stage(s)["output_hash"] is None
    # An UPSTREAM stage (parsed_brief) is NOT touched.
    assert "parsed_brief" not in invalidated


def test_resume_point_is_first_failing_stage(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    proj = tmp_path / "proj-1"
    proj.mkdir(parents=True, exist_ok=True)
    # parsed_brief is done + reusable; utci_grid's input changed -> resume there.
    pb_in = content_hash({"brief": "A"})
    _, pb_out = _write_artifact(proj, "parsed_brief.json", {"ok": True})
    m.mark_done("parsed_brief", "parsed_brief.json", pb_in, pb_out)
    _, utci_out = _write_artifact(proj, "utci_grid.json", _VALID_UTCI)
    m.mark_done("utci_grid", "utci_grid.json", content_hash({"d": 1}), utci_out)

    current = {
        "parsed_brief": pb_in,  # unchanged
        "utci_grid": content_hash({"d": 2}),  # CHANGED -> resume here
    }
    schemas = {"utci_grid": "utci_grid"}
    assert m.resume_point(current, schemas) == "utci_grid"


# ── behavior 5: content-hash based, NOT file existence ───────────────────────


def test_file_present_but_different_content_is_miss(tmp_path):
    """A file is on disk, status==done, input_hash matches — but the artifact's
    CONTENT differs from the recorded output_hash -> MISS. Proves the cache key is
    the content hash, never bare file existence (Pitfall D)."""
    m = Manifest("proj-1", project_root=tmp_path)
    proj = tmp_path / "proj-1"
    proj.mkdir(parents=True, exist_ok=True)
    in_hash = content_hash({"capacity": 50000})
    # Record an output_hash for ONE artifact...
    original = dict(_VALID_UTCI)
    _, out_hash = _write_artifact(proj, "utci_grid.json", original)
    m.mark_done("utci_grid", "utci_grid.json", in_hash, out_hash)
    # ...then overwrite the file on disk with DIFFERENT content (a present file).
    tampered = json.loads(json.dumps(original))
    tampered["cells"][0]["utci_c"] = 99.0  # changed value -> different content hash
    (proj / "utci_grid.json").write_text(json.dumps(tampered), encoding="utf-8")
    # The file exists, the input hash matches, status is done — yet it is a MISS
    # because the content no longer hashes to the recorded output_hash.
    assert m.is_reusable("utci_grid", in_hash, "utci_grid") is False


def test_missing_file_is_miss(tmp_path):
    """status==done + matching input_hash but NO file on disk -> miss."""
    m = Manifest("proj-1", project_root=tmp_path)
    in_hash = content_hash({"x": 1})
    m.mark_done("utci_grid", "utci_grid.json", in_hash, "deadbeef")
    # No file written -> not reusable (file existence still required, but is not
    # SUFFICIENT — see the content test above).
    assert m.is_reusable("utci_grid", in_hash, "utci_grid") is False


# ── behavior 6: schema-invalid cached artifact -> miss ───────────────────────


def test_schema_invalid_cached_artifact_is_miss(tmp_path):
    """The hashes line up (input + output) but the on-disk artifact no longer
    satisfies its contract -> MISS. Uses validate.py from Task 1 for the re-check."""
    m = Manifest("proj-1", project_root=tmp_path)
    proj = tmp_path / "proj-1"
    proj.mkdir(parents=True, exist_ok=True)
    # A malformed utci_grid: drop the required baseline_utci_c.
    malformed = json.loads(json.dumps(_VALID_UTCI))
    del malformed["cells"][0]["baseline_utci_c"]
    in_hash = content_hash({"capacity": 50000})
    # output_hash is computed over the malformed artifact, so hashes MATCH...
    _, out_hash = _write_artifact(proj, "utci_grid.json", malformed)
    m.mark_done("utci_grid", "utci_grid.json", in_hash, out_hash)
    # ...but schema re-validation fails -> cache miss.
    assert m.is_reusable("utci_grid", in_hash, "utci_grid") is False
    # Sanity: with NO schema check requested, the hash-only path would be a HIT,
    # which is exactly why the schema re-validation guard matters.
    assert m.is_reusable("utci_grid", in_hash, schema_name=None) is True


def test_manifest_write_round_trips(tmp_path):
    m = Manifest("proj-1", project_root=tmp_path)
    m.mark_done("parsed_brief", "parsed_brief.json", "i", "o")
    out = m.write()
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["project_id"] == "proj-1"
    assert [s["name"] for s in data["stages"]] == list(STAGE_ORDER)
    assert data["stages"][0]["status"] == DONE
