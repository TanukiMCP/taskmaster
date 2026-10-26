"""Taskmaster MCP server: design-based execution driven by the scope and situation matrix."""

from __future__ import annotations

import argparse
import json
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BeforeValidator, Field

from . import __version__
from .engine import (
    EngineError,
    EntryInput,
    Session,
    add_entries as engine_add_entries,
    complete_step as engine_complete_step,
    end_session as engine_end_session,
    mode_for,
    new_session,
    report_verification as engine_report_verification,
)
from .library import FIRST_STEP, SCOPES, SITUATIONS, VERIFY_STEP, Library, load_library
from .store import Store

INSTRUCTIONS = """\
Taskmaster runs design work as a sequence of prompts chosen from the scope and situation matrix.

1. Call get_matrix. Choose each situation with its selector questions and the smallest scope that contains every decision to change.
2. Work backward from the end goal: list the matrix entries, in order, that get from the current state to the goal. One entry per situation × scope; "redesign the landing page and add a pricing page" is improve × page, then extend × page.
3. Call start_session with the request, the end goal, and those entries. Taskmaster replies with a session_id, the procedure's working method, and the first step. Pass that session_id to every later call; other conversations may be running their own sessions at the same time.
4. Execute exactly the step you are given, using its full text as the authority. Announce it in chat first. When its result exists, call complete_step with a one-to-three sentence handoff naming the actual result.
5. Step 10 ends with report_verification: 'done', or the number of the step responsible for a discrepancy. Taskmaster reruns from that step.
6. current_step re-issues the step after an interruption or condensed context. get_status shows the whole plan; called without a session_id it lists recent sessions so a lost id can be found again.

Do not keep your own tasklist or tracking document for this work; Taskmaster holds the sequence.
"""

mcp = MCPServer("taskmaster", instructions=INSTRUCTIONS, version=__version__)

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def library() -> Library:
    return load_library()


def _json_list(value: Any) -> Any:
    """Some clients send arrays as JSON strings; accept both."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


Entries = Annotated[
    list[EntryInput],
    BeforeValidator(_json_list),
    Field(description="Ordered matrix entries, each {situation, scope, goal}"),
]


SessionId = Annotated[str, Field(description="The session_id start_session returned")]


def _session(session_id: str) -> Session:
    session = store().load(session_id.strip())
    if session is None:
        raise EngineError(f"No session '{session_id}'. Call get_status without a session_id to list recent sessions.")
    return session


def _recent() -> str:
    recent = store().recent()
    if not recent:
        return "No sessions yet. Call get_matrix, then start_session."
    lines = [f"- {s.id} [{s.status}] {s.request[:80]}" for s in recent]
    return "Recent sessions (pass one as session_id):\n" + "\n".join(lines)


def _plan(session: Session) -> str:
    lines = []
    for i, entry in enumerate(session.entries, 1):
        marker = {"done": "✓", "active": "▶", "pending": "·"}[entry.status]
        where = ""
        if entry.status == "active" and entry.step is not None:
            phase = " (diagnosis)" if entry.phase == "diagnosis" else ""
            where = f" — step {entry.step}{phase}, pass {entry.iteration}"
        lines.append(f"{marker} {i}. {entry.label}: {entry.goal}{where}")
    return "\n".join(lines)


def _entry_briefing(lib: Library, session: Session) -> str:
    entry = session.entry
    situation = lib.situations[entry.situation]
    scope = lib.scopes[entry.scope]
    parts = [
        f"# Entry {session.current + 1} of {len(session.entries)}: {entry.label}",
        f"Entry goal: {entry.goal}",
        "## Situation",
        situation.header,
    ]
    if situation.completion:
        parts.append(f"Completion: {situation.completion}")
    parts += ["## Scope", scope.header]
    if scope.expansion:
        parts.append(f"Expansion: {scope.expansion}")
    return "\n\n".join(parts)


def render_step(lib: Library, session: Session, *, briefing: bool = False, preamble: bool = False) -> str:
    entry = session.entry
    if entry is None:
        return _closing(session)
    step = lib.procedure.steps[entry.step]
    situation = lib.situations[entry.situation]
    scope = lib.scopes[entry.scope]
    mode = mode_for(lib, entry, entry.step)

    parts: list[str] = []
    if preamble:
        parts += ["# Working method (process.txt, read once and keep as the authority)", lib.procedure.preamble]
    if briefing:
        parts.append(_entry_briefing(lib, session))

    parts.append(f"# Step {entry.step}: {step.name} — {mode}")
    context = [
        f"Session ID: {session.id} (pass session_id='{session.id}' with every call)",
        f"Session end goal: {session.end_goal}",
        f"Entry {session.current + 1} of {len(session.entries)}: {entry.label} — {entry.goal}",
    ]
    if session.conditions:
        context.append(f"Task conditions: {session.conditions}")
    if entry.iteration > 1 and entry.k is not None:
        context.append(f"Pass {entry.iteration}: rerunning from step {entry.k} after verification. Results before step {entry.k} are reused unchanged.")
    parts.append("\n".join(context))

    if entry.phase == "diagnosis":
        parts += [f"## Diagnosis ({situation.title})", situation.diagnosis]
    else:
        parts += [f"## Situation rule ({situation.title}, step {entry.step})", situation.rule_for(entry.step, entry.k) or "Follow the situation's permissions."]
    parts += [f"## Scope limit ({scope.title}, step {entry.step})", scope.limits[entry.step]]

    earlier = entry.latest_handoffs(before=entry.step)
    if earlier:
        lines = [f"- Step {n} ({lib.procedure.steps[n].name}): {h.text}" for n, h in earlier.items()]
        parts += ["## Earlier results in this entry", "\n".join(lines)]
    last = entry.verifications[-1] if entry.verifications else None
    if last and last.findings and entry.phase == "chain":
        parts += ["## Latest verification findings", last.findings]

    parts += [f"## Procedure step {entry.step} (verbatim)", step.text]

    if entry.step == VERIFY_STEP:
        finish = (
            "Finish with report_verification: outcome 'done' when nothing remains to correct, "
            "or the number (0–9) of the step responsible for the earliest discrepancy, with findings naming the evidence."
        )
        if entry.situation == "review":
            finish = "Finish with report_verification(outcome='done', findings=...) listing each finding with its evidence, responsible step, and recommended change."
        elif entry.phase == "diagnosis":
            finish = (
                "Finish with report_verification: the number (0–9) of the responsible step to rerun from, with findings "
                "listing each discrepancy and its step. Report 'done' only if nothing needs to change."
            )
    else:
        finish = "When this step's result exists, call complete_step with a short handoff naming the actual result and how the next step uses it."
    parts += [
        "## Now",
        f'Announce: "I\'m on step {entry.step}: {step.name}, {mode}. This step requires [operation]. For this assignment, I\'ll [specific action]."',
        finish,
    ]
    return "\n\n".join(p for p in parts if p)


def _closing(session: Session) -> str:
    if session.status == "complete":
        return (
            f"All {len(session.entries)} entries are done for session {session.id}.\n\n{_plan(session)}\n\n"
            f"Deliver the result as the final situation's completion describes, then call end_session(session_id='{session.id}') "
            "with a summary. Use add_entries if more work is needed."
        )
    return f"Session {session.id} is {session.status}."


def _guarded(func):
    """Turn engine and library errors into plain guidance for the agent."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except EngineError as error:
            return f"Not done: {error}"

    return wrapper


@mcp.tool(structured_output=False)
def get_matrix() -> str:
    """Return the scope and situation matrix with its selector questions. Call this before start_session."""
    lib = library()
    keys = (
        "Situation values: " + ", ".join(f"{k} ({v})" for k, v in SITUATIONS.items()) + "\n"
        "Scope values: " + ", ".join(f"{k} ({v})" for k, v in SCOPES.items())
    )
    return f"{lib.matrix}\n\n{keys}"


@mcp.tool(structured_output=False)
@_guarded
def start_session(request: str, end_goal: str, entries: Entries, task_conditions: str = "") -> str:
    """Start a design session and receive its session_id and first step.

    request: the user's words. end_goal: the observable condition that holds when the work is complete.
    entries: the matrix entries in the order they will run, worked backward from the end goal.
    task_conditions: device, platform, audience, existing identity, available assets, stage of completion,
    and whether identity is open to change.
    """
    session = new_session(request, end_goal, entries, task_conditions)
    store().save(session)
    header = (
        f"Session {session.id} started. Pass session_id='{session.id}' with every call for this work.\n\n"
        f"Plan:\n{_plan(session)}"
    )
    return header + "\n\n" + render_step(library(), session, briefing=True, preamble=True)


@mcp.tool(structured_output=False)
@_guarded
def current_step(session_id: SessionId) -> str:
    """Re-issue the session's current step with its full text, rules, and earlier results. Use after an interruption or condensed context."""
    return render_step(library(), _session(session_id), briefing=True)


@mcp.tool(structured_output=False)
@_guarded
def complete_step(session_id: SessionId, handoff: str = "") -> str:
    """Finish the current step (not step 10) and receive the next one.

    handoff: one to three sentences naming the actual result and how the next step uses it.
    """
    session = _session(session_id)
    engine_complete_step(session, handoff)
    store().save(session)
    return render_step(library(), session)


@mcp.tool(structured_output=False)
@_guarded
def report_verification(session_id: SessionId, outcome: str, findings: str = "") -> str:
    """Finish step 10.

    outcome: 'done', or the number (0–9) of the step responsible for the earliest discrepancy.
    findings: each discrepancy with its evidence and responsible step, or what was checked when done.
    """
    session = _session(session_id)
    previous_index = session.current
    result = engine_report_verification(session, outcome, findings)
    store().save(session)
    if result == "rerun":
        return render_step(library(), session)
    finished = session.entries[previous_index]
    if session.status == "complete":
        return f"{finished.label} is done.\n\n" + _closing(session)
    return f"{finished.label} is done.\n\nPlan:\n{_plan(session)}\n\n" + render_step(library(), session, briefing=True)


@mcp.tool(structured_output=False)
@_guarded
def add_entries(session_id: SessionId, entries: Entries, position: Literal["next", "end"] = "next") -> str:
    """Add matrix entries to a session's plan, after the current entry ('next') or at the end.

    Use when the work needs another entry, such as a Fix or Improve the user authorized after a Review.
    """
    session = _session(session_id)
    was_complete = session.status == "complete"
    engine_add_entries(session, entries, position)
    store().save(session)
    text = f"Plan updated:\n{_plan(session)}"
    if was_complete:
        text += "\n\n" + render_step(library(), session, briefing=True)
    return text


@mcp.tool(structured_output=False)
@_guarded
def get_status(session_id: str = "") -> str:
    """Show a session's goal, plan, position, and recorded results. Without a session_id, list recent sessions."""
    if not session_id.strip():
        return _recent()
    session = _session(session_id)
    lines = [
        f"Session {session.id} [{session.status}]",
        f"Request: {session.request}",
        f"End goal: {session.end_goal}",
    ]
    if session.conditions:
        lines.append(f"Task conditions: {session.conditions}")
    lines += ["", "Plan:", _plan(session)]
    lib = library()
    for i, entry in enumerate(session.entries, 1):
        if not entry.handoffs and not entry.verifications:
            continue
        lines += ["", f"Entry {i} results ({entry.label}):"]
        for handoff in entry.handoffs:
            lines.append(f"- pass {handoff.iteration}, step {handoff.step} {lib.procedure.steps[handoff.step].name}: {handoff.text}")
        for check in entry.verifications:
            lines.append(f"- pass {check.iteration}, {check.phase}: {check.outcome}" + (f" — {check.findings}" if check.findings else ""))
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guarded
def end_session(session_id: SessionId, summary: str = "") -> str:
    """End a session. summary: what was delivered and any remaining limitations."""
    session = _session(session_id)
    engine_end_session(session, summary)
    store().save(session)
    return f"Session {session.id} ended.\n\n{_plan(session)}"


@mcp.resource("taskmaster://design/process", mime_type="text/plain")
def process_resource() -> str:
    """The full design procedure."""
    return library().procedure.full_text


@mcp.resource("taskmaster://design/matrix", mime_type="text/plain")
def matrix_resource() -> str:
    """The scope and situation matrix."""
    return library().matrix


@mcp.resource("taskmaster://design/situations/{name}", mime_type="text/plain")
def situation_resource(name: str) -> str:
    """A situation prompt: create, extend, improve, fix, or review."""
    return library().situations[name].full_text


@mcp.resource("taskmaster://design/scopes/{name}", mime_type="text/plain")
def scope_resource(name: str) -> str:
    """A scope prompt: component, page, flow, shared-styles, or product."""
    return library().scopes[name].full_text


@mcp.prompt()
def design(request: str) -> str:
    """Run a design request through Taskmaster."""
    return (
        f"Use Taskmaster for this design request: {request}\n\n"
        "Call get_matrix, choose the matrix entries that get from the current state to the end goal, "
        "then call start_session and execute each step it gives you in order."
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="taskmaster", description="Taskmaster design execution MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--version", action="version", version=f"taskmaster {__version__}")
    args = parser.parse_args()
    load_library()  # fail fast if the design files are missing or malformed
    if args.transport == "streamable-http":
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
