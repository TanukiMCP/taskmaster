import pytest

from taskmaster.engine import (
    CAPTURE_WIDTHS,
    ConstraintInput,
    DropInput,
    EngineError,
    EntryInput,
    ResultInput,
    add_capture,
    add_entries,
    complete_step,
    current_sop_step,
    escalate,
    new_session,
    record_verdict,
    report_verification,
    sop_steps,
    submit_plan,
)
from taskmaster.library import load_library
from taskmaster.store import Store

LIB = load_library()


def entry(situation, scope, goal="goal"):
    return EntryInput(situation=situation, scope=scope, goal=goal)


def plan_for(session):
    return [f"plan for {s.title}" for s in sop_steps(LIB, session.entry)]


def start(situation, scope):
    session = new_session("request", "end goal", [entry(situation, scope)])
    submit_plan(LIB, session, plan_for(session))
    return session


def chained(session):
    """One result for the current step, citing the latest earlier result (or the request on the first step)."""
    earlier = [r.id for r in session.entry.results if r.sop_step < current_sop_step(LIB, session.entry).number]
    return [ResultInput(statement=f"result of {current_sop_step(LIB, session.entry).title}", based_on=earlier[-1:] or ["request"])]


def finish(session, responsible_step=None):
    complete_step(LIB, session, "handoff", responsible_step, chained(session))


def manifest(url="http://localhost/page", ok=True):
    return {"url": url, "widths": [{"width": w, "ok": ok, "page_height": 900, "page": {"file": f"{w}.jpg"}} for w in CAPTURE_WIDTHS]}


def walk_to_verify(session):
    while current_sop_step(LIB, session.entry).kind != "verify":
        finish(session, responsible_step=3 if current_sop_step(LIB, session.entry).kind == "trace" else None)


def make_ready(session):
    add_capture(session, "comparison", "reference", manifest("http://ref"), "taskmaster")
    add_capture(session, "result", "built", manifest(), "taskmaster")
    return report_verification(LIB, session, "ready", "measured heights")


def test_work_waits_for_a_plan_of_the_right_length():
    session = new_session("r", "g", [entry("create", "page")])
    with pytest.raises(EngineError, match="Write the plan first"):
        complete_step(LIB, session, "too early", None, [ResultInput(statement="x", based_on=["request"])])
    with pytest.raises(EngineError, match="exactly 11"):
        submit_plan(LIB, session, ["only one"])
    assert submit_plan(LIB, session, plan_for(session)) is True
    assert session.entry.phase == "run" and session.entry.index == 0


def test_constraints_count_only_with_the_users_words():
    request = "Redesign the sources tab but keep our existing typography as it is"
    session = new_session(request, "g", [entry("redesign", "section")], constraints=[ConstraintInput(constraint="Keep the type", quote="keep our existing typography")])
    assert session.constraints[0].id == "C1"
    with pytest.raises(EngineError, match="no quote from the request"):
        new_session(request, "g", [entry("redesign", "section")], constraints=[ConstraintInput(constraint="Keep the palette", quote="keep the palette")])
    with pytest.raises(EngineError, match="no quote from the request"):
        new_session(request, "g", [entry("redesign", "section")], constraints=[ConstraintInput(constraint="Keep the type", quote="typography")])


def test_each_step_needs_results_that_build_on_earlier_ones():
    session = start("create", "page")
    with pytest.raises(EngineError, match="handoff is required"):
        complete_step(LIB, session, "", None, [ResultInput(statement="q", based_on=["request"])])
    with pytest.raises(EngineError, match="results are required"):
        complete_step(LIB, session, "stated", None, [])
    with pytest.raises(EngineError, match="cites nothing"):
        complete_step(LIB, session, "stated", None, [ResultInput(statement="q")])
    complete_step(LIB, session, "stated", None, [ResultInput(statement="readers need the source", based_on=["request"])])
    assert session.entry.results[0].id == "1.1"
    with pytest.raises(EngineError, match="cites no earlier result"):
        complete_step(LIB, session, "content", None, [ResultInput(statement="c", based_on=["request"])])
    with pytest.raises(EngineError, match="not earlier results"):
        complete_step(LIB, session, "content", None, [ResultInput(statement="c", based_on=["9.9"])])
    complete_step(LIB, session, "content", None, [ResultInput(statement="c", based_on=["1.1"])])
    assert [r.id for r in session.entry.results] == ["1.1", "2.1"]


def test_ready_needs_every_result_used_and_fresh_captures():
    session = start("create", "page")
    complete_step(LIB, session, "q", None, [ResultInput(statement="unused", based_on=["request"]), ResultInput(statement="a", based_on=["request"])])
    walk_to_verify(session)
    with pytest.raises(EngineError, match="1.1 \\(unused\\)"):
        report_verification(LIB, session, "ready")
    with pytest.raises(EngineError, match="Capture the result first"):
        report_verification(LIB, session, "ready")
    assert report_verification(LIB, session, "4") == "rerun"
    complete_step(LIB, session, "h", None, chained(session), dropped=[DropInput(id="1.1", reason="covered by 1.2")])
    walk_to_verify(session)
    assert make_ready(session) == "ready"
    assert session.entry.awaiting_user


def test_only_the_users_verdict_marks_work_done():
    session = start("create", "product")
    walk_to_verify(session)
    add_capture(session, "result", "built", manifest(), "taskmaster")
    with pytest.raises(EngineError, match="compared with"):
        report_verification(LIB, session, "done")
    add_capture(session, "comparison", "ref", manifest("http://ref"), "taskmaster")
    assert report_verification(LIB, session, "done") == "ready"
    assert session.status == "active"
    with pytest.raises(EngineError, match="ready for the user's review"):
        report_verification(LIB, session, "ready")
    with pytest.raises(EngineError, match="ready for the user's review"):
        escalate(session, "x", to_scope="product")
    assert record_verdict(LIB, session, "done") == "done"
    assert session.status == "complete"


def test_the_user_returns_work_to_a_step_with_their_reason():
    session = start("create", "page")
    walk_to_verify(session)
    make_ready(session)
    with pytest.raises(EngineError, match="reason"):
        record_verdict(LIB, session, "return", 3)
    assert record_verdict(LIB, session, "return", 3, "looks like a google doc") == "return"
    step = current_sop_step(LIB, session.entry)
    assert step.title == "Name the jobs and port components" and session.entry.iteration == 2
    assert session.entry.verifications[-1].findings == "looks like a google doc"
    assert not session.entry.awaiting_user


def test_a_capture_that_failed_is_refused():
    session = start("create", "page")
    with pytest.raises(EngineError, match="failed at"):
        add_capture(session, "result", "built", manifest(ok=False), "taskmaster")
    with pytest.raises(EngineError, match="1440, 820, 390"):
        add_capture(session, "result", "built", {"url": "x", "widths": []}, "taskmaster")


def test_a_result_captured_before_the_last_change_is_stale():
    session = start("create", "page")
    walk_to_verify(session)
    add_capture(session, "comparison", "ref", manifest("http://ref"), "taskmaster")
    add_capture(session, "result", "built", manifest(), "taskmaster")
    session.entry.captures[-1].taken_at = "2000-01-01T00:00:00+00:00"
    with pytest.raises(EngineError, match="after the last change"):
        report_verification(LIB, session, "ready")


def test_verification_returns_to_the_sop_step_that_works_in_it():
    session = start("create", "page")
    walk_to_verify(session)
    assert report_verification(LIB, session, "6", "image loses its subject") == "rerun"
    step = current_sop_step(LIB, session.entry)
    assert step.title == "Produce the imagery" and session.entry.iteration == 2


def test_extend_returns_into_a_grouped_step_with_a_resume_point():
    session = start("extend", "page")
    walk_to_verify(session)
    report_verification(LIB, session, "5", "new label crowds the table")
    assert current_sop_step(LIB, session.entry).title == "Carry the foundations"
    assert session.entry.resume_at == 5


def test_fix_trace_sets_the_responsible_step():
    session = start("fix", "component")
    finish(session)
    finish(session)
    with pytest.raises(EngineError, match="responsible_step"):
        finish(session)
    finish(session, responsible_step=5)
    step = current_sop_step(LIB, session.entry)
    assert step.title == "Correct the cause" and step.resolve(session.entry.k) == [5]
    finish(session)
    assert current_sop_step(LIB, session.entry).resolve(session.entry.k) == [6, 7, 8, 9]
    finish(session)
    report_verification(LIB, session, "3", "the control was the real cause")
    assert session.entry.k == 3 and current_sop_step(LIB, session.entry).title == "Correct the cause"


def test_review_never_loops_and_ends_with_findings():
    session = start("review", "section")
    walk_to_verify(session)
    with pytest.raises(EngineError, match="Review stops"):
        report_verification(LIB, session, "2")
    report_verification(LIB, session, "done", "the section should not exist")
    assert current_sop_step(LIB, session.entry).title == "Deliver the findings"
    finish(session)
    assert session.status == "complete"


def test_escalate_goes_to_the_parent_only():
    session = start("redesign", "section")
    finish(session)
    with pytest.raises(EngineError, match="parent of section is: page"):
        escalate(session, "wrong place", to_scope="element")
    escalate(session, "the section should not exist; its claims belong to the ingredients", to_scope="page")
    assert session.entries[0].status == "escalated"
    assert session.entry.label == "Redesign × Page or view" and session.entry.phase == "plan"
    with pytest.raises(EngineError):
        escalate(session, "no target")


def test_a_review_does_not_escalate_into_changes():
    session = start("review", "page")
    with pytest.raises(EngineError, match="user's authorization"):
        escalate(session, "found problems", to_situation="fix")


def test_entries_run_in_sequence_and_can_be_added():
    session = new_session("r", "g", [entry("review", "page"), entry("fix", "component")])
    submit_plan(LIB, session, plan_for(session))
    walk_to_verify(session)
    report_verification(LIB, session, "done", "findings")
    finish(session)
    assert session.current == 1 and session.entry.situation == "fix" and session.entry.phase == "plan"
    add_entries(session, [entry("extend", "page")], "end")
    assert [e.situation for e in session.entries] == ["review", "fix", "extend"]


def test_store_round_trip(tmp_path):
    store = Store(tmp_path)
    session = start("create", "flow")
    finish(session)
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.id == session.id and loaded.entry.index == 1
    assert loaded.entries[0].handoffs[0].text == "handoff"
    assert loaded.entries[0].results[0].based_on == ["request"]
    assert loaded.entries[0].plan == session.entries[0].plan
