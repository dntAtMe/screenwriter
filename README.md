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
- **Screenplay editor**: [Fountain](https://fountain.io) text laid out like a script page, with scene headings, character cues, parentheticals, dialogue, transitions, sections, synopses and notes.
  - `Tab` on a new line starts a CHARACTER cue (auto caps); on an empty dialogue line it inserts `()`.
  - `Enter` after action, dialogue or a scene heading starts a new paragraph; after a cue it continues with dialogue.
  - `Shift+Enter` gives a plain line break.
- **Autosave** shortly after you stop typing, and on tab switch or close. Open tabs are restored per project.
- **Focus mode** (`Ctrl+Shift+F`), full screen, zoom.

## Project format

A project is a plain folder, so it can be read, diffed and versioned without the app:

```
My Story/
  project.json          binder tree + metadata
  docs/<id>.md          prose and notes
  docs/<id>.fountain    screenplays
```

## Roadmap

1. ~~App shell, binder, project format~~
2. ~~Prose editor~~
3. ~~Fountain screenplay editor~~ (next: character-name autocomplete, scene navigator)
4. Ideas inbox with quick-capture and project-wide search
5. Mind map / corkboard canvas (`QGraphicsView`)
6. Export: PDF (screenplay page format), Final Draft `.fdx`, `.docx`/EPUB via Pandoc
7. Snapshots / version history
