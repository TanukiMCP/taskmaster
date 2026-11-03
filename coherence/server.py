"""CoherenceMCP server: the tools an agent calls, in the order the record allows."""

from __future__ import annotations

import argparse
import inspect
import json
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, BeforeValidator, Field

from . import __version__
from . import record as rec
from .library import INDEX, load_library
from .record import Answer, Custom, Entry, Opening, OrderInput, RecordError, Source, Store, Work
from .trace import scan, touched
from .views import packet, render_shape

INSTRUCTIONS = """\
CoherenceMCP derives a project's coherent shape from real sources, asks the person for one approval, and builds it under a closed world, so that nothing in the product comes from the average version of the thing.

Start with begin: the person's request word for word, mode 'idea' or 'existing', their questions, and any conversation context you will quote. Then call next whenever you are unsure what to do: it returns the current step with exactly the context that step needs. Answer what it gives you with the tool it names (settle, walk, decide, compile, complete, gap, revise, verify). The server refuses anything out of order or in the wrong form and says why. read('procedure') is the full procedure.

Keep no other plan, tasklist, or tracking document: the record in .coherence/ is the plan. Never decide for the person: show them .coherence/shape.md and record their decision.
"""

mcp = MCPServer("coherence", instructions=INSTRUCTIONS, version=__version__)

_project: Path | None = None
_any_project = False
_active: ContextVar[Path | None] = ContextVar("project", default=None)

ProjectArg = Annotated[str, Field(description="The project folder's absolute path. Required when the server serves any project "
                                              "(Claude Desktop); otherwise optional, and it must be the server's own project")]


def _fixed() -> Path | None:
    """The project the server was started for, if it was given one."""
    if _project is not None:
        return _project
    env = os.environ.get("COHERENCE_PROJECT")
    return Path(env).resolve() if env else None


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a)) == os.path.normcase(str(b))


def resolve_project(named: str = "") -> Path:
    """The folder a call works in: the one it names, or the server's own project, or the current folder."""
    named = named.strip()
    if not named:
        if _any_project:
            raise RecordError("Name the project: pass project, the absolute path of its folder, on every call. "
                              "If the person hasn't said where the project lives or should be made, ask them.")
        return _fixed() or Path.cwd().resolve()
    path = Path(named).expanduser()
    if not path.is_absolute():
        raise RecordError(f"project must be an absolute path to the project's folder, not '{named}'.")
    path = path.resolve()
    if path.exists() and not path.is_dir():
        raise RecordError(f"{path} is a file; project must be the project's folder.")
    fixed = None if _any_project else _fixed()
    if fixed is not None and not _same(path, fixed):
        raise RecordError(f"This server works in {fixed}, not {path}.")
    return path


def project() -> Path:
    return _active.get() or resolve_project()


def store() -> Store:
    return Store(project())


def _json(value: Any) -> Any:
    """Some clients send lists and objects as JSON strings; accept both."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def J(kind, description: str):
    return Annotated[kind, BeforeValidator(_json), Field(description=description)]


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _step(tool: str):
    """Load the record, run the move, save, log the step, and reply with the next packet.

    Every step also takes project, the folder it works in; the move itself never sees it.
    """

    def wrap(func):
        @wraps(func)
        def wrapper(*args, project: str = "", **kwargs):
            try:
                where = resolve_project(project)
            except RecordError as error:
                return f"Not done: {error}"
            token = _active.set(where)
            try:
                return run(*args, **kwargs)
            finally:
                _active.reset(token)

        def run(*args, **kwargs):
            s = store()
            context = s.last_packet()
            entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool,
                     "args": {k: _plain(v) for k, v in kwargs.items()}, "context": context}
            try:
                head, record, findings = func(*args, **kwargs)
            except RecordError as error:
                s.log(json.dumps({**entry, "ok": False, "error": str(error)}, ensure_ascii=False))
                return f"Not done: {error}"
            s.save(record)
            if record.points["root"].answer:
                s.write_shape(render_shape(record))
            nxt = packet(load_library(), record, findings)
            s.set_packet(nxt)
            s.log(json.dumps({**entry, "ok": True, "phase": record.phase}, ensure_ascii=False))
            reply = f"{head}\n\n{nxt}" if head else nxt
            if _any_project:
                reply = f"Project: {s.project} (pass project='{s.project}' on every call)\n\n{reply}"
            return reply

        sig = inspect.signature(func, eval_str=True)
        wrapper.__signature__ = sig.replace(parameters=[
            *sig.parameters.values(),
            inspect.Parameter("project", inspect.Parameter.KEYWORD_ONLY, default="", annotation=ProjectArg),
        ])
        return wrapper

    return wrap


def _all_findings(record):
    return scan(record, project(), touched(record)) if record.phase == "verify" else []


@mcp.tool(structured_output=False)
@_step("begin")
def begin(
    request: Annotated[str, Field(description="The person's message word for word, not a summary")],
    mode: Annotated[Literal["idea", "existing"], Field(description="'idea' for a new project, 'existing' for a project that already exists here")],
    questions: J(list[str] | None, "Each question the person asked, in their words") = None,
    context: Annotated[str, Field(description="Conversation passages you will quote as conversation sources, verbatim")] = "",
    replace: Annotated[bool, Field(description="Start over when a record already exists; the old one is archived")] = False,
):
    """Start a project's record from the person's request. Returns the procedure and the first point: the root."""
    s = store()
    if mode == "existing" and not s.project.is_dir():
        raise RecordError(f"There is no folder at {s.project}; mode 'existing' needs the project as it stands.")
    if s.exists():
        if not replace:
            raise RecordError("This project already has a record. Call next to continue it, or begin with replace=true to start over.")
        s.archive()
    record = rec.begin(request, mode, questions, context)
    return f"Record started in {s.dir}.\n\n# Procedure (read once; read('procedure') returns it again)\n\n{load_library().procedure}", record, []


@mcp.tool(name="next", structured_output=False)
@_step("next")
def next_step():
    """The current step, with exactly the context it needs. Call it whenever you are unsure what to do, or after an interruption."""
    record = store().load()
    return "", record, _all_findings(record)


@mcp.tool(structured_output=False)
@_step("settle")
def settle(
    point: Annotated[str, Field(description="The id of the point being answered")],
    gate: Annotated[Literal["decide", "consequence", "drop"], Field(description="decide: answer the seven questions; consequence: only one answer is defensible; drop: a different answer would change nothing")] = "decide",
    serves: Annotated[str, Field(description="1. How this serves its parents, and through them the root")] = "",
    situation: Annotated[str, Field(description="2. What happens to a person here: who, what they perceive, what they can do, what follows. For a job: what must be true")] = "",
    average: Annotated[str, Field(description="3. What the average version of this kind of project does here, stated before deciding")] = "",
    decision: Annotated[str, Field(description="4. What this project does here")] = "",
    excludes: J(list[str] | None, "4. The concrete alternatives this decision rules out") = None,
    reason: Annotated[str, Field(description="4. Why, from the parents or evidence. For drop: why nothing would change")] = "",
    agrees_with_average: Annotated[bool, Field(description="4. True when the decision is the average; then evidence specific to this project is required")] = False,
    work: J(Work | None, "5. Existing work: examined, chosen (exact reference), license, keep, change") = None,
    custom: J(Custom | None, "5. Only when nothing existing fits: reason and condition") = None,
    wrong_if: Annotated[str, Field(description="6. The observation that would show this is wrong")] = "",
    opens: J(list[Opening] | None, "7. New points this leaves open: id, kind, question, optional aspect and parents") = None,
    sources: J(list[Source] | None, "Where the answer comes from: user, conversation, research, work, derived, observation") = None,
    confidence: Annotated[Literal["low", "medium", "high"], Field(description="How certain the decision is")] = "medium",
    manifest: J(list[Entry] | None, "Concrete values the build will need: work, token, content, rule, deferred") = None,
    aspect: Annotated[str, Field(description="Optional design aspect for guidance")] = "",
    rule: Annotated[str, Field(description="For a consequence: the rule that produces it and where the rule comes from")] = "",
    still_holds: Annotated[str, Field(description="For a stale point: why its answer still holds against the changed parents")] = "",
):
    """Answer one point: drop it, settle it as a consequence, or decide it by answering the seven questions in order."""
    record = store().load()
    answer = Answer(serves=serves, situation=situation, average=average, decision=decision, excludes=excludes or [],
                    reason=reason, agrees_with_average=agrees_with_average, sources=sources or [], confidence=confidence,
                    work=work, custom=custom, wrong_if=wrong_if, opens=opens or [], manifest=manifest or [], rule=rule)
    if aspect:
        if aspect not in rec.ASPECTS:
            raise RecordError(f"'{aspect}' is not an aspect. Aspects: {', '.join(rec.ASPECTS)}.")
        record.point(point).aspect = aspect
    opened = rec.settle(record, point, gate, answer, still_holds)
    p = record.point(point)
    if still_holds.strip():
        head = f"Confirmed '{p.id}' still holds."
    elif gate == "drop":
        head = f"Dropped '{p.id}'."
    else:
        head = f"Settled '{p.id}' (v{p.version})." + (f" Opened: {', '.join(opened)}." if opened else "")
    return head, record, _all_findings(record)


@mcp.tool(structured_output=False)
@_step("walk")
def walk(
    experience: Annotated[str, Field(description="A person's way through the product from the first moment to the purpose, naming every situation as [id]")],
    construction: Annotated[str, Field(description="A builder's way through what has to exist, naming every family and job as [id]")],
    gaps: J(list[Opening] | None, "What the settled points don't determine: id, kind, question, parents") = None,
):
    """Walk the settled record both ways. Gaps become open points; a walk with no gaps sends the shape to the person."""
    record = store().load()
    opened = rec.walk(record, experience, construction, gaps)
    head = f"Walk recorded. Opened: {', '.join(opened)}." if opened else "Walk recorded with no gaps."
    return head, record, []


@mcp.tool(structured_output=False)
@_step("decide")
def decide(
    approve: Annotated[bool, Field(description="The person's decision on .coherence/shape.md")],
    reason: Annotated[str, Field(description="The person's words: required for a denial")] = "",
    points: J(list[str] | None, "For a denial: the points the person's reason concerns") = None,
):
    """Record the person's approval or denial of the shape. Never decide for them."""
    record = store().load()
    rec.decide(record, approve, reason, points)
    return ("Approved." if approve else f"Denied. Reopened: {', '.join(points or [])}."), record, []


@mcp.tool(name="compile", structured_output=False)
@_step("compile")
def compile_(
    orders: J(list[OrderInput], "Orders: id, realizes, uses, after, touches, checks"),
    token_files: J(list[str] | None, "Files where manifest values are written; the only place literals may live") = None,
):
    """Turn the approved record into build orders. Every family and job must be realized and every manifest entry used."""
    record = store().load()
    rec.compile_orders(record, orders, token_files)
    return f"Compiled {len(record.orders)} orders.", record, _all_findings(record)


class DeferredValue(BaseModel):
    id: str = Field(description="The deferred manifest entry")
    value: str = Field(description="The value set by looking at the built thing")
    observation: str = Field(description="What was observed that shows the value meets its condition")


@mcp.tool(structured_output=False)
@_step("complete")
def complete(
    order: Annotated[str, Field(description="The order's id")],
    summary: Annotated[str, Field(description="What was built")],
    evidence: Annotated[str, Field(description="What you observed with your tools that shows it works")],
    deferred: J(list[DeferredValue] | None, "Each deferred value this order used: id, value, observation") = None,
):
    """Finish an order. The server scans the files it touched for values the manifest did not settle."""
    record = store().load()
    target = record.order(order)
    findings = scan(record, project(), touched(record, [target]))
    rec.complete(record, order, summary, evidence, {d.id: (d.value, d.observation) for d in deferred or []}, findings)
    return f"Order '{target.id}' done.", record, _all_findings(record)


@mcp.tool(structured_output=False)
@_step("gap")
def gap(
    order: Annotated[str, Field(description="The order that ran into it")],
    id: Annotated[str, Field(description="An id for the new point")],
    kind: Annotated[Literal["situation", "family", "job", "tension"], Field(description="What kind of point it is")],
    question: Annotated[str, Field(description="What the order doesn't cover, as a question")],
    parents: J(list[str], "The settled points it is open under"),
    aspect: Annotated[str, Field(description="Optional design aspect")] = "",
):
    """Something the order does not cover becomes an open point, answered by the same questions, instead of a choice."""
    record = store().load()
    rec.gap(record, order, Opening(id=id, kind=kind, question=question, parents=parents, aspect=aspect))
    note = " It is at the level the person approved, so they will see it again." if kind != "job" else ""
    return f"Gap '{id}' raised from order '{order}'.{note}", record, []


@mcp.tool(structured_output=False)
@_step("revise")
def revise(
    point: Annotated[str, Field(description="The settled point an observation has undermined")],
    reason: Annotated[str, Field(description="The observation")],
):
    """Reopen a settled point. Everything built on it becomes stale, including the orders that realized it."""
    record = store().load()
    stale = rec.revise(record, point, reason)
    return f"Reopened '{point}'." + (f" Now stale: {', '.join(stale)}." if stale else ""), record, []


@mcp.tool(structured_output=False)
@_step("verify")
def verify(
    walk: Annotated[str, Field(description="Your way through the built product, naming every situation as [id] and what you observed")],
    evidence: Annotated[str, Field(description="What you ran, opened, or captured")],
    review: Annotated[str, Field(description="Who reviewed the product without having built it, and what they found")],
):
    """Close the build once the traces are clean, the walk covers every situation, and an independent review is recorded."""
    record = store().load()
    rec.verify(record, walk, evidence, review, scan(record, project(), touched(record)))
    return "Verified.", record, []


@mcp.tool(structured_output=False)
def read(ref: Annotated[str, Field(description="procedure, method, design, or design/<aspect>; empty lists them")] = "") -> str:
    """Read the library: the procedure, the method, or design guidance."""
    text = load_library().read(ref)
    return text if text is not None else f"Not done: '{ref}' names nothing in the library.\n\n{INDEX}"


@mcp.resource("coherence://procedure", mime_type="text/plain")
def procedure_resource() -> str:
    """The CoherenceMCP procedure."""
    return load_library().procedure


@mcp.resource("coherence://shape", mime_type="text/markdown")
def shape_resource() -> str:
    """The current shape of this project."""
    if _any_project:
        return "This server serves any project: the shape is in .coherence/shape.md inside the project's folder."
    s = store()
    return render_shape(s.load()) if s.exists() else "No record yet."


@mcp.prompt()
def cohere(request: str, project: str = "") -> str:
    """Run a request through CoherenceMCP."""
    where = f" The project's folder is {project}: pass project='{project}' on every call." if project else ""
    return (
        f"Use CoherenceMCP for this request: {request}\n\n"
        "Call begin with the request word for word, mode 'idea' or 'existing', and the questions it asks. Then follow next: "
        "answer each point it gives you, walk the record, show the person the shape, and build only what they approve." + where
    )


def main() -> None:
    global _project, _any_project
    parser = argparse.ArgumentParser(prog="coherence-mcp", description="CoherenceMCP server")
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", help="The project folder (default: COHERENCE_PROJECT or the current folder)")
    where.add_argument("--any-project", action="store_true",
                       help="Serve any project folder, named by the project argument of every call (for Claude Desktop, "
                            "which doesn't start servers in a project)")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--version", action="version", version=f"coherence-mcp {__version__}")
    args = parser.parse_args()
    if args.project:
        _project = Path(args.project).resolve()
    _any_project = args.any_project
    load_library()  # fail fast if the library files are missing or malformed
    if args.transport == "streamable-http":
        mcp.run("streamable-http", host=args.host, port=args.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
