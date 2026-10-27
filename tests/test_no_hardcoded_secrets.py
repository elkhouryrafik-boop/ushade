"""No-hardcoded-secrets source-tree scan (XFN-02).

A hardcoded secret crossing into version control is the XFN-02 failure. This test
walks the repo and asserts that NO tracked text source file contains a recognizable
secret literal — Anthropic keys (``sk-ant-``), AWS access-key IDs (``AKIA...``), or
a named fal/infrared/AWS-secret assignment carrying a real long token. It is the
test-side complement to the repo ``cca-enforce`` hook (CCA-F P7); secrets must be
read via ``${ENV_VAR}`` (CLAUDE.md non-negotiable).

Design (00-RESEARCH A4 — pattern-based and fast):
  - walk with os.walk, pruning {.git, node_modules, .venv, __pycache__, .pytest_cache,
    *.egg-info} and the tests/fixtures tree (fixtures carry deliberate base64/URI
    strings that are not secrets).
  - skip the file ``.env`` (gitignored real secrets live there, never committed).
  - ``.env.example`` is allowed ONLY with empty values (NAME= with nothing after);
    a populated assignment there would be a real leak and IS flagged.
  - on any match, fail loudly listing every file:line so the offender is obvious.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories pruned entirely from the walk (vendored / generated / VCS internals).
_PRUNE_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}
# Directory NAME suffixes to prune (e.g. heatguard.egg-info).
_PRUNE_DIR_SUFFIXES = (".egg-info",)

# The tests/fixtures tree carries deliberate base64 (OUT_Mesh) + URI strings that are
# NOT secrets — exclude it so the scan stays focused on real source.
_FIXTURES_DIR = (_REPO_ROOT / "tests" / "fixtures").resolve()

# Files skipped by name:
#   .env — holds real (gitignored) secrets, never committed.
#   this scanner itself — it necessarily embeds the secret-shaped patterns it hunts
#     for (the regex literals + the planted-secret discrimination test below), which
#     are NOT real secrets. The discrimination test proves the scanner still fires on
#     a real planted token via a tmp_path file, so skipping its own source is safe.
_SKIP_FILES = {".env", "test_no_hardcoded_secrets.py"}

# Text source extensions worth scanning.
_TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".js",
    ".json",
    ".md",
    ".toml",
    ".example",
    ".yaml",
    ".yml",
    ".cfg",
    ".txt",
}

# --- Secret patterns ------------------------------------------------------
# Anthropic API key (the literal CLAUDE.md / cca-enforce shape).
_RE_ANTHROPIC = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")
# AWS access-key ID.
_RE_AKIA = re.compile(r"AKIA[0-9A-Z]{16}")
# A NAMED fal/infrared/AWS-secret assignment carrying a real long token. Keyed to the
# variable NAME so the contract URIs / base64 in source don't false-positive; the
# value must be a quoted >=20-char high-entropy-ish token (defeats bare strings like
# AWS_REGION=eu-west-1, which is short and unquoted).
_RE_NAMED_KEY = re.compile(
    r"(?:fal|infrared|aws)[_-]?(?:key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{20,}['\"]",
    re.IGNORECASE,
)

_SECRET_PATTERNS = [
    ("anthropic-key", _RE_ANTHROPIC),
    ("aws-access-key-id", _RE_AKIA),
    ("named-fal/infrared/aws-secret", _RE_NAMED_KEY),
]


def _iter_source_files():
    """Yield Path for every scannable text source file, pruning vendored dirs and
    the tests/fixtures tree."""
    for dirpath, dirnames, filenames in os.walk(_REPO_ROOT):
        # Prune in-place so os.walk doesn't descend into vendored/generated dirs.
        dirnames[:] = [
            d
            for d in dirnames
            if d not in _PRUNE_DIRS
            and not d.endswith(_PRUNE_DIR_SUFFIXES)
        ]
        current = Path(dirpath).resolve()
        # Skip the entire tests/fixtures subtree.
        if current == _FIXTURES_DIR or _FIXTURES_DIR in current.parents:
            continue
        for filename in filenames:
            if filename in _SKIP_FILES:
                continue
            path = Path(dirpath) / filename
            if path.suffix.lower() in _TEXT_SUFFIXES:
                yield path


def _scan_file(path: Path):
    """Return a list of (lineno, label, snippet) secret matches in one file."""
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for label, pattern in _SECRET_PATTERNS:
            if pattern.search(line):
                hits.append((lineno, label, line.strip()[:120]))
    return hits


def test_source_tree_has_no_hardcoded_secrets():
    """The committed source tree contains zero recognizable secret literals."""
    findings = []
    for path in _iter_source_files():
        for lineno, label, snippet in _scan_file(path):
            rel = path.relative_to(_REPO_ROOT)
            findings.append(f"{rel}:{lineno} [{label}] {snippet}")
    assert not findings, "Hardcoded secret(s) detected:\n" + "\n".join(findings)


def test_env_example_has_only_empty_values():
    """.env.example documents NAMES only — every assignment is empty or a non-secret
    default (AWS_REGION). No populated secret value may live there (it is committed)."""
    example = _REPO_ROOT / ".env.example"
    if not example.is_file():
        return  # nothing to check
    # The five secret-bearing names must be empty (NAME= with nothing after).
    secret_names = {
        "ANTHROPIC_API_KEY",
        "INFRARED_API_KEY",
        "FAL_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "MAPBOX_TOKEN",
    }
    for line in example.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, value = stripped.partition("=")
        if name.strip() in secret_names:
            assert value.strip() == "", (
                f".env.example populates a secret value for {name.strip()!r} — "
                "names only, never values"
            )


def test_scanner_would_catch_a_planted_secret(tmp_path):
    """Discrimination guard: the scanner MUST flag a planted sk-ant- / AKIA token —
    proves the green result above is a real pass, not a vacuous one."""
    planted = tmp_path / "leak.py"
    planted.write_text(
        'ANTHROPIC_API_KEY = "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA"\n'
        'aws_key = "AKIAABCDEFGHIJKLMNOP"\n',
        encoding="utf-8",
    )
    hits = _scan_file(planted)
    labels = {label for _, label, _ in hits}
    assert "anthropic-key" in labels
    assert "aws-access-key-id" in labels
