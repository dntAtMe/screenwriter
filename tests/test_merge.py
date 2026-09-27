import json

from screenwriter.merge import (
    BOTH,
    KEEP,
    THEIRS,
    ConflictRecord,
    dump_conflicts,
    merge_board,
    merge_conflict_lists,
    merge_text,
    resolve,
)

BASE = "One.\n\nTwo.\n\nThree.\n\nFour."


def test_one_side_changed_takes_it():
    assert merge_text(BASE, BASE, "x") == ("x", [])
    assert merge_text(BASE, "y", BASE) == ("y", [])
    assert merge_text(BASE, "z", "z") == ("z", [])


def test_different_paragraphs_combine():
    ours = BASE.replace("One.", "One, ours.")
    theirs = BASE.replace("Four.", "Four, theirs.")
    assert merge_text(BASE, ours, theirs) == ("One, ours.\n\nTwo.\n\nThree.\n\nFour, theirs.", [])


def test_insertions_and_deletions_combine():
    ours = BASE.replace("Two.\n\n", "")  # deleted a paragraph
    theirs = BASE + "\n\nFive."  # added one at the end
    text, clashes = merge_text(BASE, ours, theirs)
    assert text == "One.\n\nThree.\n\nFour.\n\nFive." and not clashes
    # both inserted in different places
    ours = BASE.replace("One.", "Zero.\n\nOne.")
    theirs = BASE.replace("Three.", "Three.\n\nThree and a half.")
    assert merge_text(BASE, ours, theirs)[0] == "Zero.\n\nOne.\n\nTwo.\n\nThree.\n\nThree and a half.\n\nFour."


def test_same_words_changed_clash_keeps_ours():
    ours = BASE.replace("Two.", "Deux.")
    theirs = BASE.replace("Two.", "Dwa.").replace("Four.", "Four, theirs.")
    text, [clash] = merge_text(BASE, ours, theirs)
    assert text == "One.\n\nDeux.\n\nThree.\n\nFour, theirs."  # the rest of theirs still comes in
    assert (clash.kept, clash.other, clash.base, clash.before) == ("Deux.", "Dwa.", "Two.", "")


def test_both_added_at_the_same_spot_keeps_both():
    ours = BASE.replace("Two.", "Two, ours.")
    theirs = BASE.replace("Two.", "Two, theirs.")
    assert merge_text(BASE, ours, theirs) == (BASE.replace("Two.", "Two, ours, theirs."), [])
    assert merge_text(BASE, ours, theirs, theirs_first=True)[0] == BASE.replace("Two.", "Two, theirs, ours.")
    # one side has only seen the other's typing half-way: the fuller one wins, nothing doubles
    assert merge_text("A.", "A the boat.", "A the bo.") == ("A the boat.", [])


def test_clash_where_we_deleted():
    ours = BASE.replace("Two.\n\n", "")
    theirs = BASE.replace("Two.", "Two, edited.")
    text, [clash] = merge_text(BASE, ours, theirs)
    assert clash.kept == "" and clash.other.strip() == "Two, edited."
    record = ConflictRecord("x", "docs/a.md", clash.kept, clash.other, clash.base, clash.before)
    restored = resolve(text, record, THEIRS)
    assert "Two, edited." in restored and restored.startswith("One.")


def test_resolve_choices():
    record = ConflictRecord("x", "docs/a.md", "Two, ours.", "Two, theirs.")
    text = "One.\n\nTwo, ours.\n\nThree."
    assert resolve(text, record, KEEP) == text
    assert resolve(text, record, THEIRS) == "One.\n\nTwo, theirs.\n\nThree."
    assert resolve(text, record, BOTH) == "One.\n\nTwo, ours.\n\nTwo, theirs.\n\nThree."
    assert resolve("Edited again since.", record, THEIRS) is None  # can't find the spot
    script = ConflictRecord("y", "docs/a.fountain", "Hi.", "Hello.")
    assert resolve("MARA\nHi.", script, BOTH) == "MARA\nHi.\nHello."


def board(*cards, links=()):
    return json.dumps({"cards": [dict(id=i, x=x, y=0, text=t) for i, x, t in cards],
                       "links": [{"a": a, "b": b} for a, b in links]})


def test_board_merges_card_by_card():
    base = board(("a", 0, "A"), ("b", 0, "B"), links=[("a", "b")])
    ours = board(("a", 50, "A"), ("b", 0, "B"), ("c", 0, "C"), links=[("a", "b"), ("a", "c")])  # moved a, added c
    theirs = board(("a", 0, "A, edited"), links=[])  # edited a, deleted b
    text, clashes = merge_board(base, ours, theirs)
    cards = {c["id"]: c for c in json.loads(text)["cards"]}
    assert not clashes
    assert set(cards) == {"a", "c"}
    assert (cards["a"]["x"], cards["a"]["text"]) == (50, "A, edited")
    assert [(l["a"], l["b"]) for l in json.loads(text)["links"]] == [("a", "c")]


def test_board_text_clash():
    base = board(("a", 0, "A"))
    text, [clash] = merge_board(base, board(("a", 0, "Ours")), board(("a", 0, "Theirs")))
    assert json.loads(text)["cards"][0]["text"] == "Ours"
    assert (clash.card, clash.kept, clash.other) == ("a", "Ours", "Theirs")
    record = ConflictRecord("x", "docs/m.board.json", clash.kept, clash.other, card=clash.card)
    assert json.loads(resolve(text, record, THEIRS))["cards"][0]["text"] == "Theirs"


def test_conflict_lists_merge_as_sets():
    a, b, c = (ConflictRecord(i, "docs/x.md", "k", "o") for i in "abc")
    base = dump_conflicts([a, b])
    ours = dump_conflicts([a, c])  # we resolved b, found c
    theirs = dump_conflicts([b])  # they resolved a
    assert {r.id for r in merge_conflict_lists(base, ours, theirs)} == {"c"}


def test_same_paragraph_different_sentences_combine():
    base = "Mara winds the clock. The boat is late. She waits."
    ours = "Mara winds the brass clock. The boat is late. She waits."
    theirs = "Mara winds the clock. The boat is late. She waits by the window."
    assert merge_text(base, ours, theirs) == ("Mara winds the brass clock. The boat is late. She waits by the window.", [])


def test_same_words_still_clash():
    base = "The boat is late."
    text, [clash] = merge_text(base, "The boat is early.", "The boat is gone.")
    assert text == "The boat is early." and clash.other == "The boat is gone."


def test_line_endings_dont_matter():
    base = "One.\r\n\r\nTwo.\r\n"
    assert merge_text(base, "One!\n\nTwo.\n", "One.\n\nTwo?\n") == ("One!\n\nTwo?\n", [])


def test_rebase_keeps_my_edits_and_theirs():
    from screenwriter.liveedit import rebase

    def apply(shared, edits):
        for start, end, text in reversed(edits):
            shared = shared[:start] + text + shared[end:]
        return shared

    head = "# T\n\nMara."
    # both added at the same spot before joining: both kept
    assert apply("# T b1\n\nMara.", rebase(head, "# T\n a1\nMara.", "# T b1\n\nMara.")) == "# T b1\n a1\nMara."
    # a lone space is still mine to add
    assert apply("Title", rebase("Title", " Title", "Title")) == " Title"
    # my deletion applies only where their text is untouched
    assert apply("one two three four", rebase("one two three", "one three", "one two three four")) == "one three four"
    # what already reached them another way isn't added twice
    assert apply("A b1 c.", rebase("A c.", "A b1 c.", "A b1 c.")) == "A b1 c."
