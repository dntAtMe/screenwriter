# Screenwriter user guide

On macOS, `Ctrl` in every shortcut below means `⌘` (Command), and `Alt` means `⌥` (Option).

- [Projects and the binder](#projects-and-the-binder)
- [Writing prose](#writing-prose)
- [Writing screenplays](#writing-screenplays)
- [The Story Bible](#the-story-bible)
- [Boards: mind maps](#boards-mind-maps)
- [Corkboard](#corkboard)
- [Outline, Cast, search and find](#outline-cast-search-and-find)
- [Capturing ideas](#capturing-ideas)
- [Snapshots: version history](#snapshots-version-history)
- [Exporting](#exporting)
- [Views and focus](#views-and-focus)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [How projects are stored](#how-projects-are-stored)

## Projects and the binder

A **project** is one folder holding everything for a story: chapters, scripts, notes, boards and the
Story Bible. Create one with **File → New Project…** (`Ctrl+Shift+N`) or open an existing folder with
**File → Open Project…** (`Ctrl+O`). Screenwriter reopens your last project and its tabs on start.

The **binder** on the left lists the project's contents. Each item is one of:

| Icon | Item | Used for |
|:-:|---|---|
| **P** | Prose document | chapters, scenes of a novel, articles |
| **S** | Screenplay | scripts, written in Fountain |
| **N** | Note | research, to-dos, anything else |
| **B** | Board | mind maps and free-form card layouts |
| **C** / **L** | Character / Location | Story Bible entries |
| 📁 | Folder | groups anything; double-click to see it as a corkboard |

- **Add** items from the **Insert** menu or by right-clicking in the binder. A new item goes after the
  selected one, or inside it if a folder is selected.
- **Rename**: select and press `Enter`/`F2`, or right-click → Rename.
- **Reorder / nest**: drag items. Folders and documents can both hold other items.
- **Delete**: `Delete` moves an item to the **Trash**. Items in the Trash can be dragged back out, or
  deleted permanently from there (this can't be undone).

Everything **saves automatically** a moment after you stop typing, and when you switch tabs or quit.
**File → Save** (`Ctrl+S`) saves right away if you like the habit.

## Writing prose

Prose documents and notes use [Markdown](https://commonmark.org/help/), shown as you write:

| Type | Get |
|---|---|
| `# Chapter One` | a chapter heading (`##`, `###` for smaller headings) |
| `*italic*` or `_italic_` | *italic* |
| `**bold**` | **bold** |
| `> text` | a quotation |
| `***` on its own line | a scene break |
| `[[a note to yourself]]` | an inline note — greyed out, and left out of exports |

The word count is in the status bar; select text to count just that.

## Writing screenplays

Screenplays are written in [Fountain](https://fountain.io/syntax), a plain-text screenplay format, and laid
out like a printed script as you type. You mostly just type; Screenwriter recognises what each line is and
formats it. The current element is shown in the status bar.

### Elements

| Element | How to write it |
|---|---|
| **Scene heading** | starts with `INT.`, `EXT.`, `EST.`, `INT./EXT.` or `I/E` — or force any line with a leading `.` |
| **Action** | ordinary paragraphs |
| **Character** | a name in CAPS on its own line, with dialogue right below it; extensions like `(V.O.)` are fine |
| **Parenthetical** | `(quietly)` on its own line under a character or in dialogue |
| **Dialogue** | the lines right under a character |
| **Transition** | a CAPS line ending in `TO:` (`CUT TO:`), `FADE OUT.`, or force with a leading `>` |
| **Centered** | `> THE END <` |
| **Section** | `# Act One` — for structure; shown in the outline, not printed |
| **Synopsis** | `= what happens in this scene` — not printed |
| **Note** | `[[note to yourself]]` — not printed |
| **Title page** | `Title:`, `Credit:`, `Author:`, `Draft date:`, `Contact:` lines at the very top |

Force an element when the automatic guess is wrong: a leading `!` makes a line action (`!BANG!`), and `@`
makes it a character (`@McCLANE`).

### Typing flow

- `int` or `ext` followed by a space (or `.`) becomes `INT. ` / `EXT. `; headings and transitions are capitalised.
- **Tab** on a new line after a blank line starts a **character** (it types in caps). Tab on an empty line
  inside dialogue inserts `()` for a parenthetical. Parentheses close themselves.
- **Enter** after action, dialogue or a heading starts a new paragraph (with the blank line Fountain needs);
  after a character or parenthetical it continues with dialogue. **Shift+Enter** is a plain line break.
- Typing `cut to`, `fade out` or `dissolve to` and pressing Enter makes a proper transition.
- **Ctrl+1 … Ctrl+6** turn the current line into Scene Heading, Action, Character, Parenthetical, Dialogue or
  Transition (**Format** menu), adding whatever Fountain needs.

### Suggestions

While you type a character name, a location or a time of day, Screenwriter suggests ones already used in the
script and in the Story Bible. `↑`/`↓` to choose, `Enter`/`Tab` to accept, `Esc` to dismiss. Picking a
location in a heading goes straight on to suggest `DAY`, `NIGHT`, `CONTINUOUS`…

Undo (`Ctrl+Z`) works word by word.

## The Story Bible

The Story Bible keeps **character** and **location** sheets and connects them to your writing.

![A character entry](images/story-bible.png)

**Create** an entry with **Insert → New Character** (`Ctrl+Alt+C`) / **New Location** (`Ctrl+Alt+L`), or
straight from your writing:

- In a **script**, right-click a character cue or a scene heading → **Add “MARA” in Story Bible**
  (or **Open …** if it exists).
- Anywhere, **select a name, right-click → Add “…” to Story Bible → as a new Character / Location**.

New entries made this way go into a **Story Bible** folder in the binder.

**The form**:

- **Name** — also the item's title in the binder (renaming one renames the other).
- **Also called** — other names and forms, separated by commas: `MARA, the keeper`. Matching ignores case.
  The name itself (and a character's first name, *Mara* for *Mara Quinn*) always counts; you don't repeat it here.
  - **Inflected languages**: add each form you use (*Kacpra, Kacprowi*), or end a form with `*` to match any
    ending — `Kacpr*` finds *Kacpra, Kacprowi, Kacprem…*. Keep stems long enough to be unique (`Ma*` would also match *Mama*).
  - Quickest way: **select the form in your text, right-click → Add “Kacprowi” to Story Bible → as another name for → Kacper**.
- **Role, Age, Description** — free text. The description is shown when you hover the name and on corkboard cards.
- **Notes** — the large area below, Markdown like any prose (`## Headings` appear in the outline).

**Appears in** (right of the notes) lists where the entry shows up — scenes where a character speaks
(🗣, with the number of speeches and words spoken), mentions in scripts and chapters, and scenes set at a
location. Click a line to jump there. It refreshes when you switch to the entry, or press **Refresh**.

**In your writing**, Story Bible names are underlined with a dotted line (orange: characters, teal:
locations). Hover a name to see its description, and **Ctrl-click** (`⌘`-click) it to open the entry. Names are
suggested while you type a capitalised word, in prose as well as scripts.

## Boards: mind maps

A **board** (`Ctrl+Alt+B`) is a canvas of cards — for brainstorming, plot maps, relationship maps.

![A board](images/board.png)

| Do | How |
|---|---|
| New card | double-click empty space |
| Edit a card | double-click it, or select and press `F2`; `Enter` finishes, `Shift+Enter` for a new line |
| Child card (connected, to the right) | select a card, press `Tab` |
| Sibling card (below) | select a card, press `Enter` |
| Connect two cards | `Alt`+drag from one card to the other (or select two → right-click → Connect Cards) |
| Move / select several | drag cards; drag on empty space to select several |
| Colour | right-click → Color |
| Delete | select cards or links, press `Delete` |
| Pan | trackpad scroll, `Space`+drag, or middle-button drag |
| Zoom | pinch, `Ctrl`+scroll, or **View → Zoom In/Out** |

Drag documents, characters or locations **from the binder onto a board** to get cards linked to them (marked ↗);
double-click a linked card to open the document. The outline shows the board as a tree, starting from cards
nothing points to.

## Corkboard

Double-click a **folder** in the binder (or select it and press `Ctrl+Alt+K`) to see its contents as index cards.

![A corkboard](images/corkboard.png)

- **Reorder** by dragging cards — the binder follows.
- **Synopsis**: click a selected card, or press `F2`, and type. `Enter` saves, `Shift+Enter` adds a line.
  Synopses also show as tooltips in the binder.
- **Open** a card with a double-click or `Enter`.
- **Right-click** for colour labels, rename, new documents in this folder, or moving to the Trash.

Cards show the word count of chapters and scripts. Character and location cards show the entry's description
until you give them a synopsis.

## Outline, Cast, search and find

The side panel on the right (**View → Toggle Side Panel**, `Ctrl+Alt+\`) has three tabs:

- **Outline** (`Ctrl+Shift+O`) — the structure of the current document: numbered scenes under their sections
  for scripts, headings for prose, cards for boards and corkboards. Click to jump; it follows your cursor.
- **Search** (`Ctrl+Shift+F`) — search the whole project (except the Trash), grouped by document; click a result
  to open it there. Tick **Aa** to match case.
- **Cast** — the characters and locations mentioned in the current document, and how often. Click to open.

**Find** in the current document with `Ctrl+F`; `Enter` for the next match, `Shift+Enter` for the previous,
`Esc` to close (`Ctrl+G` / `Ctrl+Shift+G` — `F3` / `Shift+F3` on Windows — work without the find bar too).

## Capturing ideas

Press `Ctrl+Shift+I` anywhere, type the idea, and press `Ctrl+Enter`. It's added with the date and time to the
project's **Idea Inbox** note (created if the project doesn't have one yet).

## Snapshots: version history

A snapshot is a saved copy of a document you can go back to.

- **Take one** before a big rewrite: **File → Take Snapshot…** (`Ctrl+Alt+S`), optionally with a name.
- **Automatic**: the first time you change a document each day, the previous version is kept as a snapshot.
- **Browse** with **File → Snapshots…** (`Ctrl+Alt+H`): pick a version to see what's changed since
  (removed words struck through in red, added words in green) or the version itself.
- **Restore This Version** replaces the document. The current text is kept as a *Before restore* snapshot
  first, and you can also undo the restore.

## Exporting

Select what to export in the binder and choose **File → Export…** (`Ctrl+E`):

| Select | Formats |
|---|---|
| A screenplay | **PDF** in standard screenplay format · **Final Draft** (`.fdx`) · **Fountain** |
| A chapter or note | **PDF** · **Word** (`.docx`) · **Markdown** |
| A folder | the folder's prose documents **compiled in binder order**, as PDF, Word or Markdown |
| A board | **PNG** image or **PDF** |

- **Screenplay PDF**: Courier 12pt with industry margins and indents, a title page from the `Title:` lines,
  page numbers from page 2, scene headings never stranded at the bottom of a page, and `(MORE)` / `(CONT'D)`
  when dialogue continues on the next page. Letter or A4.
- **Manuscript** (PDF and Word): each `# Heading` starts a new page; Word files use standard manuscript format
  (Times 12pt, double spaced, first-line indents). A chapter without its own heading gets its title as one.
- `[[Notes]]` are never exported, and neither are a script's `# sections` and `= synopses`.

## Views and focus

- **Focus mode** (`Ctrl+Shift+D`) hides everything but the page. Press it again to come back.
- **Full screen**: **View → Full Screen**.
- **Zoom** (`Ctrl++` / `Ctrl+-`) changes the text size of the current document.
- Hide the binder with `Ctrl+\` and the side panel with `Ctrl+Alt+\`.

## Keyboard shortcuts

| | |
|---|---|
| **Projects** | |
| New project / Open project | `Ctrl+Shift+N` / `Ctrl+O` |
| Save now / Close tab | `Ctrl+S` / `Ctrl+W` |
| Export | `Ctrl+E` |
| Take snapshot / Browse snapshots | `Ctrl+Alt+S` / `Ctrl+Alt+H` |
| **New items** | |
| Prose document / Screenplay / Note | `Ctrl+N` / `Ctrl+Alt+N` / `Ctrl+Shift+J` |
| Board / Folder | `Ctrl+Alt+B` / `Ctrl+Shift+G` |
| Character / Location | `Ctrl+Alt+C` / `Ctrl+Alt+L` |
| Capture an idea | `Ctrl+Shift+I` |
| **Editing** | |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` (`Ctrl+Y` on Windows) |
| Find / next / previous | `Ctrl+F` / `Ctrl+G` / `Ctrl+Shift+G` (`F3` / `Shift+F3` on Windows) |
| Search the project | `Ctrl+Shift+F` |
| Screenplay element | `Ctrl+1` … `Ctrl+6` |
| **View** | |
| Outline / Corkboard | `Ctrl+Shift+O` / `Ctrl+Alt+K` |
| Binder / side panel | `Ctrl+\` / `Ctrl+Alt+\` |
| Focus mode | `Ctrl+Shift+D` |
| Zoom in / out | `Ctrl++` / `Ctrl+-` |

**Help → Screenplay Keys** and **Help → Board Keys** show the in-editor keys inside the app.

## How projects are stored

A project is an ordinary folder you can back up, sync or keep in git:

```
My Story/
  project.json          the binder: order, titles, synopses, labels
  docs/<id>.md          prose, notes and Story Bible entries (Markdown)
  docs/<id>.fountain    screenplays (Fountain)
  docs/<id>.board.json  boards
  snapshots/<id>/       earlier versions of each document
```

Files are named by a short id; the titles live in `project.json`. Every text file opens in any editor, and
`.fountain` files open in other screenwriting apps (Highland, Slugline, Fade In, Final Draft's importer…).
