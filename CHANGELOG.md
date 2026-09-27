# Changelog

All notable changes to Screenwriter are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **Go to Document** (press `Shift` twice, or `Ctrl+P`): type part of a name to jump to any document, folder
  corkboard or board card; open tabs come first. `Shift+Enter` opens it on the other side of a split view.
- **Split view**: **View → Split Right** (`Ctrl+Alt+R`) or **Split Down** (`Ctrl+Alt+D`) shows two documents at
  once. **Move Tab to Other Side** (`Ctrl+Alt+M`), **Focus Other Side** (`F6`), **Unsplit** (`Ctrl+Alt+W`).
- **Switching tabs**: `Ctrl+Tab` / `Ctrl+Shift+Tab` (or `Ctrl+PgDown` / `Ctrl+PgUp`) for the next / previous tab,
  `Alt+1` … `Alt+8` for a tab by position and `Alt+9` for the last one.

### Changed
- In a narrow editor (such as half of a split view) a screenplay's indents shrink with it, so dialogue keeps
  its shape.

## [0.2.0] - 2026-09-27

### Added
- **Project history**: automatic save points of the whole project (on open, every few minutes of changes, on
  close) and named versions (**Save Version…**). **History…** shows what each save point changed, compares any
  version with now, and restores one document — even a deleted one — or the whole project.
- **Sync & Backup** through a cloud folder (Google Drive, Dropbox, iCloud Drive, OneDrive, or any folder): the
  project and its history live there as one `.screenwriter` file, synced on open, on close, every few minutes
  and when the file changes. Changes from two computers are merged; a document changed on both keeps both
  versions. A notice when the project is open on another computer.
- **Sign in with Google**: sync projects through Google Drive directly, without the Drive app (works on Linux
  too). Access is limited to files Screenwriter creates; the sign-in is kept in the system's secure store.
  **File → Open from Google Drive…** sets a project up on another computer.
- **Share a Copy…** and **Open Project File…** for `.screenwriter` files.
- **Formatting toolbar** above the page: screenplay elements (showing the current line's), bold, italic,
  underline, notes, sections, synopses and centered text in scripts; headings, bold, italic, quotes, scene breaks
  and notes in prose. Buttons add or remove the markup for you. **View → Formatting Toolbar** hides it.
- **Shortcut hints**: hold `Ctrl` or `Alt` for a moment to see every shortcut that starts with the keys you're
  holding; add `Shift` to narrow the list. **View → Shortcut Hints** turns them off.

### Changed
- Per-document snapshots are replaced by project history; existing ones are under **File → Older Snapshots…**.

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
- Released under the MIT License.

[Unreleased]: https://github.com/dntAtMe/screenwriter/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dntAtMe/screenwriter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dntAtMe/screenwriter/releases/tag/v0.1.0
