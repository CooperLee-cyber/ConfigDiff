"""Line and character level comparison without any UI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff


@dataclass(frozen=True)
class DiffRow:
    kind: str
    text: str
    old_number: int | None = None
    new_number: int | None = None
    changed_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class DiffResult:
    rows: tuple[DiffRow, ...]
    additions: int
    deletions: int
    modifications: int
    change_positions: tuple[int, ...]
    unified_text: str

    @property
    def identical(self) -> bool:
        return self.additions == self.deletions == self.modifications == 0

    @property
    def display_text(self) -> str:
        prefix = {
            "equal": "  ",
            "added": "+ ",
            "deleted": "- ",
            "modified_old": "- ",
            "modified_new": "+ ",
            "eof": "~ ",
        }
        return "\n".join(prefix[row.kind] + row.text for row in self.rows)


def _lines(text: str) -> tuple[list[str], bool]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized:
        return [], False
    has_final_newline = normalized.endswith("\n")
    parts = normalized.split("\n")
    if has_final_newline:
        parts.pop()
    return parts, has_final_newline


def _changed_spans(before: str, after: str) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
    old_spans: list[tuple[int, int]] = []
    new_spans: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag != "equal":
            if i1 != i2:
                old_spans.append((i1, i2))
            if j1 != j2:
                new_spans.append((j1, j2))
    return tuple(old_spans), tuple(new_spans)


def _similarity(before: str, after: str) -> float:
    if not before and not after:
        return 1.0
    # Lines are usually short configuration statements. This bound prevents a
    # very long log record from dominating comparison time.
    return SequenceMatcher(None, before[:500], after[:500], autojunk=False).ratio()


def _align_replacement(old: list[str], new: list[str]) -> list[tuple[str, int | None, int | None]]:
    """Keep similar modified lines paired while preserving order."""
    m, n = len(old), len(new)
    if not m:
        return [("add", None, j) for j in range(n)]
    if not n:
        return [("delete", i, None) for i in range(m)]

    # Exact dynamic programming is useful for modest replacement blocks.
    # A bounded lookahead keeps large, fully replaced files responsive.
    if m * n > 5000:
        operations: list[tuple[str, int | None, int | None]] = []
        i = j = 0
        while i < m and j < n:
            best = (0.52, -1, -1)
            for di in range(min(5, m - i)):
                for dj in range(min(5, n - j)):
                    score = _similarity(old[i + di], new[j + dj]) - 0.04 * (di + dj)
                    if score > best[0]:
                        best = (score, di, dj)
            if best[1] < 0:
                operations.append(("delete", i, None))
                i += 1
            else:
                _, di, dj = best
                for k in range(di):
                    operations.append(("delete", i + k, None))
                for k in range(dj):
                    operations.append(("add", None, j + k))
                i += di
                j += dj
                operations.append(("modify", i, j))
                i += 1
                j += 1
        operations.extend(("delete", k, None) for k in range(i, m))
        operations.extend(("add", None, k) for k in range(j, n))
        return operations

    scores = [[0.0] * (n + 1) for _ in range(m + 1)]
    choices = [[""] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n - 1, -1, -1):
            score = _similarity(old[i], new[j])
            match = (score - 0.52) + scores[i + 1][j + 1] if score >= 0.52 else float("-inf")
            delete = scores[i + 1][j]
            add = scores[i][j + 1]
            if match > max(delete, add) + 1e-8:
                scores[i][j] = match
                choices[i][j] = "modify"
            elif delete >= add:
                scores[i][j] = delete
                choices[i][j] = "delete"
            else:
                scores[i][j] = add
                choices[i][j] = "add"
    operations = []
    i = j = 0
    while i < m and j < n:
        choice = choices[i][j]
        if choice == "modify":
            operations.append(("modify", i, j))
            i += 1
            j += 1
        elif choice == "delete":
            operations.append(("delete", i, None))
            i += 1
        else:
            operations.append(("add", None, j))
            j += 1
    operations.extend(("delete", k, None) for k in range(i, m))
    operations.extend(("add", None, k) for k in range(j, n))
    return operations


def compare_text(old_text: str, new_text: str) -> DiffResult:
    old, old_final = _lines(old_text)
    new, new_final = _lines(new_text)
    rows: list[DiffRow] = []
    added = deleted = modified = 0

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=True).get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                rows.append(DiffRow("equal", old[i], i + 1, j + 1))
        elif tag == "insert":
            for j in range(j1, j2):
                rows.append(DiffRow("added", new[j], new_number=j + 1))
                added += 1
        elif tag == "delete":
            for i in range(i1, i2):
                rows.append(DiffRow("deleted", old[i], old_number=i + 1))
                deleted += 1
        else:
            for operation, oi, nj in _align_replacement(old[i1:i2], new[j1:j2]):
                if operation == "modify":
                    i, j = i1 + oi, j1 + nj
                    old_spans, new_spans = _changed_spans(old[i], new[j])
                    rows.append(DiffRow("modified_old", old[i], old_number=i + 1, changed_spans=old_spans))
                    rows.append(DiffRow("modified_new", new[j], new_number=j + 1, changed_spans=new_spans))
                    modified += 1
                elif operation == "delete":
                    i = i1 + oi
                    rows.append(DiffRow("deleted", old[i], old_number=i + 1))
                    deleted += 1
                else:
                    j = j1 + nj
                    rows.append(DiffRow("added", new[j], new_number=j + 1))
                    added += 1

    if old_final != new_final and (old or new):
        message = "文件末尾换行：" + ("原配置有，新配置无" if old_final else "原配置无，新配置有")
        rows.append(DiffRow("eof", message))
        modified += 1

    change_positions: list[int] = []
    previous_changed = False
    for index, row in enumerate(rows):
        changed = row.kind != "equal"
        if changed and not previous_changed:
            change_positions.append(index)
        previous_changed = changed

    old_unified = old_text.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    new_unified = new_text.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    unified_parts = []
    for line in unified_diff(old_unified, new_unified, fromfile="原配置", tofile="新配置"):
        unified_parts.append(line)
        if not line.endswith("\n"):
            unified_parts.append("\n\\ No newline at end of file\n")
    unified = "".join(unified_parts)
    return DiffResult(tuple(rows), added, deleted, modified, tuple(change_positions), unified)
