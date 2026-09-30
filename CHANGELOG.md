# Changelog

All notable changes to Screenwriter are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added
- **Factions and Items** in the Story Bible, next to Characters and Locations: guilds, cults and kingdoms
  with their leader and aims; artefacts and treasure with their type, rarity and who holds them. Their
  names are found and highlighted in your writing like any other entry (Insert ▸ New Faction ⌥⌃F / New Item ⌥⌃I).
- **Tabletop campaigns.** New Project asks what you're starting; a *Tabletop campaign* (also **New Campaign**
  on the start screen) comes with folders for sessions, adventures, player characters, NPCs, locations,
  factions and items, a campaign overview (pitch, safety tools, the party), world lore, random tables and a
  relationship board. New Story Bible entries go into the matching folder.
- **Sessions.** Insert ▸ New Session (⌥⌃E) adds the next numbered session from a prep template — recap,
  strong start, scenes, secrets & clues, NPCs, treasure — and fills its recap from what you noted during
  the last one.
- Notes are now searched for Story Bible names too, so an NPC's *Appears in* lists the sessions they were in.

### Changed
- **A new look.** Calm, modern styling in light and dark: soft panel colours, rounded selection, pill-shaped
  tabs, thin scrollbars and one ink-blue accent, the same on macOS, Windows and Linux.
- **New icons** for every kind of document (page, clapperboard, sticky note, board, person, map pin) and for
  the toolbar, crisp at any size and recoloured for dark mode.
- **A header bar** with the project's name and save/sync state, and labelled **New**, **Find**, **History** and
  **Sync** buttons, plus toggles for the binder, the side panel and focus mode.
- The binder has a **Project** heading with a **+** menu for new items; the side panel's tabs are a compact
  icon switcher that names the open tab.
- A new **start screen**, and a hint with quick buttons where documents go when none is open.
- **Story Bible names** get a soft highlight instead of a dotted underline — amber for characters, teal for
  locations — in prose and now in scripts too (action, cues, scene headings). The name under the mouse
  deepens, so it's clear it can be hovered and ⌘/Ctrl-clicked. Underlines now only ever mean a spelling mistake.

## [0.7.0] - 2026-09-27

### Added
- **Fonts**: View → Fonts… picks the script, prose and screenplay-PDF fonts from eleven bundled
  typewriter-style fonts (all with Polish letters), with a preview. iA Writer Duo is the new default for writing;
  screenplay PDFs stay in Courier Prime unless you pick another font of the same width.
- **Dark mode**: View → Appearance → Follow System / Light / Dark, switched without a restart.
- **Save status**: the status bar shows *Editing…* while you type and *✓ Saved 14:32* once your work is on disk;
  `Ctrl+S` confirms with a message.
- **Smooth letters** (on by default): softer, grayscale-antialiased text without pixel snapping. On Windows it uses
  FreeType rendering, so changing it takes effect after a restart.

### Fixed
- Polish words were marked as misspelled in projects that hadn't chosen spelling languages on a computer set to
  English. Such projects now check Polish too as soon as they contain Polish letters.

## [0.6.0] - 2026-09-27

### Added
- **Comments**: select text and add a comment (`Ctrl+Shift+M`); reply, resolve and delete in the new **Comments**
  tab. Commented text is highlighted, comments follow their words as the text changes, and they sync — everyone's
  comments and replies are kept when copies merge.
- **Spell checking** in Polish and English (US / UK): red squiggles, suggestions and a project dictionary shared
  through sync; languages per project (**Edit → Spelling**), Story Bible names always accepted.
- **Mentions before a character is named**: mark a description (“the hooded figure”) as a Story Bible character
  from the right-click menu — one mention, or every one in the document — and a script's description cue
  (HOODED FIGURE) as that character for the whole script. They count in **Appears in** and the **Cast** panel,
  and print as written.

## [0.5.0] - 2026-09-27

### Added
- **Live editing** on shared folders and network drives: see what others type in the same chapter or script
  within a second or two, with their paragraph tinted and named in their colour (**View → Live Editing**).

### Changed
- Merging goes down to words: two people changing different sentences of the same paragraph no longer conflict,
  and text both added at the same spot is kept from both instead of becoming a conflict.
- A sync that brings in changes to an open document keeps your cursor and scroll position.
- Documents are saved with the same line endings on every system, and merging ignores the difference, so
  projects shared between Windows and Mac/Linux merge line by line.

## [0.4.0] - 2026-09-27

### Added
- **Writing together** through a shared folder (a network drive, or a shared Dropbox/OneDrive/Drive folder):
  set your name once (**File → Your Name…**); the status bar shows who else has the project open, the binder marks
  the documents they have open with their coloured initial, and a note above the page says when someone has the
  same document open. Save points, merges and conflicts show who made the changes.
- **Updates** tab in the side panel: recent changes by other people (and your other computers) — who, when,
  which documents, words added or removed — with what's new since you last looked in bold. Documents someone
  else changed are bold in the binder until you open them, and a notice says who changed what when it arrives.
- **Quicker sync while writing together**: with someone else in the project, sync runs about ten seconds after
  you stop typing and checks for their changes every 15 seconds. Two people saving to a shared drive at once take
  turns, and cloud apps' “conflicted copy” files of the project are merged back in and set aside.

### Changed
- **Sync merges paragraph by paragraph**: when two people (or computers) edit the same document, changes to
  different paragraphs combine, and boards merge card by card. Only the same paragraph changed differently is a
  conflict — instead of a “(from Laptop)” copy of the whole document, **Review Conflicts** shows both versions
  side by side to keep either or both. Conflicts sync, so anyone can resolve them.

### Removed
- The single “open on another computer” notice; presence (above) replaces it, for any number of people.
- **File → Older Snapshots…** and the per-document snapshots from before project history. A project's
  `snapshots` folder is no longer read; everything since 0.2.0 is in **History…**.

## [0.3.1] - 2026-09-27

### Fixed
- Screenplay PDFs and Final Draft files keep **bold**, *italic* and _underline_ (they were printed plain).
- `\*` and `\_` in a script print as a plain `*` or `_` instead of a stray backslash.

## [0.3.0] - 2026-09-27

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

[Unreleased]: https://github.com/dntAtMe/screenwriter/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/dntAtMe/screenwriter/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/dntAtMe/screenwriter/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/dntAtMe/screenwriter/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/dntAtMe/screenwriter/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/dntAtMe/screenwriter/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/dntAtMe/screenwriter/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dntAtMe/screenwriter/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dntAtMe/screenwriter/releases/tag/v0.1.0
