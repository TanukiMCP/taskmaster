import pytest

from taskmaster.engine import (
    EngineError,
    EntryInput,
    add_entries,
    complete_step,
    current_sop_step,
    escalate,
    new_session,
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


def walk_to_verify(session):
    while current_sop_step(LIB, session.entry).kind != "verify":
        step = current_sop_step(LIB, session.entry)
        complete_step(LIB, session, f"result of {step.title}", responsible_step=3 if step.kind == "trace" else None)


def test_work_waits_for_a_plan_of_the_right_length():
    session = new_session("r", "g", [entry("create", "page")])
    with pytest.raises(EngineError, match="Write the plan first"):
        complete_step(LIB, session, "too early")
    with pytest.raises(EngineError, match="exactly 11"):
        submit_plan(LIB, session, ["only one"])
    assert submit_plan(LIB, session, plan_for(session)) is True
    assert session.entry.phase == "run" and session.entry.index == 0


def test_create_runs_every_sop_step_then_finishes():
    session = start("create", "product")
    titles = []
    while current_sop_step(LIB, session.entry).kind != "verify":
        titles.append(current_sop_step(LIB, session.entry).title)
        complete_step(LIB, session)
    assert len(titles) == 10
    assert report_verification(LIB, session, "done") == "done"
    assert session.status == "complete"


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
    complete_step(LIB, session, "problem stated")
    complete_step(LIB, session, "reproduced")
    with pytest.raises(EngineError, match="responsible_step"):
        complete_step(LIB, session, "traced")
    complete_step(LIB, session, "width from type", responsible_step=5)
    step = current_sop_step(LIB, session.entry)
    assert step.title == "Correct the cause" and step.resolve(session.entry.k) == [5]
    complete_step(LIB, session, "corrected")
    assert current_sop_step(LIB, session.entry).resolve(session.entry.k) == [6, 7, 8, 9]
    complete_step(LIB, session, "carried")
    report_verification(LIB, session, "3", "the control was the real cause")
    assert session.entry.k == 3 and current_sop_step(LIB, session.entry).title == "Correct the cause"


def test_review_never_loops_and_ends_with_findings():
    session = start("review", "section")
    walk_to_verify(session)
    with pytest.raises(EngineError, match="Review stops"):
        report_verification(LIB, session, "2")
    report_verification(LIB, session, "done", "the section should not exist")
    assert current_sop_step(LIB, session.entry).title == "Deliver the findings"
    complete_step(LIB, session, "findings delivered")
    assert session.status == "complete"


def test_escalate_replaces_the_entry_with_its_parent():
    session = start("redesign", "section")
    complete_step(LIB, session, "question stated")
    escalate(session, "the section should not exist; its claims belong to the ingredients", to_scope="page")
    assert session.entries[0].status == "escalated"
    assert session.entry.label == "Redesign × Page or view" and session.entry.phase == "plan"
    with pytest.raises(EngineError):
        escalate(session, "no target")


def test_entries_run_in_sequence_and_can_be_added():
    session = new_session("r", "g", [entry("review", "page"), entry("fix", "component")])
    submit_plan(LIB, session, plan_for(session))
    walk_to_verify(session)
    report_verification(LIB, session, "done", "findings")
    complete_step(LIB, session, "delivered")
    assert session.current == 1 and session.entry.situation == "fix" and session.entry.phase == "plan"
    add_entries(session, [entry("extend", "page")], "end")
    assert [e.situation for e in session.entries] == ["review", "fix", "extend"]


def test_store_round_trip(tmp_path):
    store = Store(tmp_path)
    session = start("create", "flow")
    complete_step(LIB, session, "question")
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.id == session.id and loaded.entry.index == 1
    assert loaded.entries[0].handoffs[0].text == "question"
    assert loaded.entries[0].plan == session.entries[0].plan
