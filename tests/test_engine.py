import pytest

from taskmaster.engine import (
    EngineError,
    OperationInput,
    Session,
    compose,
    downstream,
    finish,
    new_session,
    ready,
    record,
    revise,
    states,
    upstream,
)
from taskmaster.library import SCOPES, SITUATIONS, load_library
from taskmaster.store import Store

LIB = load_library()


def op(op_id, needs=(), does="work", produces="output", guide=""):
    return OperationInput(id=op_id, needs=list(needs), does=does, produces=produces, guide=guide)


def session_with(*ops):
    session = new_session("Make a game concept", "One playable concept", "Players feel clever, not lucky")
    compose(session, list(ops))
    return session


def game():
    # brief -> fantasy -> loop -> pitch, with a side branch: brief -> audience -> pitch
    return session_with(
        op("brief"),
        op("fantasy", ["brief"]),
        op("audience", ["brief"]),
        op("loop", ["fantasy"]),
        op("pitch", ["loop", "audience"]),
    )


def done(session, op_id, output="out"):
    return record(session, op_id, output=output, check="a playtester solved it without guessing")


def test_start_needs_request_result_and_value():
    with pytest.raises(EngineError, match="value"):
        new_session("r", "y", " ")


def test_compose_refuses_broken_dependencies():
    session = new_session("r", "y", "a")
    with pytest.raises(EngineError, match="at least one"):
        compose(session, [])
    with pytest.raises(EngineError, match="not a usable id"):
        compose(session, [op("Bad Id")])
    with pytest.raises(EngineError, match="appears twice"):
        compose(session, [op("a"), op("a")])
    with pytest.raises(EngineError, match="listed after it"):
        compose(session, [op("a", ["b"]), op("b")])
    with pytest.raises(EngineError, match="not in the composition"):
        compose(session, [op("a", ["ghost"])])
    with pytest.raises(EngineError, match="can't need itself"):
        compose(session, [op("a", ["a"])])
    with pytest.raises(EngineError, match="needs does"):
        compose(session, [op("a", does=" ")])
    with pytest.raises(EngineError, match="needs produces"):
        compose(session, [op("a", produces="")])
    assert session.operations == []


def test_compose_points_out_operations_nothing_uses():
    session = new_session("r", "y", "a")
    _, _, warnings = compose(session, [op("a"), op("stray"), op("b", ["a"])])
    assert len(warnings) == 1 and "'stray'" in warnings[0] and "'a'" not in warnings[0]


def test_an_operation_waits_for_current_inputs():
    session = game()
    assert [o.id for o in ready(session)] == ["brief"]
    with pytest.raises(EngineError, match="it needs 'brief', which is not current. Work on 'brief' first"):
        done(session, "fantasy")
    with pytest.raises(EngineError, match="Record the actual output of 'brief': output"):
        record(session, "brief", output=" ", check="c")
    with pytest.raises(EngineError, match="checked against the value: Players feel clever.*is not a check"):
        record(session, "brief", output="o")
    assert done(session, "brief") == "recorded"
    assert [o.id for o in ready(session)] == ["fantasy", "audience"]
    done(session, "audience")  # an independent branch can go first
    with pytest.raises(EngineError, match="already current"):
        done(session, "audience")


def test_upstream_and_downstream_follow_the_edges():
    session = game()
    assert [o.id for o in upstream(session, "loop")] == ["brief", "fantasy"]
    assert [o.id for o in downstream(session, "fantasy")] == ["loop", "pitch"]
    assert [o.id for o in downstream(session, "audience")] == ["pitch"]


def run_all(session):
    while ready(session):
        done(session, ready(session)[0].id)


def test_revise_stales_only_what_was_built_on_it():
    session = game()
    run_all(session)
    assert set(states(session).values()) == {"current"}

    stale = revise(session, "playtest: the fantasy reads as luck", "fantasy")
    assert stale == ["loop", "pitch"]
    assert states(session) == {"brief": "current", "fantasy": "open", "audience": "current", "loop": "stale", "pitch": "stale"}
    with pytest.raises(EngineError, match="already open"):
        revise(session, "again", "fantasy")
    with pytest.raises(EngineError, match="'fantasy', which is not current"):
        done(session, "loop")

    done(session, "fantasy", "a new fantasy")
    assert session.operation("fantasy").version == 2
    assert [o.id for o in ready(session)] == ["loop"]
    assert states(session)["pitch"] == "stale"


def test_a_confirmed_output_keeps_later_work_current():
    session = game()
    run_all(session)
    revise(session, "new evidence about the fantasy", "fantasy")
    done(session, "fantasy", "a sharper fantasy")
    with pytest.raises(EngineError, match="already current; there is nothing to confirm"):
        record(session, "brief", still_holds="x")
    with pytest.raises(EngineError, match="no earlier output"):
        record(session_with(op("x")), "x", still_holds="nothing to confirm")
    assert record(session, "loop", still_holds="the loop never depended on that detail") == "confirmed"
    assert session.operation("loop").version == 1
    assert set(states(session).values()) == {"current"}  # pitch stays current: loop did not change


def test_a_new_output_stales_what_was_built_on_it():
    session = game()
    run_all(session)
    revise(session, "loop is too slow", "loop")
    done(session, "loop", "a faster loop")
    assert states(session)["pitch"] == "stale"
    assert record(session, "pitch", output="a new pitch", check="c") == "recorded"


def test_changing_the_purpose_stales_everything_recorded():
    session = game()
    run_all(session)
    stale = revise(session, "the client wants co-op", value="Friends feel clever together")
    assert stale == ["brief", "fantasy", "audience", "loop", "pitch"]
    assert session.purpose == 2 and session.value == "Friends feel clever together"
    with pytest.raises(EngineError, match="one thing at a time"):
        revise(session, "r", "loop", value="v")
    with pytest.raises(EngineError, match="Name the operation"):
        revise(session, "r")


def test_recompose_keeps_reopens_and_retires_only_what_it_names():
    session = game()
    run_all(session)
    with pytest.raises(EngineError, match="Say why"):
        compose(session, [op("brief")])
    revised = [
        OperationInput(id="brief"),
        op("fantasy", ["brief"], does="reworded, same output"),
        op("loop", ["fantasy"], produces="a loop with a fail state"),
        op("pitch", ["loop"]),
    ]
    with pytest.raises(EngineError, match="'audience' is missing from the list"):
        compose(session, revised, reason="audience research is out of scope")
    with pytest.raises(EngineError, match="'ghost', which is not in the composition"):
        compose(session, revised, reason="r", remove=["ghost"])
    reopened, changes, _ = compose(session, revised, reason="audience research is out of scope", remove=["audience"])
    assert reopened == ["loop", "pitch"]
    assert [o.id for o in session.retired] == ["audience"]
    assert "'fantasy' does was: work\n  now: reworded, same output" in changes
    assert "'audience' removed; it produced: output" in changes
    assert session.operation("fantasy").does == "reworded, same output"
    assert states(session) == {"brief": "current", "fantasy": "current", "loop": "open", "pitch": "open"}
    assert "'audience' removed" in session.log[-1].text
    with pytest.raises(EngineError, match="is new"):
        compose(session, [OperationInput(id="ghost")], reason="r", remove=["brief", "fantasy", "loop", "pitch"])


def test_finish_needs_evidence_an_outside_review_and_names_what_is_unfinished():
    session = game()
    done(session, "brief")
    with pytest.raises(EngineError, match="actually checked"):
        finish(session, "a doc", " ", "reviewed")
    with pytest.raises(EngineError, match="Every operation passing is not a review"):
        finish(session, "a doc", "read it", " ")
    with pytest.raises(EngineError, match="'fantasy', 'audience', 'loop', 'pitch' are not current"):
        finish(session, "a doc", "read it", "a fresh agent found no hook")
    assert finish(session, "a doc", "read it", "a fresh agent found no hook", limitations="stopped at the brief") == [
        "fantasy", "audience", "loop", "pitch"]
    assert session.status == "finished"
    with pytest.raises(EngineError, match="is finished"):
        done(session, "fantasy")
    compose(session, [OperationInput(id=o.id) for o in session.operations], reason="the user wants the rest")
    assert session.status == "active"


def test_the_users_questions_each_need_an_answer():
    session = new_session("How do players progress? Make a puzzle game.", "One concept", "Players feel clever",
                          questions=["How do players progress?", " "])
    assert session.questions == ["How do players progress?"]
    compose(session, [op("concept")])
    done(session, "concept")
    with pytest.raises(EngineError, match=r"1\. How do players progress\?\): answers needs 1 items"):
        finish(session, "a doc", "read it", "the user reviewed it")
    finish(session, "a doc", "read it", "the user reviewed it", answers=["Unlocking new rule sets"])
    assert session.answers == ["Unlocking new rule sets"]


@pytest.mark.parametrize("situation", SITUATIONS)
@pytest.mark.parametrize("scope", SCOPES)
def test_every_design_composition_runs_to_the_end(situation, scope):
    session = new_session("design request", "the designed work", "people can do what they came for")
    items = [OperationInput(**{**item, "does": f"do {item['id']} for this page"}) for item in LIB.composition(situation, scope)]
    _, _, warnings = compose(session, items)
    assert warnings == []
    run_all(session)
    assert set(states(session).values()) == {"current"}


def test_sessions_round_trip_through_the_store(tmp_path):
    store = Store(tmp_path)
    session = game()
    run_all(session)
    revise(session, "r", "loop")
    store.save(session)
    loaded = store.load(session.id)
    assert isinstance(loaded, Session) and states(loaded) == states(session)
    assert [s.id for s in store.recent()] == [session.id]
