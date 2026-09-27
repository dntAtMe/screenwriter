"""Spell checking: Polish and English (US / UK) Hunspell dictionaries, via spylls.

Each project chooses its languages (a word is right if any of them knows it) and keeps
its own word list, dictionary.txt, which syncs with the project, so everyone writing it
shares it. Story Bible names count as known words too.

Loading a dictionary takes a few seconds (Polish), and checking a word about a
millisecond, so both happen on a background thread: the editors ask about a word, get
"not known yet", and are told to redraw when the answers are in.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

from PySide6.QtCore import QLocale, QObject, Signal

from .marks import MARK_RE

DICTIONARIES = Path(__file__).resolve().parent / "resources" / "dictionaries"
LANGUAGES = {"pl_PL": "Polski", "en_US": "English (US)", "en_GB": "English (UK)"}
WORD_FILE = "dictionary.txt"  # the project's own words, one per line

# a word: letters, with apostrophes inside ("Keeper's", "don't")
WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
SKIP_RE = re.compile(r"https?://\S+|\S+@\S+\.\S+")  # links and e-mail addresses


def default_languages() -> list[str]:
    """What this computer's language suggests: Polish writers usually write English too."""
    name = QLocale.system().name()
    if name.startswith("pl"):
        return ["pl_PL", "en_US"]
    return ["en_GB"] if name in ("en_GB", "en_IE", "en_AU", "en_NZ") else ["en_US"]


def read_words(project_path: Path) -> set[str]:
    try:
        text = (project_path / WORD_FILE).read_text(encoding="utf-8")
    except OSError:
        return set()
    return {w.strip() for w in text.splitlines() if w.strip()}


def add_word(project_path: Path, word: str) -> None:
    words = read_words(project_path) | {word}
    (project_path / WORD_FILE).write_text("".join(f"{w}\n" for w in sorted(words, key=str.lower)), encoding="utf-8",
                                          newline="\n")


def words_to_check(text: str):
    """(start, end, word) for the words of a line worth checking."""
    skip = [(m.start(), m.end()) for m in SKIP_RE.finditer(text)]
    skip += [(m.start(2), m.end(2)) for m in MARK_RE.finditer(text)]  # the hidden name in {the hooded figure|Xardas}
    for m in WORD_RE.finditer(text):
        if any(a <= m.start() < b for a, b in skip):
            continue
        word = m.group(0)
        if len(word) < 2 or (word.isupper() and len(word) <= 3):  # INT, EXT, V.O.…
            continue
        yield m.start(), m.end(), word


_loaded: dict[str, object] = {}  # language -> spylls Dictionary, loaded once for the whole app
_loading = threading.Lock()


def _dictionary(lang: str):
    with _loading:
        if lang not in _loaded:
            from spylls.hunspell import Dictionary

            _loaded[lang] = Dictionary.from_zip(str(DICTIONARIES / f"{lang}.zip"))
        return _loaded[lang]


class Speller:
    """The dictionaries themselves (Qt-free)."""

    def __init__(self, languages: list[str]):
        self.dictionaries = [_dictionary(lang) for lang in languages if (DICTIONARIES / f"{lang}.zip").exists()]

    def correct(self, word: str) -> bool:
        word = word.replace("’", "'")
        return not self.dictionaries or any(d.lookup(word) for d in self.dictionaries)

    def suggest(self, word: str, limit: int = 6) -> list[str]:
        out: list[str] = []
        for d in self.dictionaries:
            for s in d.suggest(word.replace("’", "'")):
                if s not in out:
                    out.append(s)
                if len(out) >= limit * len(self.dictionaries):
                    break
        return out[:limit]


class SpellService(QObject):
    """Answers "is this word right?" for the editors, checking on a background thread."""

    checked = Signal()  # some answers came in: time to redraw
    suggestions = Signal(str, list)  # word, suggestions

    def __init__(self, parent=None):
        super().__init__(parent)
        self.enabled = True
        self.languages: list[str] = []
        self.known: set[str] = set()  # lower-case: project words, Story Bible names
        self.ignored: set[str] = set()  # "Ignore" for this session
        self._speller: Speller | None = None
        self._cache: dict[str, bool] = {}
        self._pending: set[str] = set()
        self._wanted_suggestions: list[str] = []
        self._lock = threading.Condition()
        self._generation = 0
        self._stopped = False
        self._thread = threading.Thread(target=self._work, name="spelling", daemon=True)
        self._thread.start()

    # --- settings ------------------------------------------------------------------------

    def set_languages(self, languages: list[str]) -> None:
        if languages == self.languages:
            return
        with self._lock:
            self.languages = list(languages)
            self._generation += 1
            self._speller = None
            self._cache.clear()
            self._pending.clear()
            self._lock.notify()
        self.checked.emit()

    def set_known(self, words: set[str]) -> None:
        words = {w.lower() for w in words}
        if words != self.known:
            self.known = words
            self.checked.emit()

    def ignore(self, word: str) -> None:
        self.ignored.add(word.lower())
        self.checked.emit()

    # --- asking -------------------------------------------------------------------------------

    def status(self, word: str) -> bool | None:
        """True if right, False if not, None if not checked yet (it will be: watch `checked`)."""
        if not self.enabled or not self.languages:
            return True
        lower = word.lower()
        if lower in self.known or lower in self.ignored:
            return True
        found = self._cache.get(word)
        if found is None:
            with self._lock:
                if word not in self._pending:
                    self._pending.add(word)
                    self._lock.notify()
        return found

    def request_suggestions(self, word: str) -> None:
        with self._lock:
            self._wanted_suggestions.append(word)
            self._lock.notify()

    def stop(self) -> None:
        """End the background thread (the window is closing)."""
        with self._lock:
            self._stopped = True
            self._lock.notify()

    def _emit(self, signal, *args) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:  # the window went away meanwhile
            self._stopped = True

    # --- the background thread ------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            with self._lock:
                while not self._stopped and not (
                        self.languages and (self._pending or self._wanted_suggestions or self._speller is None)):
                    self._lock.wait()
                if self._stopped:
                    return
                generation, languages = self._generation, list(self.languages)
                speller = self._speller
            if speller is None:
                try:
                    speller = Speller(languages)
                except Exception:  # a broken dictionary shouldn't take the app down
                    speller = Speller([])
                with self._lock:
                    if generation != self._generation:
                        continue  # the languages changed meanwhile
                    self._speller = speller
            with self._lock:
                batch, self._pending = list(self._pending)[:400], set(list(self._pending)[400:])
                wanted, self._wanted_suggestions = self._wanted_suggestions, []
            if batch:
                results = {w: speller.correct(w) for w in batch}
                with self._lock:
                    if generation == self._generation:
                        self._cache.update(results)
                self._emit(self.checked)
            for word in wanted:
                self._emit(self.suggestions, word, speller.suggest(word))
