"""The document area: one tab pane, or two side by side / one above the other.

TabArea answers the same calls as the QTabWidget it replaces (currentWidget,
addTab, indexOf, …) with indexes that count through every pane in order, so
the main window mostly doesn't care whether the view is split. The "current"
tab is the one in the active pane — the pane you last clicked or typed in —
and new tabs open there.

A document is open in one pane at a time; splitting moves the current tab
into the new pane, and a pane that runs out of tabs closes.
"""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QApplication, QSplitter, QTabWidget, QVBoxLayout, QWidget

ACTIVE_STYLE = "QTabBar::tab:selected { border-bottom: 2px solid palette(highlight); }"


class TabArea(QWidget):
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)
        self.panes: list[QTabWidget] = []
        self._bars_hidden = False
        self.active = self._add_pane()
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

    # --- panes ------------------------------------------------------------------------

    def _add_pane(self) -> QTabWidget:
        pane = QTabWidget()
        pane.setDocumentMode(True)
        pane.setTabsClosable(True)
        pane.setMovable(True)
        pane.setElideMode(Qt.TextElideMode.ElideRight)
        pane.tabBar().setExpanding(False)
        pane.tabBar().setVisible(not self._bars_hidden)
        pane.tabCloseRequested.connect(lambda i, p=pane: self.tabCloseRequested.emit(self._global(p, i)))
        pane.currentChanged.connect(lambda _i, p=pane: self._on_pane_changed(p))
        pane.tabBarClicked.connect(lambda _i, p=pane: self._activate(p))
        pane.tabBar().installEventFilter(self)
        self.splitter.addWidget(pane)
        self.panes.append(pane)
        return pane

    def is_split(self) -> bool:
        return len(self.panes) > 1

    def orientation(self) -> Qt.Orientation:
        return self.splitter.orientation()

    def split(self, orientation: Qt.Orientation) -> None:
        """Split side by side (Horizontal) or one above the other (Vertical), taking the
        current tab into the other pane. Already split: change the direction, and move it over."""
        self.splitter.setOrientation(orientation)
        if not self.is_split():
            if self.active.count() < 2:
                return  # nothing to put beside it; the direction is remembered for later
            self._add_pane()
            total = sum(self.splitter.sizes()) or 2
            self.splitter.setSizes([total // 2, total - total // 2])
        self.move_to_other_pane()

    def unsplit(self) -> None:
        """Back to one pane, with every tab in it."""
        if not self.is_split():
            return
        current = self.currentWidget()
        keep = self.panes[0]
        for pane in self.panes[1:]:
            while pane.count():
                widget, title = pane.widget(0), pane.tabText(0)
                pane.removeTab(0)
                keep.addTab(widget, title)
            self._drop_pane(pane)
        self._activate(keep)
        if current is not None:
            keep.setCurrentWidget(current)
            current.setFocus()

    def other_pane(self) -> QTabWidget | None:
        if not self.is_split():
            return None
        return self.panes[1] if self.active is self.panes[0] else self.panes[0]

    def move_to_other_pane(self, widget: QWidget | None = None) -> None:
        """Move a tab (the current one) to the other pane and make that pane active."""
        widget = widget or self.currentWidget()
        other = self.other_pane()
        if widget is None or other is None:
            return
        source = self._pane_of(widget)
        index = source.indexOf(widget)
        title = source.tabText(index)
        source.blockSignals(True)
        source.removeTab(index)
        source.blockSignals(False)
        other.setCurrentIndex(other.addTab(widget, title))
        self._activate(other)
        if source.count() == 0:
            self._drop_pane(source)
        widget.setFocus()
        self.currentChanged.emit(self.currentIndex())

    def focus_other_pane(self) -> None:
        if other := self.other_pane():
            self._activate(other)
            if widget := other.currentWidget():
                widget.setFocus()

    def _drop_pane(self, pane: QTabWidget) -> None:
        if len(self.panes) == 1:
            return
        self.panes.remove(pane)
        pane.hide()
        pane.setParent(None)
        pane.deleteLater()
        if self.active is pane:
            self.active = self.panes[0]
        self._mark_active()

    def _activate(self, pane: QTabWidget) -> None:
        if pane is self.active or pane not in self.panes:
            return
        self.active = pane
        self._mark_active()
        self.currentChanged.emit(self.currentIndex())

    def _mark_active(self) -> None:
        """Underline the current tab of the active pane, when there's more than one."""
        for pane in self.panes:
            pane.tabBar().setStyleSheet(ACTIVE_STYLE if self.is_split() and pane is self.active else "")

    def _pane_of(self, widget: QWidget) -> QTabWidget | None:
        return next((p for p in self.panes if p.indexOf(widget) >= 0), None)

    def detach(self) -> None:
        """Stop following application focus (the window is closing)."""
        QApplication.instance().focusChanged.disconnect(self._on_focus_changed)

    def _on_focus_changed(self, _old, new) -> None:
        while new is not None:
            if new in self.panes:
                self._activate(new)
                return
            new = new.parentWidget()

    def _on_pane_changed(self, pane: QTabWidget) -> None:
        if pane.count() == 0 and self.is_split():  # its last tab closed: the other pane takes the space
            was_active = pane is self.active
            self._drop_pane(pane)
            if was_active:
                self.currentChanged.emit(self.currentIndex())
        elif pane is self.active:
            self.currentChanged.emit(self.currentIndex())

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress:
            for pane in self.panes:
                if obj is pane.tabBar():
                    self._activate(pane)
        return False

    # --- QTabWidget-like interface, indexes counted through all panes -------------------------

    def _global(self, pane: QTabWidget, index: int) -> int:
        if index < 0:
            return -1
        offset = 0
        for p in self.panes:
            if p is pane:
                return offset + index
            offset += p.count()
        return -1

    def _local(self, index: int) -> tuple[QTabWidget | None, int]:
        for pane in self.panes:
            if 0 <= index < pane.count():
                return pane, index
            index -= pane.count()
        return None, -1

    def count(self) -> int:
        return sum(p.count() for p in self.panes)

    def widget(self, index: int) -> QWidget | None:
        pane, i = self._local(index)
        return pane.widget(i) if pane else None

    def indexOf(self, widget: QWidget) -> int:
        pane = self._pane_of(widget)
        return self._global(pane, pane.indexOf(widget)) if pane else -1

    def currentWidget(self) -> QWidget | None:
        return self.active.currentWidget()

    def currentIndex(self) -> int:
        return self._global(self.active, self.active.currentIndex())

    def setCurrentWidget(self, widget: QWidget) -> None:
        if pane := self._pane_of(widget):
            self._activate(pane)
            pane.setCurrentWidget(widget)

    def setCurrentIndex(self, index: int) -> None:
        pane, i = self._local(index)
        if pane:
            self._activate(pane)
            pane.setCurrentIndex(i)

    def addTab(self, widget: QWidget, title: str) -> int:
        return self._global(self.active, self.active.addTab(widget, title))

    def removeTab(self, index: int) -> None:
        pane, i = self._local(index)
        if pane:
            pane.removeTab(i)

    def tabText(self, index: int) -> str:
        pane, i = self._local(index)
        return pane.tabText(i) if pane else ""

    def setTabText(self, index: int, text: str) -> None:
        pane, i = self._local(index)
        if pane:
            pane.setTabText(i, text)

    # --- moving through tabs -----------------------------------------------------------

    def next_tab(self, step: int = 1) -> None:
        """Next / previous tab in the active pane, wrapping around."""
        if self.active.count():
            self.active.setCurrentIndex((self.active.currentIndex() + step) % self.active.count())
            self.active.currentWidget().setFocus()

    def go_to_tab(self, number: int) -> None:
        """Tab `number` (1-based) of the active pane; 9 is always the last one, as in browsers."""
        count = self.active.count()
        if count:
            index = count - 1 if number == 9 else number - 1
            if index < count:
                self.active.setCurrentIndex(index)
                self.active.currentWidget().setFocus()

    def set_tab_bars_visible(self, visible: bool) -> None:
        self._bars_hidden = not visible
        for pane in self.panes:
            pane.tabBar().setVisible(visible)

    def tab_bars_hidden(self) -> bool:
        return self._bars_hidden
