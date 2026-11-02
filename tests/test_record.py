import pytest

import flow
from coherence import record as rec
from coherence.record import Answer, Entry, Opening, OrderInput, RecordError, Source, Work


def derived(*ids):
    return [Source(kind="derived", ref=",".join(ids))]


def to_review():
    r = rec.begin(flow.REQUEST, "idea", flow.QUESTIONS)
    rec.settle(r, "root", "decide", flow.root())
    rec.settle(r, "q1", "decide", flow.question())
    rec.settle(r, "first-board", "decide", flow.situation())
    rec.settle(r, "ui-kit", "decide", flow.family())
    rec.settle(r, "board", "decide", flow.job())
    rec.walk(r, flow.EXPERIENCE, flow.CONSTRUCTION)
    return r


def test_begin_opens_the_root_and_the_persons_questions():
    r = rec.begin(flow.REQUEST, "idea", flow.QUESTIONS)
    assert [p.id for p in rec.ready_points(r)] == ["root"]
    assert r.points["q1"].parents == ["root"] and r.points["q1"].kind == "question"
    with pytest.raises(RecordError, match="mode"):
        rec.begin("x", "maybe")


def test_the_root_must_quote_the_person_exactly():
    r = rec.begin(flow.REQUEST, "idea")
    bad = flow.root().model_copy(update={"sources": [Source(kind="user", quote="players win by luck")]})
    with pytest.raises(RecordError, match="not in the request"):
        rec.settle(r, "root", "decide", bad)
    research = flow.root().model_copy(update={"sources": [Source(kind="research", ref="https://example.org/a", quote="x")]})
    with pytest.raises(RecordError, match="root quotes the person"):
        rec.settle(r, "root", "decide", research)


def test_answers_need_every_question_in_the_right_form():
    r = rec.begin(flow.REQUEST, "idea")
    with pytest.raises(RecordError, match="average, decision"):
        rec.settle(r, "root", "decide", flow.root().model_copy(update={"average": "", "decision": " "}))
    with pytest.raises(RecordError, match="not a situation"):
        rec.settle(r, "root", "decide", flow.root().model_copy(update={"situation": "Cozy and intuitive."}))
    with pytest.raises(RecordError, match="excludes nothing"):
        rec.settle(r, "root", "decide", flow.root().model_copy(update={"excludes": []}))
    rec.settle(r, "root", "decide", flow.root())
    with pytest.raises(RecordError, match="average describing itself"):
        rec.settle(r, "first-board", "decide", flow.situation().model_copy(update={"sources": [Source(kind="work", ref="industry standard")]}))
    with pytest.raises(RecordError, match="evidence specific to this project"):
        rec.settle(r, "first-board", "decide", flow.situation().model_copy(update={"agrees_with_average": True}))
    with pytest.raises(RecordError, match="link it came from"):
        rec.settle(r, "first-board", "decide", flow.situation().model_copy(update={"sources": [Source(kind="research", ref="a blog", quote="x")]}))
    with pytest.raises(RecordError, match="not settled points"):
        rec.settle(r, "first-board", "decide", flow.situation().model_copy(update={"sources": derived("nowhere")}))


def test_points_wait_for_their_parents_and_families_need_work():
    r = rec.begin(flow.REQUEST, "idea")
    with pytest.raises(RecordError, match="No point"):
        rec.settle(r, "first-board", "decide", flow.situation())
    rec.settle(r, "root", "decide", flow.root())
    rec.settle(r, "first-board", "decide", flow.situation())
    with pytest.raises(RecordError, match="give work, or custom"):
        rec.settle(r, "ui-kit", "decide", flow.family().model_copy(update={"work": None}))
    with pytest.raises(RecordError, match="exact reference"):
        bad = flow.family().model_copy(update={"work": Work(chosen="the kenney one", license="CC0", examined=["x"], keep="a", change="b")})
        rec.settle(r, "ui-kit", "decide", bad)
    with pytest.raises(RecordError, match="Deferred entry"):
        rec.settle(r, "board", "decide", flow.job().model_copy(update={"manifest": [Entry(id="t", kind="deferred", value="1s")]}))


def test_gate_drop_and_consequence():
    r = rec.begin(flow.REQUEST, "idea")
    with pytest.raises(RecordError, match="can't be dropped"):
        rec.settle(r, "root", "drop", Answer(reason="r"))
    rec.settle(r, "root", "decide", flow.root().model_copy(update={"opens": [
        Opening(id="text-size", kind="job", question="How large is the rule text?"),
        Opening(id="mascot", kind="situation", question="Does the game need a mascot?")]}))
    rec.settle(r, "mascot", "drop", Answer(reason="Nothing the player does depends on a mascot."))
    assert rec.states(r)["mascot"] == "dropped"
    with pytest.raises(RecordError, match="rule"):
        rec.settle(r, "text-size", "consequence", Answer(sources=derived("root")))
    rec.settle(r, "text-size", "consequence", Answer(rule="Reading text at arm's length on a phone: 16 to 18 CSS pixels (Butterick)",
                                                      sources=derived("root"), manifest=[Entry(id="size.rule", kind="token", value="17px")]))
    assert r.manifest["size.rule"].owner == "text-size"


def test_the_walk_must_pass_through_every_point_and_gaps_reopen_derivation():
    r = rec.begin(flow.REQUEST, "idea", flow.QUESTIONS)
    for pid, answer in [("root", flow.root()), ("q1", flow.question()), ("first-board", flow.situation()),
                        ("ui-kit", flow.family()), ("board", flow.job())]:
        rec.settle(r, pid, "decide", answer)
    with pytest.raises(RecordError, match="skips 'first-board'"):
        rec.walk(r, "A player plays.", flow.CONSTRUCTION)
    with pytest.raises(RecordError, match="don't exist"):
        rec.walk(r, flow.EXPERIENCE + " [ghost]", flow.CONSTRUCTION)
    opened = rec.walk(r, flow.EXPERIENCE, flow.CONSTRUCTION, [Opening(id="losing", kind="situation", question="What happens on a loss?", parents=["first-board"])])
    assert opened == ["losing"] and r.phase == "derive"
    with pytest.raises(RecordError, match="Settle the open points"):
        rec.walk(r, flow.EXPERIENCE, flow.CONSTRUCTION)


def test_review_denial_reopens_only_what_it_touches():
    r = to_review()
    assert r.phase == "review"
    with pytest.raises(RecordError, match="reason and the points"):
        rec.decide(r, False, "")
    rec.decide(r, False, "The first board should be a garden, not a grid.", ["first-board"])
    state = rec.states(r)
    assert state["first-board"] == "open" and state["ui-kit"] == "stale" and state["board"] == "stale" and state["q1"] == "current"
    assert r.phase == "derive" and "garden" in r.points["first-board"].notes[-1]
    rec.settle(r, "first-board", "decide", flow.situation().model_copy(update={"opens": []}))
    rec.settle(r, "ui-kit", "decide", flow.family(), still_holds="The kit still carries a garden board.")
    rec.settle(r, "board", "decide", flow.job())
    rec.walk(r, flow.EXPERIENCE, flow.CONSTRUCTION)
    rec.decide(r, True)
    assert r.phase == "compile" and rec.approval_valid(r)


def test_compile_checks_coverage_dependencies_and_cycles():
    r = to_review()
    rec.decide(r, True)
    with pytest.raises(RecordError, match="no order realizes 'board'"):
        rec.compile_orders(r, flow.ORDERS[:1])
    with pytest.raises(RecordError, match="no order uses 'kit.ui'"):
        rec.compile_orders(r, [flow.ORDERS[0].model_copy(update={"uses": ["color.ink"]}), flow.ORDERS[1]])
    with pytest.raises(RecordError, match="list them in its after"):
        rec.compile_orders(r, [flow.ORDERS[0], flow.ORDERS[1].model_copy(update={"after": []})])
    loop = [flow.ORDERS[0].model_copy(update={"after": ["board"]}), flow.ORDERS[1]]
    with pytest.raises(RecordError, match="cycle"):
        rec.compile_orders(r, loop)
    rec.compile_orders(r, flow.ORDERS, ["styles/tokens.css"])
    assert r.phase == "build" and [o.id for o in rec.ready_orders(r)] == ["foundations"]
    assert rec.must_not(r, r.order("board")) == ["instant results", "unexplained moves", "tutorial pop-ups", "hidden rules", "random drops", "paid power-ups"]


def built():
    r = to_review()
    rec.decide(r, True)
    rec.compile_orders(r, flow.ORDERS, ["styles/tokens.css"])
    rec.complete(r, "foundations", "tokens", "loaded", {}, [])
    return r


def test_orders_need_their_deferred_values_and_a_clean_scan():
    r = built()
    with pytest.raises(RecordError, match="not ready"):
        rec.complete(r, "foundations", "again", "x", {}, [])
    with pytest.raises(RecordError, match="Set the deferred values"):
        rec.complete(r, "board", "board", "shown", {}, [])
    with pytest.raises(RecordError, match="did not come from the manifest"):
        from coherence.trace import Finding
        rec.complete(r, "board", "board", "shown", {"timing.reveal": ("240ms", "read in time")}, [Finding("src/board.js", 3, "#ff0000", "color")])
    rec.complete(r, "board", "board", "shown", {"timing.reveal": ("240ms", "a new player read each result before moving")}, [])
    assert r.phase == "verify" and r.manifest["timing.reveal"].value == "240ms"


def test_revising_a_job_reopens_its_order_without_the_person():
    r = built()
    rec.complete(r, "board", "board", "shown", {"timing.reveal": ("240ms", "read in time")}, [])
    stale = rec.revise(r, "board", "The pause hides the rule on small screens.")
    assert stale == [] and r.phase == "derive"
    rec.settle(r, "board", "decide", flow.job())
    assert r.phase == "build" and [o.id for o in rec.ready_orders(r)] == ["board"]
    assert r.manifest["timing.reveal"].value == ""  # observed again on the new build


def test_a_gap_at_the_approved_level_goes_back_to_the_person():
    r = built()
    with pytest.raises(RecordError, match="parents"):
        rec.gap(r, "board", Opening(id="undo", kind="job", question="Can a move be undone?"))
    rec.gap(r, "board", Opening(id="losing", kind="situation", question="What happens on a loss?", parents=["first-board"]))
    assert r.phase == "derive" and not rec.approval_valid(r)
    loss = flow.situation().model_copy(update={"opens": [], "situation": "A player whose move breaks the rule sees the board reset with the broken rule highlighted."})
    rec.settle(r, "losing", "decide", loss)
    assert r.phase == "derive"
    rec.walk(r, flow.EXPERIENCE + " A loss resets the board [losing].", flow.CONSTRUCTION)
    assert r.phase == "review"
    rec.decide(r, True)
    assert r.phase == "build"


def test_a_job_gap_attaches_to_its_order():
    r = built()
    rec.gap(r, "board", Opening(id="undo", kind="job", question="Can a move be undone?", parents=["first-board"]))
    undo = flow.job().model_copy(update={"manifest": [Entry(id="copy.undo", kind="content", value="Take back")]})
    rec.settle(r, "undo", "decide", undo)
    order = r.order("board")
    assert r.phase == "build" and "undo" in order.realizes and "copy.undo" in order.uses


def test_verify_needs_clean_traces_a_full_walk_and_a_review():
    r = built()
    rec.complete(r, "board", "board", "shown", {"timing.reveal": ("240ms", "read in time")}, [])
    with pytest.raises(RecordError, match="skips 'first-board'"):
        rec.verify(r, "It works.", "ran it", "a fresh agent", [])
    with pytest.raises(RecordError, match="review"):
        rec.verify(r, "[first-board] played it", "ran it", "", [])
    rec.verify(r, "[first-board] A new player read the rule and solved the board.", "ran it in a browser", "A fresh agent compared it with the shape", [])
    assert r.phase == "done"


def test_risk_ranks_uncertain_decisions_with_much_built_on_them():
    r = to_review()
    ranked = [p.id for _, p in rec.risk(r)]
    assert ranked[0] == "first-board" and "root" not in ranked
