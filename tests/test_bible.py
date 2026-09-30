from screenwriter.bible import (
    CHARACTER,
    BibleIndex,
    all_names,
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
    text = format_entry({"name": "Mara Quinn", "aliases": "MARA", "role": "", "backstory": "Line one\nline two"}, "Notes here.\n")
    assert text == "---\nname: Mara Quinn\naliases: MARA\nbackstory: Line one\n  line two\n---\n\nNotes here.\n"
    fields, notes = parse_entry(text)
    assert fields == {"name": "Mara Quinn", "aliases": "MARA", "backstory": "Line one\nline two"}
    assert notes == "\nNotes here.\n"
    assert parse_entry("just notes") == ({}, "just notes")
    assert entry_summary(format_entry({"name": "X", "description": "a keeper"}, "")) == "a keeper"


def test_script_names():
    assert script_names({"name": "Mara Quinn"}) == ["MARA QUINN", "MARA"]
    assert script_names({"name": "Owen", "aliases": "owen, skipper"}) == ["OWEN", "SKIPPER"]
    # adding another form never drops the name itself
    assert script_names({"name": "Kacper", "aliases": "Kacprowi"}) == ["KACPER", "KACPROWI"]
    assert script_names({"name": "Kacper Nowak", "aliases": "Kacpr*"}) == ["KACPER NOWAK", "KACPER", "KACPR*"]
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
        (CHARACTER, format_entry({"name": "Mara Quinn", "aliases": "MARA, KEEPER"}, "")),
        (CHARACTER, format_entry({"name": "Owen"}, "")),
        (LOCATION, format_entry({"name": "Lamp Room"}, "")),
    ]
    assert known_names(entries) == (["MARA", "KEEPER", "MARA QUINN", "OWEN"], ["LAMP ROOM"])


def test_report_finds_name_and_other_forms():
    fields = {"name": "Kacper", "aliases": "Kacprowi"}
    text = "Kacper przyszedł. Dałem to Kacprowi."
    report = character_report(script_names(fields), [("p", "Rozdział", "prose", text)])
    assert [text[a.pos : a.pos + a.length] for a in report.appearances] == ["Kacper", "Kacprowi"]


def test_legacy_script_names_key_becomes_aliases():
    fields, _ = parse_entry("---\nname: Mara\nscript names: MARA, KEEPER\n---\n")
    assert fields == {"name": "Mara", "aliases": "MARA, KEEPER"}
    assert "aliases: MARA, KEEPER" in format_entry(fields, "")


def test_location_prose_mentions():
    report = location_report(["Skerry Rock"], [("p", "Ch 1", "prose", "The light on Skerry Rock.\nskerry rock again")])
    assert len(report.appearances) == 2


def _index():
    from screenwriter.bible import BibleIndex

    return BibleIndex([
        ("k", CHARACTER, format_entry({"name": "Kacper", "aliases": "Kacpr*, Kacperek"}, "")),
        ("m", CHARACTER, format_entry({"name": "Mara Quinn", "description": "the keeper"}, "")),
        ("l", LOCATION, format_entry({"name": "Skerry Rock"}, "")),
        ("x", CHARACTER, format_entry({"name": ""}, "")),  # unnamed entries are ignored
    ])


def test_index_matches_inflected_forms():
    index = _index()
    text = "Dałem to Kacprowi. Kacperek i Kacper. Mara szła na Skerry Rock z Kacprem, a MARA QUINN patrzyła."
    found = [(m.group(0), e.node_id) for m, e in index.find(text)]
    assert found == [
        ("Kacprowi", "k"), ("Kacperek", "k"), ("Kacper", "k"), ("Mara", "m"),
        ("Skerry Rock", "l"), ("Kacprem", "k"), ("MARA QUINN", "m"),
    ]
    assert index.lookup("KACPRA").node_id == "k"
    assert index.lookup("Kac") is None
    assert "Kacpr*" not in index.completions() and "Mara Quinn" in index.completions()
    assert [(e.node_id, n) for e, n in index.cast(text)] == [("k", 4), ("m", 2), ("l", 1)]


def test_stem_alias_in_script_reports():
    report = character_report(["KACPR*"], [("p", "Rozdział", "prose", "Kacprowi było zimno.")])
    assert [a.label for a in report.appearances] == ["Kacprowi było zimno."]


def test_factions_and_items_are_found_in_writing():
    from screenwriter.bible import FACTION, ITEM, LABELS, report

    assert list(LABELS) == [CHARACTER, LOCATION, FACTION, ITEM]
    docs = [("p", "Session 3", "prose", "The Zhentarim want Dawnbringer.\nThe blade glows."), ("s", "Pilot", "screenplay", SCRIPT)]
    zhents = report(FACTION, ["Zhentarim"], docs)
    assert [(a.doc_id, a.line) for a in zhents.appearances] == [("p", 0)]
    blade = report(ITEM, all_names(parse_entry(format_entry({"name": "Dawnbringer", "aliases": "the blade"}, ""))[0], ITEM), docs)
    assert [a.line for a in blade.appearances] == [0, 1]
    index = BibleIndex([("z", FACTION, format_entry({"name": "Zhentarim"}, "")), ("d", ITEM, format_entry({"name": "Dawnbringer"}, ""))])
    assert sorted((e.kind, n) for e, n in index.cast(docs[0][3])) == [(FACTION, 1), (ITEM, 1)]
