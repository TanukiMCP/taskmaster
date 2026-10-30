"""Taskmaster MCP server: runs a task as a composition of operations in dependency order."""

from __future__ import annotations

import argparse
import json
from functools import wraps
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import BeforeValidator, Field

from . import __version__
from .engine import (
    EngineError,
    Operation,
    OperationInput,
    Session,
    changed_inputs,
    compose as engine_compose,
    downstream,
    finish as engine_finish,
    new_session,
    ready,
    record as engine_record,
    revise as engine_revise,
    states,
    upstream,
)
from .library import INDEX, Library, load_library
from .store import Store

INSTRUCTIONS = """\
Taskmaster runs a task as a composition of operations, each building on the concrete results of the ones it needs. library('method') is the full working method.

1. start: the request, the concrete result it asks for, the value that makes that result worth having, and the starting information. You get a session_id; pass it to every later call. Other conversations may run their own sessions at the same time.
2. compose: derive the operations this task needs. Each has an id, the operations whose outputs it needs (listed before it), what it does for this task, and the concrete output it produces. For product or interface design work, read library('design') to choose a situation and scope, then adopt the ready composition from library('design/<situation>/<scope>').
3. Work the operation Taskmaster gives you, using the results it builds on and its guide. Announce it in chat first. When its output exists, call record with the output, how it still serves the value, and the assumptions it rests on. An operation can't be recorded until everything it needs is current.
4. When evidence shows an earlier output or assumption is wrong, call revise on that operation: everything built on it becomes stale and is redone or confirmed. When the work needs a missing operation or a different decomposition, call compose again with the reason.
5. When every operation is current, deliver the result and call finish with what was delivered, what was actually checked, and what remains limited.

next re-issues the current operation after an interruption or condensed context; without a session_id it lists recent sessions. Keep no other tasklist or tracking document: the composition lives in Taskmaster.
"""

COMPOSE_GUIDE = """\
Derive the operations this task needs from the request, the starting information, the result, and the value. Give each one:
- id: a short lowercase name.
- needs: the ids of the operations whose outputs it consumes, each listed before it. Leave out dependencies that aren't real.
- does: the specific work it does for this task and the questions it must answer.
- produces: the concrete output the operations after it use: a decision, a model, an artifact, or evidence, not another paragraph.
- guide (optional): a library reference whose text comes with the operation.
Then call compose(session_id, operations=[...]).

Ready compositions: for product or interface design work, read library('design') to choose a situation and scope, then library('design/<situation>/<scope>') and adopt its composition, writing each "does" for this task."""

mcp = MCPServer("taskmaster", instructions=INSTRUCTIONS, version=__version__)

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def lib() -> Library:
    return load_library()


def _json_list(value: Any) -> Any:
    """Some clients send arrays as JSON strings; accept both."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


SessionId = Annotated[str, Field(description="The session_id start returned")]
Operations = Annotated[
    list[OperationInput],
    BeforeValidator(_json_list),
    Field(description="The operations in an order where each comes after what it needs. When revising, an item with only an id keeps that operation as it is."),
]
Assumptions = Annotated[
    list[str] | None,
    BeforeValidator(_json_list),
    Field(description="Provisional assumptions this output rests on; if one fails, this operation is the one to revise"),
]


def _session(session_id: str) -> Session:
    try:
        session = store().load(session_id.strip())
    except ValueError:
        raise EngineError(f"Session '{session_id}' was made by an earlier version of Taskmaster and can't continue here. Start a new session.") from None
    if session is None:
        raise EngineError(f"No session '{session_id}'. Call next without a session_id to list recent sessions.")
    return session


def _header(session: Session) -> str:
    lines = [
        f"Session {session.id}: pass session_id='{session.id}' with every call.",
        f"Result to produce: {session.result}",
        f"Value to preserve: {session.value}",
    ]
    if session.starting:
        lines.append(f"Starting information: {session.starting}")
    return "\n".join(lines)


def overview(session: Session) -> str:
    state = states(session)
    candidates = ready(session, state)
    first = candidates[0].id if candidates else None
    marks = {"current": "✓", "stale": "↻", "open": "○"}
    lines = []
    for op in session.operations:
        needs = f" ← {', '.join(op.needs)}" if op.needs else ""
        label = state[op.id] + (", next" if op.id == first else "")
        lines.append(f"{'▶' if op.id == first else marks[state[op.id]]} {op.id}{needs} ({label})")
    done = sum(1 for s in state.values() if s == "current")
    return f"Operations, {done} of {len(state)} current:\n" + "\n".join(lines)


def _result_block(op: Operation) -> str:
    latest = op.result
    lines = [f"### {op.id} (v{latest.version})", latest.output]
    if latest.assumptions:
        lines.append("Assumptions: " + "; ".join(latest.assumptions))
    if latest.evidence:
        lines.append(f"Evidence: {latest.evidence}")
    return "\n".join(lines)


def render_next(library: Library, session: Session) -> str:
    """The operation to work on now, with everything it builds on."""
    if session.status == "finished":
        return _finished(session)
    if not session.operations:
        return f"{_header(session)}\n\nNo operations yet.\n\n{COMPOSE_GUIDE}"
    state = states(session)
    candidates = ready(session, state)
    if not candidates:
        return (
            f"All {len(session.operations)} operations are current.\n\n"
            f"Deliver the result: {session.result}\n\n"
            f"Then call finish(session_id='{session.id}', delivered=..., evidence=..., limitations=...): what was delivered and how to "
            "reach it; what was actually checked, that it works as built and separately that it achieves its purpose; and what remains limited."
        )
    op = candidates[0]
    revised = state[op.id] == "open" and op.result is not None
    label = "stale" if state[op.id] == "stale" else "revised" if revised else "open"
    parts = [f"# Next: {op.id} ({label})", _header(session)]

    this = [f"Does: {op.does}", f"Produces: {op.produces}"]
    this.append(f"Needs: {', '.join(op.needs)}" if op.needs else "Needs: nothing; it starts from the starting information.")
    built_on = downstream(session, op.id)
    if built_on:
        this.append(
            f"Built on it: {len(built_on)} later operation{'s' if len(built_on) != 1 else ''} ({', '.join(o.id for o in built_on)}). "
            "Give it effort in proportion to that and to how uncertain it is."
        )
    else:
        this.append("Built on it: nothing later; its output is the requested result.")
    parts += ["## This operation", "\n".join(this)]

    if state[op.id] == "stale":
        why = "; ".join(changed_inputs(session, op))
        parts += [
            "## Why it is stale",
            f"It was built on inputs that have changed: {why}. Its earlier output is below. Record a new output, or confirm the earlier one with still_holds if it holds against the changed inputs.",
            _result_block(op),
        ]
    elif revised:
        note = next((n.text for n in reversed(op.notes) if n.text.startswith(("Revised", "Reopened"))), "")
        parts += ["## Why it is open again", f"{note}\nIts previous output is below.", _result_block(op)]

    built_from = upstream(session, op.id)
    if built_from:
        parts += ["## Working state it builds on", "\n\n".join(_result_block(o) for o in built_from)]

    if op.guide:
        parts += [f"## Guide: {op.guide}", library.read(op.guide) or "This guide reference no longer names anything in the library."]

    now = [
        f"Say in chat what '{op.id}' will establish for this task, then do the work.",
        f"When its output exists, call record(session_id='{session.id}', operation='{op.id}', output=..., preserves=..., assumptions=[...], evidence=...).",
    ]
    if op.result is not None:
        now.append(f"If the earlier output still holds, call record(session_id='{session.id}', operation='{op.id}', still_holds='why').")
    now.append(
        "If the work shows an earlier output or assumption is wrong, call revise on that operation. If it shows a missing operation "
        "or a better decomposition, call compose with the change and the reason."
    )
    others = [o.id for o in candidates[1:]]
    if others:
        now.append(f"Also ready, and recordable in any order: {', '.join(others)}.")
    parts += ["## Now", "\n".join(now)]
    return "\n\n".join(parts)


def _finished(session: Session) -> str:
    lines = [f"Session {session.id} is finished.", f"Delivered: {session.delivered}", f"Evidence: {session.evidence}"]
    if session.limitations:
        lines.append(f"Limitations: {session.limitations}")
    return "\n".join(lines)


def _guarded(func):
    """Turn engine errors into plain guidance for the agent."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except EngineError as error:
            return f"Not done: {error}"

    return wrapper


@mcp.tool(structured_output=False)
@_guarded
def start(
    request: Annotated[str, Field(description="The user's words")],
    result: Annotated[str, Field(description="The concrete result the request asks for")],
    value: Annotated[str, Field(description="What makes that result worth having: the purpose, appeal, or experience every operation must preserve")],
    starting: Annotated[str, Field(description="The starting information: what exists, constraints, conditions, and available evidence")] = "",
) -> str:
    """Start a session and receive its session_id and the working method. Then derive the operations and call compose."""
    session = new_session(request, result, value, starting)
    store().save(session)
    return "\n\n".join([
        f"Session {session.id} started. Pass session_id='{session.id}' with every call for this work.",
        "# Working method (library('method'); read it once and keep it as the authority)",
        lib().method,
        "# Now: derive the composition",
        COMPOSE_GUIDE,
    ])


@mcp.tool(structured_output=False)
@_guarded
def compose(
    session_id: SessionId,
    operations: Operations,
    reason: Annotated[str, Field(description="Required when revising: what the work showed that changes the composition")] = "",
) -> str:
    """Set the session's operations, or revise them. Operations kept unchanged keep their results; a recorded operation whose needs or output change is reopened; one left out is retired."""
    session = _session(session_id)
    library = lib()
    for item in operations:
        if item.guide.strip() and library.read(item.guide) is None:
            raise EngineError(f"'{item.id}' has guide '{item.guide}', which names nothing in the library. library() lists the references.")
    revising = bool(session.operations)
    reopened, warnings = engine_compose(session, operations, reason)
    store().save(session)
    head = f"Composition revised: {reason.strip()}" if revising else f"Composition recorded: {len(session.operations)} operations."
    if reopened:
        head += f"\nReopened: {', '.join(reopened)}."
    return "\n\n".join([head, *warnings, overview(session), render_next(library, session)])


@mcp.tool(name="next", structured_output=False)
@_guarded
def next_operation(session_id: Annotated[str, Field(description="The session_id; leave empty to list recent sessions")] = "") -> str:
    """Show where a session stands and re-issue the operation to work on now, with the results it builds on. Use after an interruption or condensed context."""
    if not session_id.strip():
        recent = store().recent()
        if not recent:
            return "No sessions yet. Call start."
        return "Recent sessions (pass one as session_id):\n" + "\n".join(f"- {s.id} [{s.status}] {s.request[:80]}" for s in recent)
    session = _session(session_id)
    if not session.operations or session.status == "finished":
        return render_next(lib(), session)
    return f"{overview(session)}\n\n{render_next(lib(), session)}"


@mcp.tool(structured_output=False)
@_guarded
def record(
    session_id: SessionId,
    operation: Annotated[str, Field(description="The operation's id")],
    output: Annotated[str, Field(description="The actual output: the concrete result the operation produces")] = "",
    preserves: Annotated[str, Field(description="How this output still serves the session's value")] = "",
    assumptions: Assumptions = None,
    evidence: Annotated[str, Field(description="Sources, observations, or checks that support the output")] = "",
    still_holds: Annotated[str, Field(description="For a stale or revised operation: why its earlier output still holds against the changed inputs. Leaves the operations built on it current.")] = "",
) -> str:
    """Record an operation's output and receive the next operation. Refused while anything it needs is missing or stale."""
    session = _session(session_id)
    outcome = engine_record(session, operation, output, preserves, assumptions, evidence, still_holds)
    store().save(session)
    op = session.operation(operation)
    head = f"Confirmed '{op.id}' v{op.version} still holds." if outcome == "confirmed" else f"Recorded '{op.id}' v{op.version}."
    return f"{head}\n\n{render_next(lib(), session)}"


@mcp.tool(structured_output=False)
@_guarded
def revise(
    session_id: SessionId,
    reason: Annotated[str, Field(description="The observation that undermines the output or assumption")],
    operation: Annotated[str, Field(description="The operation to reopen")] = "",
    value: Annotated[str, Field(description="A new value, only when evidence requires changing the purpose itself")] = "",
    result: Annotated[str, Field(description="A new requested result, only when evidence requires changing it")] = "",
) -> str:
    """Reopen an operation whose output or assumption no longer holds; everything built on it becomes stale. Or, with value or result, change the purpose explicitly; every recorded operation becomes stale."""
    session = _session(session_id)
    stale = engine_revise(session, reason, operation, value, result)
    store().save(session)
    head = f"Reopened '{operation.strip()}'." if operation.strip() else "Purpose changed."
    head += f" Now stale: {', '.join(stale)}." if stale else " Nothing else was built on it yet."
    return f"{head}\n\n{overview(session)}\n\n{render_next(lib(), session)}"


@mcp.tool(structured_output=False)
@_guarded
def finish(
    session_id: SessionId,
    delivered: Annotated[str, Field(description="What was delivered and how to reach or use it")],
    evidence: Annotated[str, Field(description="What was actually checked: that it works as built, and separately that it achieves its purpose")],
    limitations: Annotated[str, Field(description="What remains limited or unchecked; required when operations are not current")] = "",
) -> str:
    """Close the session with the delivered result, its evidence, and its remaining limitations."""
    session = _session(session_id)
    unfinished = engine_finish(session, delivered, evidence, limitations)
    store().save(session)
    text = _finished(session)
    if unfinished:
        text += f"\nNot current when it closed: {', '.join(unfinished)}."
    return text


@mcp.tool(structured_output=False)
@_guarded
def library(ref: Annotated[str, Field(description="A library reference, such as method, design, design/redesign/page, or design/process/5; empty lists them")] = "") -> str:
    """Read the library: the working method, the design matrix, a design entry's ready composition, or one procedure step."""
    text = lib().read(ref)
    if text is None:
        raise EngineError(f"'{ref}' names nothing in the library.\n\n{INDEX}")
    return text


@mcp.resource("taskmaster://method", mime_type="text/plain")
def method_resource() -> str:
    """The working method Taskmaster runs."""
    return lib().method


@mcp.resource("taskmaster://design/process", mime_type="text/plain")
def process_resource() -> str:
    """The full design procedure."""
    return lib().procedure.full_text


@mcp.resource("taskmaster://design/matrix", mime_type="text/plain")
def matrix_resource() -> str:
    """The design library's scope and situation matrix."""
    return lib().matrix


@mcp.prompt()
def run(request: str) -> str:
    """Run a request through Taskmaster."""
    return (
        f"Use Taskmaster for this request: {request}\n\n"
        "Call start with the request, the concrete result it asks for, the value that makes that result worth having, and the "
        "starting information. Derive the operations and call compose (for design work, adopt a ready composition from "
        "library('design')). Then work each operation Taskmaster gives you and record its actual output before the next."
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="taskmaster", description="Taskmaster MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--version", action="version", version=f"taskmaster {__version__}")
    args = parser.parse_args()
    load_library()  # fail fast if the library files are missing or malformed
    if args.transport == "streamable-http":
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
