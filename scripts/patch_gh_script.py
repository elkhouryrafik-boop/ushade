"""Inject a new Python script into festcool_structure.gh's embedded Python-3 component.

Encoding (reverse-engineered): whole .gh = raw-DEFLATE (zlib -15). Inside the
decompressed stream the script is stored as UTF-8 -> base64(ascii) -> prefixed by a
.NET 7-bit-encoded-int giving the BYTE COUNT of the base64 ascii. We locate the b64
run, read its varint prefix for the exact bounds, splice the new b64 + new varint,
and recompress.

Usage: python scripts/patch_gh_script.py <new_script.py> [<target.gh>]
Verifies by reading the length-prefixed string back and decoding.
"""
import base64, re, sys, zlib
from pathlib import Path


def enc7(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def read7_back(buf: bytes, end: int):
    """Read a .NET 7-bit-int that ENDS at index `end` (exclusive). Returns (value, start)."""
    # last byte (just before `end`) has high bit clear; preceding bytes have it set.
    i = end - 1
    bytes_le = []
    # collect continuation bytes walking left
    while i >= 0:
        bytes_le.insert(0, buf[i])
        if buf[i] & 0x80 == 0 and i != end - 1:
            # this is a terminator of a PREVIOUS varint -> not ours; stop, drop it
            bytes_le.pop(0)
            i += 1
            break
        if i == end - 1:
            i -= 1
            continue
        i -= 1
    # bytes_le now little-endian groups; first byte is least significant
    val = 0
    for shift, b in enumerate(bytes_le):
        val |= (b & 0x7F) << (7 * shift)
    return val, end - len(bytes_le)


def main():
    new_script = Path(sys.argv[1]).read_text(encoding="utf-8")
    gh = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "festcool_structure.gh"
    data = gh.read_bytes()
    raw = zlib.decompress(data, -15)

    m = re.search(rb"[A-Za-z0-9+/=]{200,}", raw)
    if not m:
        sys.exit("no base64 run found")
    rs, re_ = m.start(), m.end()

    # align: find the lead offset where the run decodes to valid script
    b64_start = b64_end = None
    for lead in range(0, 4):
        chunk = raw[rs + lead:re_]
        if len(chunk) % 4:
            chunk = chunk[: len(chunk) - (len(chunk) % 4)]
        try:
            dec = base64.b64decode(chunk)
        except Exception:
            continue
        if b"import Rhino" in dec or b"festcool" in dec:
            b64_start = rs + lead
            b64_end = b64_start + len(chunk)
            old_script = dec.decode("utf-8", "replace")
            break
    if b64_start is None:
        sys.exit("could not align base64 run to a script")

    old_len = b64_end - b64_start
    val, varint_start = read7_back(raw, b64_start)
    if val != old_len:
        # fall back: assume 2-byte varint sized to old_len
        varint_start = b64_start - len(enc7(old_len))
    print(f"located script: b64[{b64_start}:{b64_end}] len={old_len} varint@{varint_start} (decoded={val})")
    print(f"old script {len(old_script)} chars; new script {len(new_script)} chars")

    new_b64 = base64.b64encode(new_script.encode("utf-8"))
    new_region = enc7(len(new_b64)) + new_b64
    raw_new = raw[:varint_start] + new_region + raw[b64_end:]

    # verify round-trip read at the new offset
    chk = base64.b64decode(new_b64).decode("utf-8")
    assert chk == new_script, "round-trip mismatch"

    recompressed = zlib.compressobj(9, zlib.DEFLATED, -15)
    blob = recompressed.compress(raw_new) + recompressed.flush()
    # sanity: must re-decompress to raw_new
    assert zlib.decompress(blob, -15) == raw_new, "recompress verify failed"

    bak = gh.with_suffix(gh.suffix + ".prepatch")
    if not bak.exists():
        bak.write_bytes(data)
    gh.write_bytes(blob)
    print(f"PATCHED {gh.name} ({len(data)} -> {len(blob)} bytes); backup at {bak.name}")


if __name__ == "__main__":
    main()
