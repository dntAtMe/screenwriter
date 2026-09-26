# Screenwriter

A personal, tunable writing app for screenplays, books, notes and ideas, built with Qt (PySide6).

## Run

```bash
uv run python -m screenwriter                               # reopens the last project
uv run python -m screenwriter "examples/The Lighthouse"     # open a specific project
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
- **Outline** (`Ctrl+Shift+O`): numbered scenes under their sections for scripts, headings for prose. Click to jump; it follows the cursor.
- **Search** (`Ctrl+Shift+F`): matches across the whole project, grouped by document. **Find** (`Ctrl+F`, `Ctrl+G`) searches the current document.
- **Idea capture** (`Ctrl+Shift+I`): jot an idea from anywhere; it lands, timestamped, in the project's Idea Inbox note.
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
```

`project.json` also records which note is the Idea Inbox.

## Roadmap

1. ~~App shell, binder, project format~~
2. ~~Prose editor~~
3. ~~Fountain screenplay editor~~, smart formatting, completion, outline
4. ~~Ideas inbox with quick capture, project-wide search~~
5. Mind map / corkboard canvas (`QGraphicsView`)
6. Export: PDF (screenplay page format), Final Draft `.fdx`, `.docx`/EPUB via Pandoc
7. Snapshots / version history
