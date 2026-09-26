# Screenwriter

A personal, tunable writing app for screenplays, books, notes and ideas, built with Qt (PySide6).

## Run

```bash
uv run python -m screenwriter                               # reopens the last project
uv run python -m screenwriter ~/Documents/"My Story"        # open a specific project
```

To try the sample, copy it first so your edits don't end up in the repo:

```bash
cp -R "examples/The Lighthouse" ~/Documents/ && uv run python -m screenwriter ~/Documents/"The Lighthouse"
```

Tests: `uv run pytest`

## What's there

- **Binder**: a tree of folders and documents (prose, screenplay, note). Drag to reorder or nest. Right-click to add, rename or trash. Items in the Trash can be deleted permanently.
- **Prose editor**: Markdown in a centred serif column, with live headings, *emphasis* and `[[inline notes]]`, plus word count (including selection).
- **Screenplay editor**: [Fountain](https://fountain.io) text laid out like a script page, with scene headings, character cues, parentheticals, dialogue, transitions, sections, synopses and notes. Formatting follows what you type:
  - `int`/`ext`/`i/e` + space becomes `INT.`/`EXT.`/`INT./EXT.`; headings and transitions are capitalised.
  - `cut to`, `fade out` or `dissolve to` + Enter becomes a proper transition.
  - A line in caps becomes a character cue; the dialogue under it is indented. A caps word starting an action line doesn't jump.
  - Completion for character names (plus `V.O.`, `O.S.`, `CONT'D`), locations and times of day, taken from your script.
  - `Tab` starts a cue on a new line, or adds `()` in dialogue. Parentheses close themselves.
  - `Enter` moves to the next logical element; `Shift+Enter` gives a plain line break.
  - `Ctrl+1…6` turns the line into Scene Heading, Action, Character, Parenthetical, Dialogue or Transition.
  - Undo works word by word and never replays stale formatting.
- **Boards** (`Ctrl+Alt+B`): a canvas of cards for mind maps and corkboards.
  - Double-click to add a card. `Tab` adds a connected child card; `Enter` adds a sibling.
  - `Alt`+drag from one card to another connects them. Drag to move; drag on empty space to select several.
  - Cards come in six colours. Pan with the trackpad, `Space`+drag or middle-drag; zoom with pinch or `Ctrl`+wheel.
  - Drag chapters, scenes or notes from the binder onto a board to get cards linked to them; double-click one to open it.
  - The outline shows the map as a tree, and search covers card text.
- **Outline** (`Ctrl+Shift+O`): numbered scenes under their sections for scripts, headings for prose. Click to jump; it follows the cursor.
- **Search** (`Ctrl+Shift+F`): matches across the whole project, grouped by document. **Find** (`Ctrl+F`, `Ctrl+G`) searches the current document.
- **Idea capture** (`Ctrl+Shift+I`): jot an idea from anywhere; it lands, timestamped, in the project's Idea Inbox note.
- **Export** (`Ctrl+E`, for the item selected in the binder):
  - Screenplays: industry-format **PDF** (Courier 12pt, standard margins and indents, a title page from Fountain `Title:`/`Author:`/… lines, page numbers, scene headings kept with what follows, `(MORE)`/`(CONT'D)` when dialogue breaks across pages), **Final Draft `.fdx`** and **Fountain**.
  - Prose: one chapter, or a whole folder compiled in binder order, as **PDF**, **Word `.docx`** (standard manuscript format: Times 12pt, double spaced, chapters on new pages) or **Markdown**. `[[notes]]` are left out.
  - Boards: **PNG** or **PDF** image.
- **Autosave** shortly after you stop typing, and on tab switch or close. Open tabs are restored per project.
- **Focus mode** (`Ctrl+Shift+D`), full screen, zoom.

On macOS, `Ctrl` in these shortcuts is `⌘`.

## Project format

A project is a plain folder, so it can be read, diffed and versioned without the app:

```
My Story/
  project.json          binder tree + metadata
  docs/<id>.md          prose and notes
  docs/<id>.fountain    screenplays
  docs/<id>.board.json  boards (cards + links)
```

`project.json` also records which note is the Idea Inbox.

## Roadmap

1. ~~App shell, binder, project format~~
2. ~~Prose editor~~
3. ~~Fountain screenplay editor~~, smart formatting, completion, outline
4. ~~Ideas inbox with quick capture, project-wide search~~
5. ~~Mind map / corkboard canvas~~
6. ~~Export: screenplay PDF, Final Draft, manuscript PDF/Word/Markdown, board images~~ (EPUB via Pandoc: later)
7. Snapshots / version history
