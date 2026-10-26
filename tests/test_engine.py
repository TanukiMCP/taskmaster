import pytest

from taskmaster.engine import (
    EngineError,
    EntryInput,
    add_entries,
    complete_step,
    mode_for,
    new_session,
    report_verification,
)
from taskmaster.library import load_library
from taskmaster.store import Store


def entry(situation, scope, goal="goal"):
    return EntryInput(situation=situation, scope=scope, goal=goal)


def walk_to_verify(session):
    while session.entry.step != 10:
        complete_step(session, f"result of step {session.entry.step}")


def test_create_runs_every_step_then_finishes():
    session = new_session("build an app", "the app works", [entry("create", "product")])
    seen = []
    while session.entry.step != 10:
        seen.append(session.entry.step)
        complete_step(session)
    assert seen == list(range(0, 10))
    assert report_verification(session, "done") == "done"
    assert session.status == "complete"


def test_verification_reruns_from_the_responsible_step():
    session = new_session("r", "g", [entry("create", "page")])
    walk_to_verify(session)
    assert report_verification(session, "6", "image loses its subject") == "rerun"
    assert session.entry.step == 6 and session.entry.iteration == 2
    walk_to_verify(session)
    assert report_verification(session, "done") == "done"


def test_improve_diagnoses_before_changing():
    session = new_session("redesign", "g", [entry("improve", "page")])
    complete_step(session, "question stated")
    assert session.entry.phase == "diagnosis" and session.entry.step == 10
    report_verification(session, "2", "order is wrong")
    assert session.entry.phase == "chain" and session.entry.step == 2
    walk_to_verify(session)
    assert report_verification(session, "done") == "done"


def test_fix_marks_later_steps_decide_or_keep():
    lib = load_library()
    session = new_session("fix overflow", "g", [entry("fix", "component")])
    complete_step(session)
    report_verification(session, "5", "width from type")
    assert mode_for(lib, session.entry, 5) == "decide"
    assert mode_for(lib, session.entry, 7) == "decide or keep"


def test_review_cannot_loop_into_implementation():
    session = new_session("audit", "g", [entry("review", "page")])
    walk_to_verify(session)
    with pytest.raises(EngineError):
        report_verification(session, "3")
    assert report_verification(session, "done", "findings") == "done"


def test_entries_run_in_sequence_and_can_be_added():
    session = new_session("r", "g", [entry("improve", "page"), entry("extend", "page")])
    complete_step(session)
    report_verification(session, "done")
    assert session.current == 1 and session.entry.situation == "extend"
    add_entries(session, [entry("fix", "component")], "end")
    walk_to_verify(session)
    report_verification(session, "done")
    assert session.entry.situation == "fix"


def test_step_ten_requires_report_verification():
    session = new_session("r", "g", [entry("create", "component")])
    walk_to_verify(session)
    with pytest.raises(EngineError):
        complete_step(session)


def test_extend_keeps_identity_steps():
    lib = load_library()
    session = new_session("add page", "g", [entry("extend", "page")])
    assert mode_for(lib, session.entry, 5) == "keep"
    assert mode_for(lib, session.entry, 3) == "decide"


def test_shared_styles_keeps_structure():
    lib = load_library()
    session = new_session("new type", "g", [entry("improve", "shared-styles")])
    complete_step(session)
    report_verification(session, "1")
    assert mode_for(lib, session.entry, 1) == "keep"
    assert mode_for(lib, session.entry, 5) == "decide or keep"


def test_store_round_trip(tmp_path):
    store = Store(tmp_path)
    session = new_session("r", "g", [entry("create", "flow")])
    complete_step(session, "question")
    store.save(session)
    loaded = store.load(session.id)
    assert loaded.id == session.id and loaded.entry.step == 1
    assert loaded.entries[0].handoffs[0].text == "question"
