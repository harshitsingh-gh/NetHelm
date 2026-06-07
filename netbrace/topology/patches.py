"""Apply a unified diff to a device config. Strict, deterministic, total.

We use unified diffs because they are the natural representation of a config
change and are exactly what we show the model. The oracle applies the SAME patch
to produce the post-change snapshot, so generation and grading can never drift.

This is intentionally a small, strict applier (not `patch(1)`):
  * context and removed lines must match the source EXACTLY (no fuzz);
  * a mismatch raises PatchError rather than silently producing wrong configs —
    a wrong post-config would corrupt ground truth, so we fail loud.

Only single-file hunks are needed (one device config per patch). The '---'/'+++'
header lines are optional and ignored if present.
"""

from __future__ import annotations


class PatchError(ValueError):
    """Raised when a patch does not apply cleanly to the given source."""


def apply_unified_diff(source: str, patch: str) -> str:
    """Return ``source`` with ``patch`` applied. Raise PatchError on any mismatch."""
    src_lines = source.splitlines()
    patch_lines = patch.splitlines()

    # Skip optional file headers.
    i = 0
    while i < len(patch_lines) and (
        patch_lines[i].startswith("--- ") or patch_lines[i].startswith("+++ ")
    ):
        i += 1

    result: list[str] = []
    src_pos = 0  # index into src_lines already consumed into result

    while i < len(patch_lines):
        line = patch_lines[i]
        if not line.startswith("@@"):
            raise PatchError(f"expected hunk header, got: {line!r}")
        start_old = _parse_hunk_old_start(line)  # 1-based
        hunk_src_idx = start_old - 1
        if hunk_src_idx < 0 or hunk_src_idx > len(src_lines):
            raise PatchError(f"hunk start {start_old} out of range")

        # Emit unchanged source up to the hunk start.
        if hunk_src_idx < src_pos:
            raise PatchError("overlapping or out-of-order hunks")
        result.extend(src_lines[src_pos:hunk_src_idx])
        src_pos = hunk_src_idx

        i += 1
        while i < len(patch_lines) and not patch_lines[i].startswith("@@"):
            pl = patch_lines[i]
            if pl == "":
                tag, content = " ", ""          # bare empty line == context
            else:
                tag, content = pl[0], pl[1:]

            if tag == " ":                       # context: must match, keep
                _expect(src_lines, src_pos, content)
                result.append(src_lines[src_pos])
                src_pos += 1
            elif tag == "-":                     # removal: must match, drop
                _expect(src_lines, src_pos, content)
                src_pos += 1
            elif tag == "+":                     # addition: insert
                result.append(content)
            elif tag == "\\":                    # "\ No newline at end of file"
                pass
            else:
                raise PatchError(f"unexpected patch line: {pl!r}")
            i += 1

    # Emit the remainder of the source.
    result.extend(src_lines[src_pos:])

    text = "\n".join(result)
    if source.endswith("\n"):
        text += "\n"
    return text


def _expect(src_lines: list[str], pos: int, content: str) -> None:
    if pos >= len(src_lines):
        raise PatchError(f"patch expected {content!r} past end of source")
    if src_lines[pos] != content:
        raise PatchError(
            f"context mismatch at source line {pos + 1}: "
            f"expected {content!r}, found {src_lines[pos]!r}"
        )


def _parse_hunk_old_start(header: str) -> int:
    """Parse '@@ -<old_start>[,<len>] +<new_start>[,<len>] @@' -> old_start (int)."""
    try:
        minus = header.split("-", 1)[1]
        old_part = minus.split(" ", 1)[0]
        return int(old_part.split(",", 1)[0])
    except (IndexError, ValueError) as e:
        raise PatchError(f"malformed hunk header: {header!r}") from e
