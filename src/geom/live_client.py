"""LIVE Rhino.Compute client — the GROUNDED solve path (GEOM-01, RHINO_LIVE opt-in).

This is the real-Rhino counterpart to ``reference_generator`` (PREVIEW). It implements the same
``.solve(gh_request) -> gh_response`` seam the Python spine (``geom.geom.run_gh_stage``) injects, but
instead of synthesising a PREVIEW mesh it POSTs the frozen ``gh_request`` to a running
Rhino.Compute server, evaluates a Grasshopper definition (``GH_DEFINITION_PATH``), and reassembles
the two contract outputs (``OUT_Mesh`` + ``OUT_BOM``) from the ``RH_OUT:*`` params.

Honesty: a response from THIS client is GROUNDED (a real Grasshopper solve), NOT PREVIEW — but the
Karamba pass inside the ``.gh`` remains "live-only pre-screening, requires engineering sign-off",
never "certified" (the geometry is real; the structural verdict is still not a stamped calc).

Wire contract (matches ``decode.py`` exactly):
  * inputs  — IN_Footprint  -> one closed ``PolylineCurve`` per polygon, metres, Z-up (XY plane);
              IN_FlowVectors -> one ``LineCurve`` per evac route;
              IN_SunVector   -> a single ``Vector3d``.
              Each rides a ``RH_IN:<name>`` DataTree, geometry serialized via ``rhino3dm .Encode()``.
  * outputs — RH_OUT:OUT_Mesh (a Rhino mesh, re-encoded to the project's ``base64(json(mesh.Encode())))``
              b64 that ``decode.py`` inverts), RH_OUT:OUT_Pillars (int), RH_OUT:OUT_Membrane_m2 (number).

``rhino3dm`` + ``compute_rhino3d`` are the optional ``geom`` extra — lazy-imported INSIDE ``solve``
(clone of ``reference_generator._load_geom_sdk``) so merely importing this module is dependency- and
network-free and the base pytest tier stays green.

Secrets (P7): ``RHINO_COMPUTE_KEY`` flows from the env straight into the compute lib's auth and is
NEVER assigned to a logged variable; on failure only the exception *type name* is surfaced — the raw
compute error (which can carry the URL / auth) is dropped (``from None``), mirroring the MJ-06 fix.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

_SCHEMA_VERSION = "1.0.0"
# Local Rhino.Compute default — the worker (compute.geometry.exe) Hops launches on :6500, no key.
_DEFAULT_COMPUTE_URL = "http://localhost:6500/"
_KARAMBA_PROVENANCE = "live-only, pre-screening, requires engineering sign-off"


class RhinoComputeError(Exception):
    """Typed live-solve failure.

    Named identically to the conftest ``FakeRhinoClient`` error and the Node ``client.ts`` seam so
    the spine's ``type(exc).__name__ == "RhinoComputeError"`` check propagates it UNWRAPPED (callers
    catch one stable type across all three solve seams).
    """


def _load_geom_sdk():
    """Lazily import ``rhino3dm`` + ``compute_rhino3d`` (the ``geom`` extra). Never at module top.

    Raises ``RhinoComputeError`` with an actionable install hint on ImportError so a missing extra
    surfaces as a typed live-solve failure (keeps the base offline suite dependency-free).
    """
    try:  # imported here, NEVER at module top
        import rhino3dm  # noqa: PLC0415
        import compute_rhino3d.Grasshopper as Grasshopper  # noqa: PLC0415
        import compute_rhino3d.Util as Util  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised via the typed-error path
        raise RhinoComputeError(
            "rhino3dm / compute_rhino3d not installed — `pip install -e \".[geom]\"`"
        ) from exc
    return rhino3dm, Util, Grasshopper


def _encode(geo) -> str:
    """Serialize a rhino3dm geometry to the compute ``data`` string (archive3dm JSON)."""
    return json.dumps(geo.Encode())


def _scalar(parsed: dict, name: str) -> str:
    """First data item of an ``RH_OUT:<name>`` branch, as a raw string. Raises if absent/empty."""
    items = parsed.get(name) or []
    if not items:
        raise RhinoComputeError(f"RH_OUT:{name} missing or empty in the compute response")
    return items[0]


def _as_number(raw) -> float:
    """Coerce a compute scalar ``data`` (which may be a JSON-encoded string) to a float."""
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(json.loads(raw))  # handles '2.0' and '"2.0"'
    except (ValueError, TypeError, json.JSONDecodeError):
        return float(raw)


class ComputeRhinoClient:
    """``.solve(gh_request) -> gh_response`` against a running Rhino.Compute server.

    Config is env-first (``${ENV_VAR}`` discipline) with constructor overrides for tests:
      * ``GH_DEFINITION_PATH`` — path to the ``.gh`` definition (REQUIRED for a live solve).
      * ``RHINO_COMPUTE_URL``  — compute base URL (default the local Hops worker ``:6500``).
      * ``RHINO_COMPUTE_KEY``  — optional API key (cloud / secured compute); never logged.
    """

    def __init__(
        self,
        gh_path: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.gh_path = gh_path or os.environ.get("GH_DEFINITION_PATH")
        self.url = url or os.environ.get("RHINO_COMPUTE_URL", _DEFAULT_COMPUTE_URL)
        # key read from env unless explicitly overridden; kept off any log path
        self._api_key = api_key if api_key is not None else os.environ.get("RHINO_COMPUTE_KEY")

    def solve(self, gh_request: dict) -> dict:
        """Evaluate the GH definition on the compute server and return a contract-valid gh_response.

        Raises ``RhinoComputeError`` on any missing config, transport failure, or malformed output —
        the spine maps this to a failed (NOT done) stage with no partial artifact.
        """
        rhino3dm, Util, Grasshopper = _load_geom_sdk()

        if not self.gh_path:
            raise RhinoComputeError("GH_DEFINITION_PATH not set (RHINO_LIVE path)")
        if not Path(self.gh_path).is_file():
            raise RhinoComputeError(f"GH definition not found: {self.gh_path}")

        Util.url = self.url if self.url.endswith("/") else self.url + "/"
        if self._api_key:
            Util.apiKey = self._api_key  # lib -> auth header; never assigned to a logged variable

        trees = self._build_trees(gh_request, rhino3dm, Grasshopper)
        try:
            response = Grasshopper.EvaluateDefinition(self.gh_path, trees)
        except Exception as exc:  # noqa: BLE001 - sanitize: raw error can carry url/auth (MJ-06 discipline)
            raise RhinoComputeError(
                f"rhino.compute solve failed ({type(exc).__name__})"
            ) from None
        return self._parse_response(response, rhino3dm)

    @staticmethod
    def _build_trees(gh_request: dict, rhino3dm, Grasshopper) -> list:
        """gh_request -> three ``RH_IN:*`` DataTrees of rhino3dm-encoded geometry (NO reshape).

        All footprint curves ride a SINGLE branch ``{0}`` (likewise flow lines) so a List-access
        consumer (the festcool Python component) solves ONCE over the whole list and emits ONE
        combined structure — NOT once per item. (Per-branch ``{i}`` made GH fan the solve out to
        85 separate runs, yielding 85 output branches the frozen contract can't read.)
        """
        fp_items = []
        for poly in gh_request["IN_Footprint"]:
            pl = rhino3dm.Polyline()
            for pt in poly:
                pl.Add(pt["x_m"], pt["y_m"], 0.0)
            pl.Add(poly[0]["x_m"], poly[0]["y_m"], 0.0)  # close the ring
            fp_items.append(_encode(rhino3dm.PolylineCurve(pl)))
        fp_tree = Grasshopper.DataTree("RH_IN:IN_Footprint")
        fp_tree.Append([0], fp_items)

        fv_items = []
        for line in gh_request["IN_FlowVectors"]:
            o, d = line["origin"], line["destination"]
            lc = rhino3dm.LineCurve(
                rhino3dm.Point3d(o["x_m"], o["y_m"], 0.0),
                rhino3dm.Point3d(d["x_m"], d["y_m"], 0.0),
            )
            fv_items.append(_encode(lc))
        fv_tree = Grasshopper.DataTree("RH_IN:IN_FlowVectors")
        fv_tree.Append([0], fv_items)

        sun_tree = Grasshopper.DataTree("RH_IN:IN_SunVector")
        sx, sy, sz = gh_request["IN_SunVector"]
        sun_tree.Append([0], [_encode(rhino3dm.Vector3d(sx, sy, sz))])

        return [fp_tree, fv_tree, sun_tree]

    @staticmethod
    def _parse_response(response: dict, rhino3dm) -> dict:
        """compute ``values`` -> frozen gh_response; validate on the way out (defence-in-depth)."""
        if not isinstance(response, dict) or "values" not in response:
            raise RhinoComputeError("compute response carried no 'values' (definition / RH_OUT wiring?)")

        # Flatten every RH_OUT param to {logical_name: [data, ...]} (strip the RH_OUT: prefix).
        parsed: dict[str, list] = {}
        for val in response["values"]:
            name = str(val.get("ParamName", "")).split(":")[-1]
            items: list = []
            for branch in (val.get("InnerTree") or {}).values():
                for entry in branch:
                    items.append(entry.get("data"))
            parsed[name] = items

        mesh_raw = _scalar(parsed, "OUT_Mesh")
        mesh_dict = json.loads(mesh_raw) if isinstance(mesh_raw, str) else mesh_raw
        mesh = rhino3dm.CommonObject.Decode(mesh_dict)
        if mesh is None or type(mesh).__name__ != "Mesh":
            raise RhinoComputeError("RH_OUT:OUT_Mesh did not decode to a Rhino Mesh")
        # Re-encode to the project's b64 contract (the exact inverse decode.py expects).
        b64 = base64.b64encode(json.dumps(mesh.Encode()).encode("utf-8")).decode("ascii")

        gh_response = {
            "schema_version": _SCHEMA_VERSION,
            "OUT_Mesh": {"b64": b64},
            "OUT_BOM": {
                "pillars": int(round(_as_number(_scalar(parsed, "OUT_Pillars")))),
                "membrane_m2": _as_number(_scalar(parsed, "OUT_Membrane_m2")),
            },
        }
        # Validate-on-receipt (the spine validates too; this is defence-in-depth at the seam — MN-05).
        from validate.validate import validate  # noqa: PLC0415 (deferred — keep import-time light)

        validate(gh_response, "gh_response")
        return gh_response
