import pytest

from screenwriter.fountain import (
    El,
    character_name,
    characters,
    classify,
    locations,
    normalize_transition,
    outline,
    parse,
    times_of_day,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("INT. KITCHEN - DAY", El.SCENE),
        ("ext. beach", El.SCENE),
        (".FLASHBACK", El.SCENE),
        ("@McCLANE", El.CHARACTER),
        ("MARA (40s, tired) winds the clock.", El.ACTION),
        ("CUT TO:", El.TRANSITION),
        ("FADE OUT.", El.TRANSITION),
        ("FADE IN:", El.ACTION),
        ("> THE END <", El.CENTERED),
        ("> BURN TO WHITE.", El.TRANSITION),
        ("# ACT ONE", El.SECTION),
        ("= Synopsis here", El.SYNOPSIS),
        ("[[a note]]", El.NOTE),
        ("She walks in.", El.ACTION),
        ("!SCREAMS", El.ACTION),
    ],
)
def test_classify_after_blank(text, expected):
    assert classify(text, El.BLANK) == expected


@pytest.mark.parametrize("cue", ["MARA", "MARA (V.O.)", "DR. WHO (cont'd)", "BOB ^"])
def test_cue_needs_dialogue_below(cue):
    assert classify(cue, El.BLANK, next_text="Hello.") == El.CHARACTER
    assert classify(cue, El.BLANK, next_text="") == El.ACTION
    assert classify(cue, El.BLANK, next_text=None) == El.ACTION


def test_cue_while_typing():
    assert classify("MA", El.BLANK, next_text="", editing=True) == El.CHARACTER
    assert classify("I", El.BLANK, next_text="", editing=True) == El.ACTION  # "I walk…" doesn't jump
    assert classify("BOOM!", El.BLANK, next_text="", editing=True) == El.ACTION
    assert classify("", El.BLANK, forced_cue=True) == El.CHARACTER


def test_parse_dialogue_block():
    assert [el for _, el in parse("MARA\n(quietly)\nHello.\n\nShe leaves.")] == [
        El.CHARACTER, El.PARENTHETICAL, El.DIALOGUE, El.BLANK, El.ACTION,
    ]


def test_caps_line_inside_action_is_action():
    assert [el for _, el in parse("She turns.\nBOOM")] == [El.ACTION, El.ACTION]


def test_character_name():
    assert character_name("@McCLANE (V.O.) ^") == "McCLANE"


@pytest.mark.parametrize(
    "typed, expected",
    [("cut to", "CUT TO:"), ("smash cut to:", "SMASH CUT TO:"), ("fade out", "FADE OUT."), ("fade in", "FADE IN:")],
)
def test_normalize_transition(typed, expected):
    assert normalize_transition(typed) == expected


SCRIPT = """# ACT ONE

INT. KITCHEN - DAY

MARA
Tea?

OWEN
Please.

## Night

EXT. BEACH - NIGHT

MARA
Look.

.FLASHBACK
"""


def test_structure():
    lines = parse(SCRIPT)
    assert [(i.kind, i.level, i.title, i.number) for i in outline(lines)] == [
        ("section", 0, "ACT ONE", 0),
        ("scene", 1, "INT. KITCHEN - DAY", 1),
        ("section", 1, "Night", 0),
        ("scene", 2, "EXT. BEACH - NIGHT", 2),
        ("scene", 2, "FLASHBACK", 3),
    ]
    assert characters(lines).most_common() == [("MARA", 2), ("OWEN", 1)]
    assert set(locations(lines)) == {"INT. KITCHEN", "EXT. BEACH", "FLASHBACK"}
    assert times_of_day(lines)[:2] in (["DAY", "NIGHT"], ["NIGHT", "DAY"])


def test_title_page():
    lines = parse("Title: THE LIGHTHOUSE\nCredit: written by\nAuthor: K. P.\nContact:\n    Somewhere\n    123\n\nEXT. SEA - DAY")
    assert [el for _, el in lines][:7] == [El.TITLE_PAGE] * 6 + [El.BLANK]
    assert lines[7][1] == El.SCENE
    from screenwriter.fountain import title_page

    assert title_page(lines) == {"title": "THE LIGHTHOUSE", "credit": "written by", "author": "K. P.",
                                 "contact": "Somewhere\n123"}


def test_title_key_mid_script_is_action():
    assert [el for _, el in parse("She reads.\n\nTitle: nothing")][-1] == El.ACTION
