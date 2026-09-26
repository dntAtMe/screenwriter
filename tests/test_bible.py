from screenwriter.bible import (
    CHARACTER,
    LOCATION,
    character_report,
    entry_summary,
    format_entry,
    known_names,
    location_report,
    parse_entry,
    script_names,
)

SCRIPT = """INT. LAMP ROOM - NIGHT

Mara winds the clock. OWEN watches.

MARA
(quietly)
Right on time.

OWEN
Always is.

EXT. JETTY - DAY

MARA (V.O.)
Thursday. It's Thursday.
"""
PROSE = "Mara had kept the light.\nOwen came on Mondays; Mara didn't."


def test_entry_round_trip():
    text = format_entry({"name": "Mara Quinn", "script names": "MARA", "role": "", "backstory": "Line one\nline two"}, "Notes here.\n")
    assert text == "---\nname: Mara Quinn\nscript names: MARA\nbackstory: Line one\n  line two\n---\n\nNotes here.\n"
    fields, notes = parse_entry(text)
    assert fields == {"name": "Mara Quinn", "script names": "MARA", "backstory": "Line one\nline two"}
    assert notes == "\nNotes here.\n"
    assert parse_entry("just notes") == ({}, "just notes")
    assert entry_summary(format_entry({"name": "X", "description": "a keeper"}, "")) == "a keeper"


def test_script_names():
    assert script_names({"name": "Mara Quinn"}) == ["MARA QUINN", "MARA"]
    assert script_names({"name": "Owen", "script names": "owen, skipper"}) == ["OWEN", "SKIPPER"]
    assert script_names({"name": "Lamp Room"}, LOCATION) == ["LAMP ROOM"]
    assert script_names({}) == []


def test_character_report():
    docs = [("s", "Pilot", "screenplay", SCRIPT), ("p", "Chapter 1", "prose", PROSE)]
    report = character_report(["MARA QUINN", "MARA"], docs)
    assert report.speeches == 2
    assert report.words == 3 + 3  # "Right on time." + "Thursday. It's Thursday."
    assert len(report.scenes) == 2
    by_doc = report.by_document()
    pilot = by_doc[("s", "Pilot")]
    assert [a.speaks for a in pilot] == [False, True, True]  # mentioned in action, then two cues
    assert pilot[1].label == "INT. LAMP ROOM - NIGHT"
    assert SCRIPT[pilot[0].pos : pilot[0].pos + pilot[0].length] == "Mara"
    assert len(by_doc[("p", "Chapter 1")]) == 2
    assert PROSE[by_doc[("p", "Chapter 1")][1].pos :].startswith("Mara didn't")


def test_location_report():
    report = location_report(["JETTY"], [("s", "Pilot", "screenplay", SCRIPT)])
    assert [a.label for a in report.appearances] == ["EXT. JETTY - DAY"]


def test_known_names():
    entries = [
        (CHARACTER, format_entry({"name": "Mara Quinn", "script names": "MARA, KEEPER"}, "")),
        (CHARACTER, format_entry({"name": "Owen"}, "")),
        (LOCATION, format_entry({"name": "Lamp Room"}, "")),
    ]
    assert known_names(entries) == (["MARA", "KEEPER", "OWEN"], ["LAMP ROOM"])
