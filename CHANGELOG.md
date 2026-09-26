# Changelog

All notable changes to Screenwriter are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-09-26

The first release.

### Writing
- **Binder** of folders, chapters, screenplays, notes, boards and Story Bible entries: drag to reorder and nest, Trash with restore.
- **Prose editor**: Markdown in a centred column, inline `[[notes]]`, word counts.
- **Screenplay editor** for Fountain, laid out like a script page as you type:
  scene headings, character cues, dialogue, parentheticals, transitions, sections, synopses, title page;
  smart typing (`int` → `INT.`, `cut to` → `CUT TO:`, Tab for cues and parentheticals);
  suggestions for characters, locations and times of day; `Ctrl+1…6` to set the element; word-by-word undo.

### Planning
- **Story Bible**: character and location entries with a form and notes, *Also called* forms (with `stem*`
  matching for inflected languages), and **Appears in** — speeches, words spoken, scenes and mentions.
  Names are underlined in prose (hover card, ⌘/Ctrl-click to open), suggested while typing, and can be added
  from any selection. **Cast** panel for the current document.
- **Boards**: mind-map canvas with coloured cards, links, child/sibling keys, cards linked to documents.
- **Corkboard**: any folder as index cards with synopses, colour labels and word counts; drag to reorder.
- **Outline** of scenes and headings, **project search**, **find**, and **quick idea capture** into an Idea Inbox.

### Output and safety
- **Export**: screenplay PDF in industry format (title page, `(MORE)`/`(CONT'D)`), Final Draft `.fdx`,
  Fountain; manuscript PDF, Word `.docx` (standard manuscript format) and Markdown, per chapter or compiled
  per folder; board images (PNG, PDF).
- **Snapshots**: named and automatic daily versions of each document, word-level comparison, undoable restore.
- Autosave, restored tabs, focus mode, zoom.
- Packages for macOS (`.dmg`), Windows (installer and portable `.zip`) and Linux (`.AppImage`, `.tar.gz`).

[Unreleased]: https://github.com/dntAtMe/screenwriter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dntAtMe/screenwriter/releases/tag/v0.1.0
