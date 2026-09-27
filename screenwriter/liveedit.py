"""The window side of live editing (see live.py).

Every second: say which document this window shows; if someone else is on the same one,
share it as a CRDT — join the live session they're in (or start one), turn every change
typed here into CRDT operations as it happens, apply the others' operations to the editor
where they happened, and mark where the others are.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor, QTextCursor, QTextFormat
from PySide6.QtWidgets import QLabel, QTextEdit

from . import people
from .editors.prose import ProseEditor
from .editors.screenplay import ScreenplayEditor
from .live import Channel, LiveState, byte_offset, char_index, find_line, new_doc, new_gen, qt_position
from .merge import TOKEN_RE
from .sync import _is_ancestor

HEARTBEAT = 5  # ticks between re-publishing an unchanged state, so it stays fresh
TIDY_EVERY = 300  # ticks between tidying old files


def live_editor(editor) -> bool:
    return isinstance(editor, (ProseEditor, ScreenplayEditor))


def char_edits(old: str, new: str) -> list[tuple[int, int, str]]:
    """(start, end, replacement) in `old`, in order, turning it into `new`: lines are matched
    first (fast), then the words inside lines that changed — whole words, so one person's
    word is never respelled into another's."""
    a, b = old.splitlines(keepends=True), new.splitlines(keepends=True)
    offsets = [0]
    for line in a:
        offsets.append(offsets[-1] + len(line))
    edits = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        old_words = TOKEN_RE.findall(old[offsets[i1]:offsets[i2]])
        new_words = TOKEN_RE.findall("".join(b[j1:j2]))
        starts = [offsets[i1]]
        for w in old_words:
            starts.append(starts[-1] + len(w))
        for wtag, w1, w2, v1, v2 in SequenceMatcher(None, old_words, new_words, autojunk=False).get_opcodes():
            if wtag != "equal":
                edits.append((starts[w1], starts[w2], "".join(new_words[v1:v2])))
    return edits


def _tokens(text: str) -> tuple[list[str], list[int]]:
    words = TOKEN_RE.findall(text)
    starts = [0]
    for w in words:
        starts.append(starts[-1] + len(w))
    return words, starts


def rebase(head: str, mine: str, shared: str) -> list[tuple[int, int, str]]:
    """My edits since `head`, replayed onto `shared`, as (start, end, replacement) in `shared`,
    in order. What I added goes in where it belongs; what I deleted goes only where it is still
    untouched in `shared` — so nothing anyone else wrote is ever removed, and nothing I wrote
    is lost."""
    h_words, h_at = _tokens(head)
    s_words, s_at = _tokens(shared)
    blocks = [(tag, h_at[i1], h_at[i2], s_at[j1], s_at[j2])
              for tag, i1, i2, j1, j2 in SequenceMatcher(None, h_words, s_words, autojunk=False).get_opcodes()]

    def place(pos: int) -> tuple[int, str]:
        """Where a head position is in `shared`, and what they wrote there instead, if anything."""
        for tag, h0, h1, s0, s1 in blocks:  # something of theirs right here comes first
            if tag != "equal" and h0 <= pos <= h1:
                return s1, shared[s0:s1]
        for tag, h0, h1, s0, s1 in blocks:
            if h0 <= pos <= h1:
                return s0 + (pos - h0), ""
        return len(shared), ""

    edits = []
    for start, end, text in char_edits(head, mine):
        for tag, h0, h1, s0, s1 in blocks:  # delete only what's the same on both sides
            lo, hi = max(start, h0), min(end, h1)
            if tag == "equal" and lo < hi:
                edits.append((s0 + lo - h0, s0 + hi - h0, ""))
        at, theirs = place(start)
        already = text.strip() and text.strip() in theirs  # it reached them another way: once is enough
        if text and not already:
            edits.append((at, at, text))
    return sorted(edits, key=lambda e: (e[0], e[1] > e[0]))


class LiveSession:
    """One document, shared live as a CRDT while others are on it too."""

    def __init__(self, editor, doc_id: str, gen: str, base_text: str):
        self.editor = editor
        self.doc_id = doc_id
        self.gen = gen
        self.doc, self.text = new_doc(base_text)
        self.dirty = True
        self._local = False  # applying our own edit to the CRDT
        self._remote = False  # applying theirs to the editor
        self._started = False  # the editor shows the shared text (until then, theirs only goes into the CRDT)
        self._last = ""
        self._subscription = self.text.observe(self._on_crdt_change)

    # --- getting in step ---------------------------------------------------------------------

    def start(self, head_text: str) -> None:
        """After the others' states are in: bring in what we wrote before joining, then show
        the shared text."""
        shared = str(self.text)
        mine = self.editor.text()
        if mine != shared:
            self._edit_crdt(shared, rebase(head_text, mine, shared))
        self._last = self.editor.text()
        if self._last != str(self.text):
            self._show(str(self.text))
        self._started = True
        self.editor.textChanged.connect(self._on_typed)

    def _edit_crdt(self, old: str, edits: list[tuple[int, int, str]]) -> None:
        """Apply (start, end, replacement) edits of `old` (the CRDT's text) as our own, touching
        only what they name — replacing whole lines would throw the others' cursors out of them."""
        self._local = True
        try:
            with self.doc.transaction():
                for start, end, text in reversed(edits):
                    b0, b1 = byte_offset(old, start), byte_offset(old, end)
                    if b1 > b0:
                        del self.text[b0:b1]
                    if text:
                        self.text.insert(b0, text)
        finally:
            self._local = False
        self.dirty = True

    def _show(self, text: str) -> None:
        self._remote = True
        try:
            self.editor.apply_remote_text(text)
        finally:
            self._remote = False
        self._last = self.editor.text()

    # --- our typing ---------------------------------------------------------------------------------

    def _on_typed(self) -> None:
        if self._remote:
            return
        new = self.editor.text()
        old = self._last
        if new == old:
            return  # only formatting changed
        start = 0
        limit = min(len(old), len(new))
        while start < limit and old[start] == new[start]:
            start += 1
        end = 0
        while end < limit - start and old[len(old) - 1 - end] == new[len(new) - 1 - end]:
            end += 1
        b0, b1 = byte_offset(old, start), byte_offset(old, len(old) - end)
        inserted = new[start:len(new) - end]
        self._local = True
        try:
            with self.doc.transaction():
                if b1 > b0:
                    del self.text[b0:b1]
                if inserted:
                    self.text.insert(b0, inserted)
        finally:
            self._local = False
        self._last = new
        self.dirty = True

    # --- their typing -------------------------------------------------------------------------------------

    def merge_in(self, updates: list[bytes]) -> None:
        for update in updates:
            self.doc.apply_update(update)

    def _on_crdt_change(self, event) -> None:
        if self._local or not self._started:
            return
        editor = self.editor
        current = editor.text()
        cursor = QTextCursor(editor.document())
        screenplay = isinstance(editor, ScreenplayEditor)
        mine = editor.textCursor()
        # Where my cursor belongs afterwards (Qt would push it past text inserted right at it;
        # it stays with my own typing instead). Set once the edit is done: moving the cursor in
        # the middle of an edit block isn't allowed.
        my_pos = None if mine.hasSelection() else mine.position()
        self._remote = True
        if screenplay:
            editor._replaying = True  # not steps of our own to undo
        try:
            cursor.beginEditBlock()
            at = 0  # UTF-8 offset in `current`, as the delta walks through it
            for op in event.delta:
                if "retain" in op:
                    at += op["retain"]
                elif "insert" in op:
                    s = op["insert"] if isinstance(op["insert"], str) else ""
                    i = char_index(current, at)
                    q = qt_position(current, i)
                    cursor.setPosition(q)
                    cursor.insertText(s)
                    if my_pos is not None and q < my_pos:
                        my_pos += len(s.encode("utf-16-le")) // 2
                    current = current[:i] + s + current[i:]
                    at += len(s.encode("utf-8"))
                elif "delete" in op:
                    i, j = char_index(current, at), char_index(current, at + op["delete"])
                    a, b = qt_position(current, i), qt_position(current, j)
                    cursor.setPosition(a)
                    cursor.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                    cursor.removeSelectedText()
                    if my_pos is not None:
                        my_pos = my_pos - (b - a) if my_pos >= b else min(my_pos, a) if my_pos > a else my_pos
                    current = current[:i] + current[j:]
            cursor.endEditBlock()
        finally:
            if screenplay:
                editor._replaying = False
            self._remote = False
        if my_pos is not None and editor.textCursor().position() != my_pos:
            mine = editor.textCursor()
            mine.setPosition(min(my_pos, editor.document().characterCount() - 1))
            editor.setTextCursor(mine)
        if screenplay:
            editor.history.reset(editor.text())
            editor._full_refresh()
        else:
            editor.document().clearUndoRedoStacks()
        self._last = editor.text()
        if self._last != str(self.text):  # shouldn't happen; if it does, show the shared text
            self._show(str(self.text))

    def stop(self) -> None:
        try:
            self.editor.textChanged.disconnect(self._on_typed)
        except (RuntimeError, TypeError):
            pass
        try:
            self.text.unobserve(self._subscription)
        except Exception:  # the CRDT is going away anyway
            pass


class LiveEditing(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.enabled = True
        self.timer = QTimer(self, interval=1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.session: LiveSession | None = None
        self._channel: Channel | None = None
        self._published: tuple | None = None
        self._since_publish = 0
        self._ticks = 0
        self._markers: dict[int, dict[str, tuple[int, QLabel, str]]] = {}  # editor id -> session -> (line, label, colour)
        self._hooked: set[int] = set()
        self._fetched: set[str] = set()  # sessions we've synced for, to get the version they grew from

    # --- where live editing applies ---------------------------------------------------------------

    def _package(self):
        w = self.window
        target = w.sync_target
        package = getattr(target, "package", None)  # a shared folder (not Google Drive)
        if not self.enabled or not w.project or package is None or not target.available():
            return None
        return package

    def active(self) -> bool:
        return self._package() is not None and bool(self.window.others)

    def is_live(self, doc_id: str) -> bool:
        return self.session is not None and self.session.doc_id == doc_id

    # --- the tick ------------------------------------------------------------------------------------

    def tick(self) -> None:
        package = self._package()
        if package is None:
            self.leave()
            return
        if self._channel is None or self._channel.package != package:
            self._channel = Channel(package)
        channel = self._channel
        w = self.window
        self._ticks += 1
        if self._ticks % TIDY_EVERY == 0:
            channel.tidy()

        editor = w.tabs.currentWidget()
        node = w.project.find(editor.node_id) if live_editor(editor) else None
        peers = [s for s in channel.states(w.session) if node is not None and s.doc_id == node.id]
        if self.session and (node is None or self.session.editor is not editor or not peers):
            self._stop_session()
        if peers:
            gens = sorted({s.gen for s in peers if s.gen} | ({self.session.gen} if self.session else set()))
            if self.session and gens and gens[0] != self.session.gen:
                self._stop_session()  # two sessions started at once: everyone moves to the older one
            if self.session is None:
                self._join(channel, editor, node, gens[0] if gens else None)
        if self.session:
            self.session.merge_in(channel.changed_states(w.session, self.session.gen))
            if self.session.dirty:
                channel.write_state(w.session, self.session.gen, self.session.doc.get_update())
                self.session.dirty = False
        self._publish(channel, editor, node)
        self._show_cursors(editor if self.session else None, peers)

    def _head_text(self, node) -> str:
        w = self.window
        head = w.history.head()
        data = w.history.file_at(head, f"docs/{w.project.doc_path(node).name}") if head else None
        return data.decode("utf-8", "replace").replace("\r\n", "\n") if data else ""

    def _has_version(self, origin: str) -> bool:
        """Whether our history holds that saved version (so our text grew from it too)."""
        repo, head = self.window.history.repo, self.window.history.head()
        try:
            return head is not None and _is_ancestor(repo, origin.encode(), head)
        except KeyError:
            return False

    def _join(self, channel: Channel, editor, node, gen: str | None) -> None:
        w = self.window
        if gen is None:  # nobody's in a session of this document yet: start one
            w.sync_now(quiet=True)  # so the version it grows from is on the shared folder for them
            gen = new_gen()
            head = w.history.head()
            channel.create_base(gen, node.id, editor.text(), head.decode() if head else "", self._head_text(node))
        info = channel.base(gen)
        if info is None:
            return  # their starting text hasn't reached this computer yet; next time
        origin = info.get("origin", "")
        if origin and not self._has_version(origin):
            if gen not in self._fetched:  # the version their text grew from: get it first
                self._fetched.add(gen)
                w.sync_now(quiet=True)
            if not self._has_version(origin):
                return  # not synced to the shared folder yet; try again shortly
        session = LiveSession(editor, node.id, gen, info["text"])
        channel.forget(gen)
        session.merge_in(channel.changed_states(w.session, gen))
        # what we have that the session doesn't: everything since the version it grew from
        session.start(info.get("origin_text", "") if origin else self._head_text(node))
        self.session = session

    def _stop_session(self) -> None:
        if self.session:
            self.session.stop()
            self.session = None

    def _publish(self, channel: Channel, editor, node) -> None:
        w = self.window
        if node is None:
            key = None
        else:
            block = editor.textCursor().block()
            key = (node.id, self.session.gen if self.session else "", block.blockNumber(), block.text())
        self._since_publish += 1
        if key == self._published and self._since_publish < HEARTBEAT:
            return
        self._published, self._since_publish = key, 0
        if key is None:
            channel.withdraw(w.session)
        else:
            channel.publish(LiveState(w.session, w.person_name(), *key))

    # --- the others' cursors -----------------------------------------------------------------------------

    def _show_cursors(self, editor, peers: list[LiveState]) -> None:
        for key in list(self._markers):
            if editor is None or key != id(editor):
                self._clear_editor(key)
        if editor is None:
            return
        markers = self._markers.setdefault(id(editor), {})
        if id(editor) not in self._hooked:
            self._hooked.add(id(editor))
            editor.verticalScrollBar().valueChanged.connect(lambda _=0, e=editor: self._place_labels(e))
            editor.destroyed.connect(lambda _=None, k=id(editor): (self._markers.pop(k, None), self._hooked.discard(k)))
        lines = editor.text().split("\n")
        for session in set(markers) - {s.session for s in peers}:
            markers.pop(session)[1].deleteLater()
        selections = []
        for s in peers:
            colour = people.colour_for(s.person)
            n = find_line(lines, s.line, s.line_text)
            if s.session not in markers:
                label = QLabel(s.person, editor.viewport())
                label.setStyleSheet(f"background: {colour}; color: white; border-radius: 3px; padding: 0 4px; font-size: 11px;")
                label.adjustSize()
                label.show()
                markers[s.session] = (n, label, colour)
            markers[s.session] = (n, markers[s.session][1], colour)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(editor.document().findBlockByNumber(n))
            selection.cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            tint = QColor(colour)
            tint.setAlpha(40)
            selection.format.setBackground(tint)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selections.append(selection)
        editor.setExtraSelections(selections)
        self._place_labels(editor)

    def _place_labels(self, editor) -> None:
        for line, label, _ in self._markers.get(id(editor), {}).values():
            rect = editor.cursorRect(QTextCursor(editor.document().findBlockByNumber(line)))
            label.move(max(0, editor.viewport().width() - label.width() - 6), max(0, rect.top()))

    def _clear_editor(self, key: int) -> None:
        for _, label, _ in self._markers.pop(key, {}).values():
            label.deleteLater()
        editor = next((e for e in self.window.editors.values() if id(e) == key), None)
        if editor is not None and live_editor(editor):
            editor.setExtraSelections([])

    def clear(self) -> None:
        for key in list(self._markers):
            self._clear_editor(key)
        self._published = None

    def leave(self) -> None:
        """Stop sharing (the project is closing, sync stopped, or live editing turned off)."""
        self._stop_session()
        if self._channel is not None:
            self._channel.withdraw(self.window.session)
        self.clear()
        self._channel = None
