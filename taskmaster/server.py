"""Taskmaster MCP server: design-based execution driven by the scope and situation matrix."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BeforeValidator, Field

from . import __version__
from .engine import (
    CAPTURE_WIDTHS,
    CaptureKind,
    ConstraintInput,
    DropInput,
    EngineError,
    Entry,
    EntryInput,
    ResultInput,
    Scope,
    Session,
    Situation,
    add_capture,
    add_entries as engine_add_entries,
    complete_step as engine_complete_step,
    current_sop_step,
    end_session as engine_end_session,
    escalate as engine_escalate,
    latest_results,
    new_session,
    record_verdict,
    report_verification as engine_report_verification,
    sop_steps,
    submit_plan as engine_submit_plan,
)
from .library import SCOPES, SITUATIONS, VERIFY_STEP, Library, SopStep, load_library
from .store import Store

INSTRUCTIONS = """\
Taskmaster runs design work as standard operating procedures chosen from the scope and situation matrix. process.txt is the fixed design procedure; each situation has an SOP that sets the working path through it, and each scope sets how far the work reaches.

1. Call get_matrix. Choose each situation with its selector questions and the smallest scope that contains every decision to change.
2. Work backward from the end goal: list the matrix entries, in order, that get from the current state to the goal. "Redesign the landing page and add a pricing page" is redesign × page, then extend × page.
3. Call start_session with the user's request copied word for word, the end goal, and those entries. A constraint, such as keeping the existing identity, counts only with the user's own words quoted from the request. Taskmaster replies with a session_id, the working method, and the first entry's SOP and scope sheet. Pass that session_id to every later call; other conversations may run their own sessions at the same time.
4. Before any work, call submit_plan with one item per SOP step: the specific work you will do on this assignment, the questions you must answer, and the result that will show the step is complete.
5. Execute exactly the SOP step you are given, using the procedure text it includes as the authority. Announce it in chat first. When its result exists, call complete_step with a short handoff and the step's results, each citing the earlier results it builds on. Before a verify step finishes, capture the result and what it is compared with. Verify steps end with report_verification: 'ready' for the user's review, or the procedure step responsible for a discrepancy. Only the user marks work done.
6. When a step shows the decision belongs to a parent scope or another situation, call escalate instead of working around the boundary.
7. current_step re-issues the current step after an interruption or condensed context. get_status without a session_id lists recent sessions.

Do not keep your own tasklist or tracking document for this work; the plan lives in Taskmaster.
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
Constraints = Annotated[
    list[ConstraintInput],
    BeforeValidator(_json_list),
    Field(description="Constraints the user stated, each with the user's own words quoted from the request"),
]
Results = Annotated[
    list[ResultInput],
    BeforeValidator(_json_list),
    Field(description="This step's results, each {statement, based_on: [IDs of earlier results, constraints, or 'request']}"),
]
Drops = Annotated[
    list[DropInput],
    BeforeValidator(_json_list),
    Field(description="Earlier results no later step will use, each {id, reason}"),
]
PlanItems = Annotated[
    list[str],
    BeforeValidator(_json_list),
    Field(description="One item per SOP step, in order: the specific work, the questions to answer, and the result that shows the step is complete"),
]
SessionId = Annotated[str, Field(description="The session_id start_session returned")]


def _session(session_id: str) -> Session:
    session = store().load(session_id.strip())
    if session is None:
        raise EngineError(f"No session '{session_id}'. Call get_status without a session_id to list recent sessions.")
    return session


def _plan(lib: Library, session: Session) -> str:
    lines = []
    for i, entry in enumerate(session.entries, 1):
        marker = {"done": "✓", "active": "▶", "pending": "·", "escalated": "↑"}[entry.status]
        where = ""
        if entry.status == "active":
            total = len(sop_steps(lib, entry))
            where = " — writing the plan" if entry.phase == "plan" else f" — SOP step {entry.index + 1} of {total}, pass {entry.iteration}"
        lines.append(f"{marker} {i}. {entry.label}: {entry.goal}{where}")
    return "\n".join(lines)


def _step_tag(step: SopStep) -> str:
    return "" if step.kind == "work" else f" ({step.kind})"


def _entry_briefing(lib: Library, session: Session) -> str:
    entry = session.entry
    parts = [f"# Entry {session.current + 1} of {len(session.entries)}: {entry.label}", f"Entry goal: {entry.goal}"]
    if entry.note:
        parts.append(entry.note)
    parts += [
        f"## Situation SOP: {SITUATIONS[entry.situation]}",
        lib.situations[entry.situation].full_text,
        f"## Scope: {SCOPES[entry.scope]}",
        lib.scopes[entry.scope].full_text,
    ]
    return "\n\n".join(parts)


def _plan_request(lib: Library, session: Session) -> str:
    entry = session.entry
    steps = sop_steps(lib, entry)
    outline = "\n".join(f"{s.number}. {s.title}{_step_tag(s)}" for s in steps)
    return "\n\n".join([
        "## Write your plan before any work",
        f"Call submit_plan(session_id='{session.id}', plan=[...]) with exactly {len(steps)} items, one per SOP step in this order:",
        outline,
        "Each item states the specific work you will do for that step on this assignment, the questions you must answer, "
        "and the result that will show the step is complete. Write it from the SOP, the scope sheet, and what you already know "
        "about the assignment; do not start the work until the plan is accepted.",
    ])


def _procedure_blocks(lib: Library, step: SopStep, numbers: list[int]) -> list[str]:
    if not numbers:
        return ["## Procedure", "No procedure steps apply here."]
    blocks: list[str] = []
    for n in numbers:
        proc = lib.procedure.steps[n]
        if step.modifier == "keep":
            blocks += [f"## Procedure step {n}: {proc.name} — Keep rule (get_process_step({n}) for the full step)", proc.paragraph("Keep:")]
        elif step.modifier == "produces":
            blocks += [f"## Procedure step {n}: {proc.name} — what it produces (get_process_step({n}) for the full step)", proc.paragraph("Produces:")]
        else:
            blocks += [f"## Procedure step {n}: {proc.name} (verbatim)", proc.text]
    return blocks


def render_step(lib: Library, session: Session, *, briefing: bool = False, preamble: bool = False) -> str:
    entry = session.entry
    if entry is None:
        return _closing(lib, session)

    parts: list[str] = []
    if preamble:
        parts += ["# Working method (process.txt, read once and keep as the authority)", lib.procedure.preamble]
    if entry.phase == "plan":
        parts += [_entry_briefing(lib, session), _plan_request(lib, session)]
        return "\n\n".join(p for p in parts if p)
    if briefing:
        parts.append(_entry_briefing(lib, session))
    if entry.awaiting_user:
        parts += [_awaiting(session, entry)]
        return "\n\n".join(p for p in parts if p)

    steps = sop_steps(lib, entry)
    step = current_sop_step(lib, entry)
    numbers = step.resolve(entry.k)
    situation = SITUATIONS[entry.situation]
    scope = lib.scopes[entry.scope]
    where = ", ".join(f"{n} ({lib.procedure.steps[n].name})" for n in numbers) or "none"

    parts.append(f"# {situation} step {step.number} of {len(steps)}: {step.title}{_step_tag(step)}")
    context = [
        f"Session ID: {session.id} (pass session_id='{session.id}' with every call)",
        f"The user's words: {session.request}",
        f"Session end goal: {session.end_goal}",
        f"Entry {session.current + 1} of {len(session.entries)}: {entry.label} — {entry.goal}",
        f"Works in procedure step: {where}",
    ]
    if session.constraints:
        context.append("Constraints, in the user's words (anything not listed here is open):")
        context += [f"- {c.id}: {c.text} — \"{c.quote}\"" for c in session.constraints]
    else:
        context.append("Constraints: none quoted from the user, so no identity or other decision is kept on the user's say-so.")
    if session.conditions:
        context.append(f"Task conditions: {session.conditions}")
    if entry.k is not None:
        context.append(f"Responsible procedure step (k): {entry.k} ({lib.procedure.steps[entry.k].name})")
    if entry.iteration > 1 and entry.resume_at is not None:
        context.append(f"Pass {entry.iteration}: verification returned procedure step {entry.resume_at}; resume there. Earlier results are reused unchanged.")
    parts.append("\n".join(context))

    parts += [f"## SOP step ({situation})", step.instruction]
    if entry.plan:
        parts += ["## Your plan for this step", entry.plan[entry.index]]

    scope_lines = [f"Boundary: {scope.fields.get('Boundary', '')}"]
    scope_lines += [f"{label}: {text}" for label, text in scope.lines_for(numbers or [VERIFY_STEP])]
    parts += [f"## Scope: {scope.title}", "\n".join(scope_lines)]

    earlier = _earlier_results(entry, steps)
    if earlier:
        parts += ["## Earlier results in this entry (cite these IDs)", earlier]
    if entry.captures:
        parts += ["## Captures in this entry", _capture_lines(entry)]
    last = entry.verifications[-1] if entry.verifications else None
    if last and last.findings and step.kind != "verify":
        title = "## The user's reason for returning the work" if last.outcome.startswith("returned by the user") else "## Latest verification findings"
        parts += [title, last.findings]

    parts += _procedure_blocks(lib, step, numbers)
    parts += ["## Working rules", lib.procedure.working_rules]

    first_sop = steps[0].number == step.number
    cite_rule = (
        "cite 'request' or the constraint IDs it rests on"
        if first_sop
        else "cite at least one earlier result ID it builds on (constraints and 'request' may be cited as well)"
    )
    results_rule = (
        f"results=[{{statement, based_on}}, ...] lists this step's results; each result must {cite_rule}. "
        "dropped=[{id, reason}] sets aside an earlier result no later step will use; before verification every earlier "
        "result is used by a later step or dropped."
    )
    if step.kind == "verify":
        if entry.situation == "review":
            finish = "Finish with report_verification(outcome='done', findings=...) listing each finding with its evidence, responsible step, and recommended change."
        else:
            finish = (
                "Before finishing, capture the result (capture with kind 'result') after the last change, and what it is compared "
                "with: its references or accepted views (kind 'comparison'), or the work before (kind 'before'). Then finish with "
                "report_verification: outcome 'ready' when nothing remains to correct, or the number (0–9) of the procedure step "
                "responsible for the earliest discrepancy, with findings naming the evidence. 'ready' hands the work to the user; "
                "report what was measured and checked, never that it is good, clean, better, or fixed."
            )
    elif step.kind == "trace":
        finish = f"Finish with complete_step(handoff=..., results=..., responsible_step=<0–9>) naming the cause and the procedure step where it lies. {results_rule}"
    else:
        finish = f"When this step's result exists, call complete_step with a short handoff naming the actual result and how the next step uses it. {results_rule}"
    finish += " If the decision belongs to a parent scope or another situation, call escalate instead. If a discovery changes the plan, call submit_plan again with the revised plan."
    first = numbers[0] if numbers else VERIFY_STEP
    parts += [
        "## Now",
        f'Announce: "I\'m on {situation} step {step.number}: {step.title}, working in procedure step {first} '
        f'([decide or keep]). This step requires [operation]. For this assignment, I\'ll [the planned action, made specific]."',
        finish,
    ]
    return "\n\n".join(p for p in parts if p)


def _earlier_results(entry: Entry, steps) -> str:
    titles = {s.number: s.title for s in steps}
    lines: list[str] = []
    current = None
    for result in sorted(latest_results(entry).values(), key=lambda r: (r.sop_step, int(r.id.split(".")[1]))):
        if result.sop_step != current:
            current = result.sop_step
            lines.append(f"SOP step {current} ({titles.get(current, '')}):")
        mark = f" [dropped: {entry.dropped[result.id]}]" if result.id in entry.dropped else ""
        lines.append(f"- {result.id}: {result.statement} (based on {', '.join(result.based_on)}){mark}")
    return "\n".join(lines)


def _capture_lines(entry: Entry) -> str:
    lines = []
    for c in entry.captures:
        files = ", ".join(w.get("page", {}).get("file", "") for w in c.widths)
        heights = ", ".join(f"{w['width']}: {w.get('page_height')}px{' (scrolls sideways)' if w.get('overflow') else ''}" for w in c.widths)
        lines.append(f"- {c.kind} '{c.label}' {c.url}{' ' + c.selector if c.selector else ''} — taken by {c.taken_by} at {c.taken_at}; page heights {heights}; files {files}")
    return "\n".join(lines)


def _awaiting(session: Session, entry: Entry) -> str:
    last = entry.verifications[-1] if entry.verifications else None
    compare = _compare_page(session, entry)
    return "\n\n".join(
        p
        for p in [
            f"# Waiting for the user's verdict — {entry.label}",
            f"Session ID: {session.id}",
            "The work is ready for the user's review. Tell the user it is ready, show them the captures, and report what was "
            "measured and checked. Do not call it good, clean, better, or fixed, and do not continue until they decide.",
            f"Side-by-side page: {compare}" if compare else "",
            "## Captures",
            _capture_lines(entry),
            f"## Your verification notes\n{last.findings}" if last and last.findings else "",
            "The user records their verdict themselves, either with `taskmaster verdict "
            f"{session.id} done` or `taskmaster verdict {session.id} return <step 0–9> --reason \"...\"` on their own machine, "
            "or on the Taskmaster review page of the connector. You cannot record it for them.",
        ]
        if p
    )


def _compare_page(session: Session, entry: Entry) -> str:
    """Write a page showing each width's result beside its comparisons, for captures Taskmaster took itself."""
    taken = [c for c in entry.captures if c.taken_by == "taskmaster"]
    if not taken:
        return ""
    folder = _capture_dir(session)
    index = session.entries.index(entry) + 1
    path = folder / f"entry-{index}-side-by-side.html"
    order = {"result": 0, "comparison": 1, "before": 2}
    rows = []
    for width in CAPTURE_WIDTHS:
        cells = []
        for c in sorted(taken, key=lambda c: order[c.kind]):
            w = next((x for x in c.widths if x.get("width") == width), None)
            if not w:
                continue
            image = (w.get("element") or w.get("page") or {}).get("file", "")
            rel = os.path.relpath(image, folder) if image else ""
            cells.append(
                f'<figure><figcaption>{html.escape(c.kind)}: {html.escape(c.label)}<br><small>{html.escape(c.url)} · '
                f'page {w.get("page_height")}px{" · scrolls sideways" if w.get("overflow") else ""}</small></figcaption>'
                f'<img src="{html.escape(rel)}" alt=""></figure>'
            )
        rows.append(f"<h2>{width}px</h2><div class=row>{''.join(cells)}</div>")
    path.write_text(
        "<!doctype html><meta charset=utf-8><title>Side by side</title><style>"
        "body{font:14px system-ui,sans-serif;margin:24px}.row{display:flex;gap:24px;align-items:flex-start;overflow-x:auto}"
        "figure{margin:0;flex:0 0 auto;max-width:48%}img{max-width:100%;border:1px solid #ccc}figcaption{margin-bottom:6px}"
        f"</style><h1>{html.escape(entry.label)}: {html.escape(entry.goal)}</h1>{''.join(rows)}",
        encoding="utf-8",
    )
    return str(path)


def _capture_dir(session: Session) -> Path:
    return store().root / "captures" / session.id


def _closing(lib: Library, session: Session) -> str:
    if session.status == "complete":
        return (
            f"All {len(session.entries)} entries are done for session {session.id}.\n\n{_plan(lib, session)}\n\n"
            f"Deliver the result as the final situation's completion describes, then call end_session(session_id='{session.id}') "
            "with a summary. Use add_entries if more work is needed."
        )
    return f"Session {session.id} is {session.status}."


def _after_move(lib: Library, session: Session, index: int) -> str:
    """The reply after a step finishes: the next step, or the next entry's briefing, or the closing."""
    if session.current == index and session.status == "active":
        return render_step(lib, session)
    finished = session.entries[index]
    if session.status == "complete":
        return f"{finished.label} is done.\n\n" + _closing(lib, session)
    return f"{finished.label} is done.\n\nEntries:\n{_plan(lib, session)}\n\n" + render_step(lib, session)


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
def start_session(
    request: str,
    end_goal: str,
    entries: Entries,
    task_conditions: str = "",
    constraints: Constraints | None = None,
) -> str:
    """Start a design session and receive its session_id, the working method, and the first entry's SOP.

    request: the user's own words, copied exactly. end_goal: the observable condition that holds when the work is complete.
    entries: the matrix entries in the order they will run, worked backward from the end goal.
    task_conditions: device, platform, audience, available assets, and stage of completion.
    constraints: what the user said must be kept or followed, such as an existing identity, each with the user's words
    quoted from the request. A constraint without the user's words is refused; that decision stays open.
    """
    session = new_session(request, end_goal, entries, task_conditions, constraints or [])
    store().save(session)
    lib = library()
    header = f"Session {session.id} started. Pass session_id='{session.id}' with every call for this work.\n\nEntries:\n{_plan(lib, session)}"
    return header + "\n\n" + render_step(lib, session, preamble=True)


@mcp.tool(structured_output=False)
@_guarded
def submit_plan(session_id: SessionId, plan: PlanItems) -> str:
    """Write or revise the plan for the current entry: one item per SOP step, in order. The first plan starts the work."""
    session = _session(session_id)
    lib = library()
    starting = engine_submit_plan(lib, session, plan)
    store().save(session)
    if starting:
        return "Plan accepted.\n\n" + render_step(lib, session)
    return "Plan revised. Continue with the current step.\n\n" + render_step(lib, session)


@mcp.tool(structured_output=False)
@_guarded
def current_step(session_id: SessionId) -> str:
    """Re-issue the current step with its SOP, plan item, procedure text, and earlier results. Use after an interruption or condensed context."""
    return render_step(library(), _session(session_id), briefing=True)


@mcp.tool(structured_output=False)
@_guarded
def complete_step(
    session_id: SessionId,
    handoff: str,
    results: Results,
    responsible_step: int | None = None,
    dropped: Drops | None = None,
) -> str:
    """Finish the current SOP step (not a verify step) and receive the next one.

    handoff: the actual result and how the next step uses it.
    results: this step's results, each {statement, based_on}. based_on lists the IDs of the earlier results it builds on
    (shown in each step as 2.1, 3.2, ...); the first step cites 'request' or constraint IDs.
    responsible_step: required on a trace step — the procedure step (0–9) where the cause lies.
    dropped: earlier results no later step will use, each {id, reason}.
    """
    session = _session(session_id)
    lib = library()
    index = session.current
    engine_complete_step(lib, session, handoff, responsible_step, results, dropped or [])
    store().save(session)
    return _after_move(lib, session, index)


@mcp.tool(structured_output=False)
@_guarded
def report_verification(session_id: SessionId, outcome: str, findings: str = "") -> str:
    """Finish a verify step.

    outcome: 'ready' when nothing remains to correct, which hands the work to the user for their verdict; or the number
    (0–9) of the procedure step responsible for the earliest discrepancy. A Review finishes with 'done' and its findings.
    findings: each discrepancy with its evidence and responsible step, or what was measured and checked when ready.
    """
    session = _session(session_id)
    lib = library()
    index = session.current
    engine_report_verification(lib, session, outcome, findings)
    store().save(session)
    return _after_move(lib, session, index)


@mcp.tool(structured_output=False)
@_guarded
def escalate(session_id: SessionId, reason: str, to_scope: Scope | None = None, to_situation: Situation | None = None) -> str:
    """End the current entry because its decision belongs elsewhere, and start the right entry in its place.

    Use when the unit should not exist or should move (escalate to its parent scope), or when a Fix needs the
    structure replaced (escalate to redesign). reason: what the step showed.
    """
    session = _session(session_id)
    lib = library()
    engine_escalate(session, reason, to_scope, to_situation)
    store().save(session)
    return f"Escalated.\n\nEntries:\n{_plan(lib, session)}\n\n" + render_step(lib, session)


@mcp.tool(structured_output=False)
@_guarded
def capture(session_id: SessionId, kind: CaptureKind, url: str, label: str = "", selector: str = "") -> str:
    """Have Taskmaster capture a page at 1440, 820 and 390 pixels wide, for the current entry.

    kind: 'result' for the work as built (after its last change), 'comparison' for a reference or accepted view it is
    compared with, 'before' for the work before it changed. url: the page. selector: the element to capture on its own
    as well, such as the section being designed. label: a short name, such as 'Ingredients tab'.
    """
    session = _session(session_id)
    entry = session.entry
    if entry is None:
        raise EngineError(f"Session {session.id} is {session.status}.")
    folder = _capture_dir(session)
    index = session.entries.index(entry) + 1
    name = f"entry-{index}-{len(entry.captures) + 1}-{kind}-{re.sub(r'[^a-z0-9]+', '-', (label or kind).lower()).strip('-')[:40]}"
    manifest = _run_capture(url, folder, name, selector)
    recorded = add_capture(session, kind, label, manifest, "taskmaster")
    store().save(session)
    page = _compare_page(session, entry)
    lines = [f"Captured {recorded.kind} '{recorded.label}' at {', '.join(str(w) for w in CAPTURE_WIDTHS)}:"]
    for w in recorded.widths:
        element = f", element {w['element_height']}px" if w.get("element_height") is not None else ""
        lines.append(f"- {w['width']}: page {w['page_height']}px{element}{', scrolls sideways' if w.get('overflow') else ''} — {w['page']['file']}")
    if page:
        lines.append(f"Side-by-side page: {page}")
    return "\n".join(lines)


def _run_capture(url: str, folder: Path, name: str, selector: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise EngineError("Capturing needs Node.js and Playwright on this machine (npm i playwright && npx playwright install chromium).")
    script = Path(__file__).with_name("capture.mjs")
    command = [node, str(script), "--out", str(folder), "--name", name]
    if selector.strip():
        command += ["--selector", selector.strip()]
    command.append(url.strip())
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=300, cwd=os.getcwd())
    except subprocess.TimeoutExpired:
        raise EngineError(f"Capturing {url} took longer than five minutes.") from None
    if done.returncode != 0:
        raise EngineError(f"The capture of {url} failed: {done.stderr.strip() or 'no output'}")
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        raise EngineError(f"The capture script returned something unreadable: {done.stdout[:200]}") from None


@mcp.tool(structured_output=False)
@_guarded
def get_process_step(step: int) -> str:
    """Return one procedure step from process.txt in full (0–10), for steps an SOP step names only by its Keep rule."""
    lib = library()
    if step not in lib.procedure.steps:
        raise EngineError("Procedure steps are numbered 0 to 10.")
    return lib.procedure.steps[step].text


@mcp.tool(structured_output=False)
@_guarded
def add_entries(session_id: SessionId, entries: Entries, position: Literal["next", "end"] = "next") -> str:
    """Add matrix entries to a session, after the current entry ('next') or at the end.

    Use when the work needs another entry, such as a Fix or Redesign the user authorized after a Review.
    """
    session = _session(session_id)
    lib = library()
    was_complete = session.status == "complete"
    engine_add_entries(session, entries, position)
    store().save(session)
    text = f"Entries updated:\n{_plan(lib, session)}"
    if was_complete:
        text += "\n\n" + render_step(lib, session)
    return text


@mcp.tool(structured_output=False)
@_guarded
def get_status(session_id: str = "") -> str:
    """Show a session's goal, entries, plan, position, and recorded results. Without a session_id, list recent sessions."""
    if not session_id.strip():
        recent = store().recent()
        if not recent:
            return "No sessions yet. Call get_matrix, then start_session."
        return "Recent sessions (pass one as session_id):\n" + "\n".join(f"- {s.id} [{s.status}] {s.request[:80]}" for s in recent)
    session = _session(session_id)
    lib = library()
    lines = [f"Session {session.id} [{session.status}]", f"Request: {session.request}", f"End goal: {session.end_goal}"]
    if session.conditions:
        lines.append(f"Task conditions: {session.conditions}")
    lines += ["", "Entries:", _plan(lib, session)]
    for i, entry in enumerate(session.entries, 1):
        if not entry.plan and not entry.handoffs and not entry.note:
            continue
        lines += ["", f"Entry {i} ({entry.label}):"]
        if entry.note:
            lines.append(entry.note)
        running = entry.status == "active" and entry.phase == "run"
        for n, (step, item) in enumerate(zip(sop_steps(lib, entry), entry.plan)):
            mark = "▶" if running and n == entry.index else ("·" if running and n > entry.index else "✓")
            lines.append(f"{mark} {step.number}. {step.title}: {item}")
        for handoff in entry.handoffs:
            lines.append(f"- pass {handoff.iteration}, SOP step {handoff.sop_step}: {handoff.text}")
        results = _earlier_results(entry, sop_steps(lib, entry))
        if results:
            lines += ["Results:", results]
        if entry.captures:
            lines += ["Captures:", _capture_lines(entry)]
        for check in entry.verifications:
            lines.append(f"- pass {check.iteration}, verify at SOP step {check.sop_step}: {check.outcome}" + (f" — {check.findings}" if check.findings else ""))
        if entry.awaiting_user:
            lines.append("Waiting for the user's verdict.")
    if session.constraints:
        lines += ["", "Constraints, in the user's words:"] + [f"- {c.id}: {c.text} — \"{c.quote}\"" for c in session.constraints]
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guarded
def end_session(session_id: SessionId, summary: str = "") -> str:
    """End a session. summary: what was delivered and any remaining limitations."""
    session = _session(session_id)
    engine_end_session(session, summary)
    store().save(session)
    return f"Session {session.id} ended.\n\n{_plan(library(), session)}"


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
    """A situation SOP: create, extend, redesign, fix, or review."""
    return library().situations[name].full_text


@mcp.resource("taskmaster://design/scopes/{name}", mime_type="text/plain")
def scope_resource(name: str) -> str:
    """A scope sheet: element, component, section, page, flow, product, or shared-styles."""
    return library().scopes[name].full_text


@mcp.prompt()
def design(request: str) -> str:
    """Run a design request through Taskmaster."""
    return (
        f"Use Taskmaster for this design request: {request}\n\n"
        "Call get_matrix and choose the matrix entries that get from the current state to the end goal. "
        "Call start_session, write the plan for each entry's SOP with submit_plan before any work, "
        "then execute each step Taskmaster gives you in order."
    )


def verdict_main(argv: list[str]) -> None:
    """The user's own command for work that is ready for review: taskmaster verdict <session> done|return [step] --reason."""
    parser = argparse.ArgumentParser(prog="taskmaster verdict", description="Record your verdict on work Taskmaster says is ready for review")
    parser.add_argument("session_id")
    parser.add_argument("verdict", choices=["done", "return"])
    parser.add_argument("step", nargs="?", type=int, help="with return: the procedure step (0–9) the work goes back to")
    parser.add_argument("--reason", default="", help="why; required with return")
    args = parser.parse_args(argv)
    session = store().load(args.session_id)
    if session is None:
        sys.exit(f"No session {args.session_id} in {store().root}.")
    try:
        outcome = record_verdict(library(), session, args.verdict, args.step, args.reason)
    except EngineError as error:
        sys.exit(str(error))
    store().save(session)
    if outcome == "done":
        print(f"Marked done. {session.id}: {session.status}.")
    else:
        print(f"Returned to procedure step {args.step}. The agent sees your reason at its next step.")


def main() -> None:
    if sys.argv[1:2] == ["verdict"]:
        verdict_main(sys.argv[2:])
        return
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
