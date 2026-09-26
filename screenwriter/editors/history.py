"""Text-only undo history.

The screenplay editor restyles lines as you type (indents depend on the cursor
line, on Tab, on the line below). If Qt's own undo stack recorded those format
changes, undo/redo would replay stale formatting. Instead Qt's undo is off and
this history records only changes to the plain text; formatting is recomputed
from the text after every undo/redo.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Edit:
    pos: int
    removed: str
    added: str


@dataclass
class Step:
    cursor_before: int
    cursor_after: int
    edits: list[Edit] = field(default_factory=list)

    @property
    def typing(self) -> str | None:
        """'insert' / 'delete' for a single-character-ish edit that can merge with its neighbour."""
        if len(self.edits) != 1:
            return None
        e = self.edits[0]
        if e.added and not e.removed and "\n" not in e.added:
            return "insert"
        if e.removed and not e.added and "\n" not in e.removed:
            return "delete"
        return None


def diff(old: str, new: str, hint: tuple[int, int, int] | None = None) -> Edit | None:
    """The single contiguous edit that turns old into new."""
    if old == new:
        return None
    if hint:
        pos, removed, added = hint
        if old[:pos] + new[pos : pos + added] + old[pos + removed :] == new:
            return Edit(pos, old[pos : pos + removed], new[pos : pos + added])
    # Fallback: common prefix / suffix, found with C-speed slice comparisons.
    lo, hi = 0, min(len(old), len(new))
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if old[:mid] == new[:mid]:
            lo = mid
        else:
            hi = mid - 1
    prefix = lo
    lo, hi = 0, min(len(old), len(new)) - prefix
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if old[len(old) - mid :] == new[len(new) - mid :]:
            lo = mid
        else:
            hi = mid - 1
    suffix = lo
    return Edit(prefix, old[prefix : len(old) - suffix], new[prefix : len(new) - suffix])


class TextHistory:
    LIMIT = 2000

    def __init__(self, text: str = ""):
        self.reset(text)

    def reset(self, text: str) -> None:
        self.text = text
        self.undo_stack: list[Step] = []
        self.redo_stack: list[Step] = []
        self._group: Step | None = None
        self._depth = 0

    # --- recording --------------------------------------------------------------

    def begin(self, cursor: int) -> None:
        """Group every edit until the matching end() into one undo step."""
        if self._depth == 0:
            self._group = Step(cursor, cursor)
        self._depth += 1

    def end(self, cursor: int) -> None:
        self._depth -= 1
        if self._depth == 0:
            group, self._group = self._group, None
            if group.edits:
                group.cursor_after = cursor
                self._push(group)

    def record(self, new_text: str, cursor: int, hint: tuple[int, int, int] | None = None) -> None:
        edit = diff(self.text, new_text, hint)
        self.text = new_text
        if edit is None:
            return
        if self._group is not None:
            self._group.edits.append(edit)
        else:
            self._push(Step(edit.pos, cursor, [edit]))

    def _push(self, step: Step) -> None:
        self.redo_stack.clear()
        if self.undo_stack and self._merge(self.undo_stack[-1], step):
            return
        self.undo_stack.append(step)
        del self.undo_stack[: -self.LIMIT]

    @staticmethod
    def _merge(last: Step, step: Step) -> bool:
        """Typing merges into word-sized undo steps; so does holding Backspace."""
        kind = step.typing
        if kind is None or kind != last.typing:
            return False
        a, b = last.edits[0], step.edits[0]
        if kind == "insert":
            if a.pos + len(a.added) != b.pos:
                return False
            if a.added[-1].isspace() and not b.added[0].isspace():
                return False  # a new word starts a new step
            a.added += b.added
        else:
            if b.pos + len(b.removed) == a.pos:  # backspace
                a.pos, a.removed = b.pos, b.removed + a.removed
            elif b.pos == a.pos:  # forward delete
                a.removed += b.removed
            else:
                return False
        last.cursor_after = step.cursor_after
        return True

    # --- replay -------------------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def pop_undo(self) -> Step | None:
        if not self.undo_stack:
            return None
        step = self.undo_stack.pop()
        self.redo_stack.append(step)
        return step

    def pop_redo(self) -> Step | None:
        if not self.redo_stack:
            return None
        step = self.redo_stack.pop()
        self.undo_stack.append(step)
        return step
