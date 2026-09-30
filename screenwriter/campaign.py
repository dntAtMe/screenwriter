"""Tabletop campaigns: a starter project for game masters, and numbered session notes.

A campaign is an ordinary project with folders a GM reaches for — Sessions, Adventures,
the Story Bible split into NPCs, Locations, Factions and Items — and a few starter
documents. Sessions are notes written from a prep template (after "The Lazy Dungeon
Master"); a new one opens with a recap taken from what happened in the last.
"""

from __future__ import annotations

import re

from .project import BOARD, CHARACTER, FACTION, FOLDER, ITEM, LOCATION, NOTE, PROSE, Node, Project

SESSIONS = "Sessions"
PLAY_NOTES = "What happened"  # the section filled in at the table, the next session's recap

SESSION_TEMPLATE = """# {title}

Date:
Players:

## Recap
{recap}

## Strong start
How the session opens — straight into something happening.

## Scenes
-

## Secrets & clues
Things the players could discover, in no particular order.
-

## NPCs & places

## Treasure

## {play_notes}
Jot it down as you play: it becomes next session's recap.
"""

OVERVIEW = """# {name}

## Pitch
One or two sentences: what the campaign is about.

## Tone & themes

## Safety tools
Lines (never in the game):
Veils (happen off-screen):

## The party
| Player | Character | Class & level | Hooks |
|---|---|---|---|
| | | | |

## House rules
"""

LORE = """# World Lore

## History

## Gods & powers

## Calendar & holidays
"""

TABLES = """# Random Tables

## Rumours in the tavern
| d6 | Rumour |
|---|---|
| 1 | |
| 2 | |
| 3 | |
| 4 | |
| 5 | |
| 6 | |

## NPC names
-
"""

ADVENTURE = """# First Adventure

## Hook

## The situation
What's going on before the party arrives, and what happens if they do nothing.

## Locations

## Villain & plan

## Rewards
"""

_FOLDERS = [  # (title, [(kind, title, text)])
    ("Campaign", [(NOTE, "Campaign Overview", OVERVIEW), (NOTE, "World Lore", LORE), (NOTE, "Random Tables", TABLES)]),
    (SESSIONS, [(NOTE, "Session 1", None)]),
    ("Adventures", [(PROSE, "First Adventure", ADVENTURE)]),
    ("Player Characters", []),
    ("NPCs", []),
    ("Locations", []),
    ("Factions", []),
    ("Items & Treasure", []),
    ("Maps & Relationships", [(BOARD, "Who Knows Whom", None)]),
]

# where "New Character" etc. land in a campaign: the folder named for the kind
KIND_FOLDERS = {CHARACTER: "NPCs", LOCATION: "Locations", FACTION: "Factions", ITEM: "Items & Treasure"}


def create_campaign(project: Project) -> None:
    """Fill a new, empty project with the campaign folders and starter documents."""
    folders = []
    for title, docs in _FOLDERS:
        folder = project.new_node(FOLDER, title)
        for kind, doc_title, text in docs:
            node = project.new_node(kind, doc_title)
            if kind == NOTE and title == SESSIONS:
                text = session_text(doc_title, "")
            if text is not None:
                project.write_text(node, text.replace("{name}", project.name))
            folder.children.append(node)
        folders.append(folder)
    trash = project.root.index(next(n for n in project.root if n.kind == "trash"))
    project.root[trash:trash] = folders
    project.save()


# --- sessions ------------------------------------------------------------------------


_NUMBER_RE = re.compile(r"^session\s+(\d+)\b", re.IGNORECASE)


def session_number(title: str) -> int | None:
    m = _NUMBER_RE.match(title.strip())
    return int(m.group(1)) if m else None


def sessions(nodes: list[Node]) -> list[Node]:
    """Session notes among `nodes` ("Session 3 – The Heist"), in number order."""
    found = [n for n in nodes if n.kind in (NOTE, PROSE) and session_number(n.title) is not None]
    return sorted(found, key=lambda n: session_number(n.title))


def next_title(nodes: list[Node]) -> str:
    numbers = [session_number(n.title) for n in sessions(nodes)]
    return f"Session {max(numbers, default=0) + 1}"


def section(text: str, heading: str) -> str:
    """The body of a "## heading" section of a Markdown note, without the heading."""
    m = re.search(rf"^#+\s*{re.escape(heading)}\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    rest = text[m.end():]
    end = re.search(r"^#{1,2}\s", rest, re.MULTILINE)
    return (rest[: end.start()] if end else rest).strip("\n")


def recap_from(previous: str) -> str:
    """What happened last time, from the previous session's play notes (hints left out)."""
    hint = SESSION_TEMPLATE.split(f"## {{play_notes}}\n", 1)[1].strip()
    notes = section(previous, PLAY_NOTES).replace(hint, "").strip()
    return notes


def session_text(title: str, previous: str = "") -> str:
    recap = recap_from(previous) if previous else ""
    return SESSION_TEMPLATE.format(
        title=title,
        recap=recap or "What happened last time — to read out at the start.",
        play_notes=PLAY_NOTES,
    )
