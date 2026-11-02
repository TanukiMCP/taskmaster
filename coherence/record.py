"""The record: a project's points, its manifest, its orders, and the phase it is in.

The record is the single source of truth for a project. The agent submits answers;
the record checks their form and sources, keeps versions, and decides what is open
next. It never judges whether an answer is good, only whether it is well formed,
sourced, and connected to the purpose.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .library import ASPECTS

Phase = Literal["derive", "review", "compile", "build", "verify", "done"]
Kind = Literal["root", "question", "situation", "family", "job", "tension"]
APPROVAL_KINDS = ("root", "question", "situation", "family", "tension")
BUILT_KINDS = ("family", "job")
OPENABLE_KINDS = ("situation", "family", "job", "tension")
SOURCE_KINDS = ("user", "conversation", "research", "work", "derived", "observation")
REFUSED_PHRASES = ("best practice", "industry standard", "users expect", "common knowledge")
CONFIDENCE_WEIGHT = {"low": 3, "medium": 2, "high": 1}
ROOT_QUESTION = "What is this for, for whom, and what does it refuse to be?"
ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ID_MENTION = re.compile(r"\[([a-z0-9][a-z0-9._-]*)\]")


class RecordError(ValueError):
    """The submission does not fit the record's form or its current phase."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.lower().split())


def _names(ids) -> str:
    return ", ".join(f"'{i}'" for i in ids)


def _words(text: str) -> int:
    return len(text.split())


class Source(BaseModel):
    kind: str = Field(description="user, conversation, research, work, derived, or observation")
    ref: str = Field(default="", description="research: the link; work: the exact reference; derived: the point ids; observation: what was observed")
    quote: str = Field(default="", description="user and conversation: the exact words; research: the passage; observation: what it showed")


class Work(BaseModel):
    chosen: str = Field(description="Exact reference to the existing work chosen: a link, package@version, or path")
    license: str = Field(description="What its license allows")
    examined: list[str] = Field(description="The existing works actually examined, including the one chosen")
    keep: str = Field(description="What is kept: whatever makes it work")
    change: str = Field(description="What is changed: whatever makes it belong to this project")


class Custom(BaseModel):
    reason: str = Field(description="Why no existing work does this job")
    condition: str = Field(description="The condition the custom work must meet")


class Opening(BaseModel):
    id: str = Field(description="Short lowercase id for the new point, such as 'combat.warning'")
    kind: str = Field(description="situation, family, job, or tension")
    question: str = Field(description="What is open, as a question")
    aspect: str = Field(default="", description="Optional design aspect: " + ", ".join(ASPECTS))
    parents: list[str] | None = Field(default=None, description="Settled points it serves; defaults to the point being settled")


class Entry(BaseModel):
    id: str = Field(description="Short lowercase id, such as 'color.ink' or 'copy.hero-title'")
    kind: Literal["work", "token", "content", "rule", "deferred"]
    value: str = Field(default="", description="The value; for work, an exact reference; empty for deferred")
    note: str = Field(default="", description="work: what is kept and changed; deferred: the condition it must meet")
    paths: list[str] = Field(default_factory=list, description="work: where the work lives in the project")
    owner: str = ""
    observation: str = ""
    version: int = 1


class Answer(BaseModel):
    serves: str = ""
    situation: str = ""
    average: str = ""
    decision: str = ""
    excludes: list[str] = Field(default_factory=list)
    reason: str = ""
    agrees_with_average: bool = False
    sources: list[Source] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    work: Work | None = None
    custom: Custom | None = None
    wrong_if: str = ""
    opens: list[Opening] = Field(default_factory=list)
    manifest: list[Entry] = Field(default_factory=list)
    rule: str = ""


class Point(BaseModel):
    id: str
    kind: Kind
    question: str
    parents: list[str] = Field(default_factory=list)
    aspect: str = ""
    raised_by: str = ""
    status: Literal["open", "settled", "dropped"] = "open"
    gate: Literal["decide", "consequence", "drop"] | None = None
    answer: Answer | None = None
    version: int = 0
    inputs: dict[str, int] = Field(default_factory=dict)
    history: list[Answer] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Order(BaseModel):
    id: str
    realizes: list[str]
    uses: list[str] = Field(default_factory=list)
    after: list[str] = Field(default_factory=list)
    touches: list[str]
    checks: str
    done: bool = False
    done_versions: dict[str, int] = Field(default_factory=dict)
    summary: str = ""
    evidence: str = ""


class OrderInput(BaseModel):
    id: str = Field(description="Short lowercase id, such as 'foundations'")
    realizes: list[str] = Field(description="The family and job points this order builds")
    uses: list[str] = Field(default_factory=list, description="The manifest entries it may use")
    after: list[str] = Field(default_factory=list, description="Orders that must be done first")
    touches: list[str] = Field(description="Files or globs, relative to the project, that it will create or change")
    checks: str = Field(description="The check that will show its situations now happen")


class Walk(BaseModel):
    experience: str
    construction: str
    at: str = Field(default_factory=_now)


class Decision(BaseModel):
    approve: bool
    reason: str = ""
    points: list[str] = Field(default_factory=list)
    at: str = Field(default_factory=_now)


class Verification(BaseModel):
    walk: str
    evidence: str
    review: str
    at: str = Field(default_factory=_now)


class Record(BaseModel):
    request: str
    mode: Literal["idea", "existing"]
    context: str = ""
    phase: Phase = "derive"
    points: dict[str, Point] = Field(default_factory=dict)
    manifest: dict[str, Entry] = Field(default_factory=dict)
    orders: list[Order] = Field(default_factory=list)
    token_files: list[str] = Field(default_factory=list)
    walks: list[Walk] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    approved: dict[str, int] = Field(default_factory=dict)
    verification: Verification | None = None
    created: str = Field(default_factory=_now)
    updated: str = Field(default_factory=_now)

    def point(self, point_id: str) -> Point:
        point = self.points.get(point_id.strip())
        if point is None:
            raise RecordError(f"No point '{point_id}' in the record.")
        return point

    def order(self, order_id: str) -> Order:
        for order in self.orders:
            if order.id == order_id.strip():
                return order
        raise RecordError(f"No order '{order_id}'. Orders: {', '.join(o.id for o in self.orders) or 'none yet'}.")

    def touch(self) -> None:
        self.updated = _now()


# ---- derived state -------------------------------------------------------------------


def states(record: Record) -> dict[str, str]:
    """Each point's state: open, current, stale, or dropped. Parents are always earlier in the record."""
    state: dict[str, str] = {}
    for point in record.points.values():
        if point.status == "dropped":
            state[point.id] = "dropped"
        elif point.status == "open":
            state[point.id] = "open"
        elif all(state.get(p) == "current" and point.inputs.get(p) == record.points[p].version for p in point.parents):
            state[point.id] = "current"
        else:
            state[point.id] = "stale"
    return state


def children(record: Record) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {pid: [] for pid in record.points}
    for point in record.points.values():
        for parent in point.parents:
            found.setdefault(parent, []).append(point.id)
    return found


def descendants(record: Record, point_id: str) -> list[str]:
    kids = children(record)
    seen: list[str] = []
    pending = list(kids.get(point_id, []))
    while pending:
        pid = pending.pop(0)
        if pid not in seen and record.points[pid].status != "dropped":
            seen.append(pid)
            pending.extend(kids.get(pid, []))
    return seen


def ancestors(record: Record, point_id: str) -> list[str]:
    seen: list[str] = []
    pending = list(record.points[point_id].parents)
    while pending:
        pid = pending.pop(0)
        if pid not in seen:
            seen.append(pid)
            pending.extend(record.points[pid].parents)
    return [pid for pid in record.points if pid in seen]


def ready_points(record: Record) -> list[Point]:
    """Points to answer now: open or stale, with every parent current, in the order they were raised."""
    state = states(record)
    return [
        p for p in record.points.values()
        if state[p.id] in ("open", "stale") and all(state.get(parent) == "current" for parent in p.parents)
    ]


def unsettled(record: Record) -> list[str]:
    state = states(record)
    return [pid for pid, s in state.items() if s in ("open", "stale")]


def approval_valid(record: Record) -> bool:
    if not record.approved:
        return False
    state = states(record)
    level = {pid for pid, p in record.points.items() if p.kind in APPROVAL_KINDS and state[pid] != "dropped"}
    if level != set(record.approved):
        return False
    return all(state[pid] == "current" and record.points[pid].version == version for pid, version in record.approved.items())


def risk(record: Record) -> list[tuple[int, Point]]:
    """Settled decisions ranked by uncertainty times influence, highest first."""
    state = states(record)
    ranked = []
    for point in record.points.values():
        if state[point.id] != "current" or point.gate != "decide" or point.kind == "root":
            continue
        score = CONFIDENCE_WEIGHT[point.answer.confidence] * (1 + len(descendants(record, point.id)))
        ranked.append((score, point))
    return sorted(ranked, key=lambda pair: -pair[0])


def order_done(record: Record, order: Order) -> bool:
    if not order.done:
        return False
    state = states(record)
    return all(state.get(pid) == "current" and record.points[pid].version == order.done_versions.get(pid) for pid in order.realizes)


def ready_orders(record: Record) -> list[Order]:
    done = {o.id for o in record.orders if order_done(record, o)}
    return [o for o in record.orders if o.id not in done and all(a in done for a in o.after)]


def coverage_gaps(record: Record) -> tuple[list[str], list[str]]:
    """Family and job points no order realizes, and manifest entries no order uses."""
    state = states(record)
    realized = {pid for o in record.orders for pid in o.realizes}
    used = {mid for o in record.orders for mid in o.uses}
    built = [pid for pid, p in record.points.items() if p.kind in BUILT_KINDS and state[pid] == "current" and pid not in realized]
    unused = [mid for mid, e in record.manifest.items() if e.owner in record.points and state[e.owner] == "current" and mid not in used]
    return built, unused


def must_not(record: Record, order: Order) -> list[str]:
    """Every exclusion from the points an order builds and everything above them."""
    found: list[str] = []
    for pid in order.realizes:
        for qid in [pid, *reversed(ancestors(record, pid))]:  # nearest first
            answer = record.points[qid].answer
            for item in answer.excludes if answer else []:
                if item not in found:
                    found.append(item)
    return found


# ---- validation ----------------------------------------------------------------------


def _check_sources(record: Record, sources: list[Source], *, need_user: bool = False, need_evidence: bool = False) -> None:
    if not sources:
        raise RecordError("Give at least one source: user, conversation, research, work, derived, or observation.")
    state = states(record)
    request, context = _norm(record.request), _norm(record.context)
    for s in sources:
        if s.kind not in SOURCE_KINDS:
            raise RecordError(f"'{s.kind}' is not a source kind. Use: {', '.join(SOURCE_KINDS)}.")
        if s.kind not in ("user", "conversation", "research") and any(p in _norm(s.ref + " " + s.quote) for p in REFUSED_PHRASES):
            raise RecordError("'Best practice', 'industry standard', 'users expect', and 'common knowledge' are not sources; they are the average describing itself.")
        if s.kind == "user" and (not s.quote.strip() or _norm(s.quote) not in request):
            raise RecordError(f"A user source quotes the person's words exactly, and '{s.quote}' is not in the request.")
        if s.kind == "conversation":
            if not context:
                raise RecordError("No conversation context was given at begin, so there is nothing to quote from.")
            if not s.quote.strip() or _norm(s.quote) not in context:
                raise RecordError(f"A conversation source quotes the context exactly, and '{s.quote}' is not in it.")
        if s.kind == "research" and (not re.match(r"https?://", s.ref.strip()) or not s.quote.strip()):
            raise RecordError("A research source needs the link it came from and the passage quoted from it.")
        if s.kind == "work" and not s.ref.strip():
            raise RecordError("A work source needs an exact reference to the work.")
        if s.kind == "derived":
            ids = [i for i in re.split(r"[\s,]+", s.ref.strip()) if i]
            missing = [i for i in ids if state.get(i) != "current"]
            if not ids or missing:
                raise RecordError(f"A derived source lists the settled points it follows from; {_names(missing) or 'none were given'} are not settled points.")
        if s.kind == "observation" and (not s.ref.strip() or not s.quote.strip()):
            raise RecordError("An observation source says what was observed and what it showed.")
    if need_user and not any(s.kind == "user" for s in sources):
        raise RecordError("The root quotes the person: include a user source with their exact words from the request.")
    if need_evidence and all(s.kind == "derived" for s in sources):
        raise RecordError("A decision that agrees with the average needs evidence specific to this project, not only derivation.")


def _resolvable(ref: str) -> bool:
    ref = ref.strip()
    return bool(re.match(r"https?://", ref)) or bool(re.search(r"@\d", ref)) or "/" in ref or "\\" in ref


def _check_entries(record: Record, owner: str, entries: list[Entry]) -> None:
    seen: set[str] = set()
    for e in entries:
        if not ID.match(e.id):
            raise RecordError(f"'{e.id}' is not a usable manifest id: lowercase letters, digits, '.', '-', '_'.")
        if e.id in seen:
            raise RecordError(f"Manifest entry '{e.id}' appears twice.")
        seen.add(e.id)
        existing = record.manifest.get(e.id)
        if existing and existing.owner != owner:
            raise RecordError(f"'{e.id}' is already in the manifest from '{existing.owner}'. Reuse it instead of adding another.")
        if e.kind == "work" and not _resolvable(e.value):
            raise RecordError(f"Work entry '{e.id}' needs an exact reference: a link, package@version, or path.")
        if e.kind in ("token", "content", "rule") and not e.value.strip():
            raise RecordError(f"Manifest entry '{e.id}' needs its value.")
        if e.kind == "deferred" and (e.value.strip() or not e.note.strip()):
            raise RecordError(f"Deferred entry '{e.id}' has no value yet, and its note is the condition the value must meet.")


def _check_openings(record: Record, settling: str, openings: list[Opening]) -> None:
    state = states(record)
    seen: set[str] = set()
    for o in openings:
        if not ID.match(o.id) or o.id in record.points or o.id in seen:
            raise RecordError(f"'{o.id}' can't be a new point id: it must be new, lowercase letters, digits, '.', '-', '_'.")
        seen.add(o.id)
        if o.kind not in OPENABLE_KINDS:
            raise RecordError(f"'{o.id}' has kind '{o.kind}'; new points are situation, family, job, or tension.")
        if not o.question.strip():
            raise RecordError(f"'{o.id}' needs its question.")
        if o.aspect and o.aspect not in ASPECTS:
            raise RecordError(f"'{o.aspect}' is not an aspect. Aspects: {', '.join(ASPECTS)}.")
        for parent in o.parents or []:
            if parent != settling and state.get(parent) != "current":
                raise RecordError(f"'{o.id}' names parent '{parent}', which is not a settled point.")


def _check_decision(record: Record, point: Point, a: Answer) -> None:
    required = {"situation": a.situation, "average": a.average, "decision": a.decision, "reason": a.reason, "wrong_if": a.wrong_if}
    if point.kind != "root":
        required = {"serves": a.serves, **required}
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise RecordError(f"Answer every question: {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} empty.")
    if _words(a.situation) < 8:
        raise RecordError("The situation says who is there, what they can perceive, what they can do, and what follows. A few words or adjectives are not a situation.")
    if not [x for x in a.excludes if x.strip()]:
        raise RecordError("Name the concrete alternatives this decision excludes. A decision that excludes nothing says nothing.")
    _check_sources(record, a.sources, need_user=point.kind == "root", need_evidence=a.agrees_with_average)
    if point.kind in BUILT_KINDS and not (a.work or a.custom):
        raise RecordError(f"A {point.kind} answers who has already done this: give work, or custom with the reason nothing existing fits.")
    if a.work:
        w = a.work
        if not (w.chosen.strip() and w.license.strip() and w.keep.strip() and w.change.strip() and [x for x in w.examined if x.strip()]):
            raise RecordError("Work names what was examined, the one chosen, its license, what is kept, and what is changed.")
        if not _resolvable(w.chosen):
            raise RecordError("The chosen work needs an exact reference: a link, package@version, or path.")
    if a.custom and not (a.custom.reason.strip() and a.custom.condition.strip()):
        raise RecordError("Custom work needs the reason nothing existing fits and the condition it must meet.")


# ---- moves ---------------------------------------------------------------------------


def begin(request: str, mode: str, questions: list[str] | None = None, context: str = "") -> Record:
    if not request.strip():
        raise RecordError("begin needs the person's request, word for word.")
    if mode not in ("idea", "existing"):
        raise RecordError("mode is 'idea' for a new project or 'existing' for a project that already exists.")
    record = Record(request=request.strip(), mode=mode, context=context.strip())
    record.points["root"] = Point(id="root", kind="root", question=ROOT_QUESTION, raised_by="begin")
    for i, question in enumerate([q.strip() for q in questions or [] if q.strip()], 1):
        record.points[f"q{i}"] = Point(id=f"q{i}", kind="question", question=question, parents=["root"], raised_by="begin")
    return record


def _require(record: Record, *phases: str) -> None:
    if record.phase not in phases:
        raise RecordError(f"The record is in {record.phase}; this belongs to {' or '.join(phases)}. Call next for the current step.")


def _after_derive(record: Record) -> None:
    """Once nothing is open: return to the build when the approval still holds, or ask for a walk."""
    if unsettled(record) or not approval_valid(record):
        return
    built, unused = coverage_gaps(record)
    record.phase = "compile" if built or unused or not record.orders else "build"


def settle(record: Record, point_id: str, gate: str = "decide", answer: Answer | None = None, still_holds: str = "") -> list[str]:
    """Answer one point. Returns the ids of the points it opened."""
    _require(record, "derive")
    point = record.point(point_id)
    state = states(record)
    if state[point.id] not in ("open", "stale"):
        raise RecordError(f"'{point.id}' is {state[point.id]}; only open or stale points are settled. Call next for what is open.")
    waiting = [p for p in point.parents if state.get(p) != "current"]
    if waiting:
        raise RecordError(f"'{point.id}' serves {_names(waiting)}, which must be settled first.")
    answer = answer or Answer()

    if still_holds.strip():
        if state[point.id] != "stale":
            raise RecordError(f"'{point.id}' is not stale; still_holds confirms a settled answer whose parents changed.")
        point.inputs = {p: record.points[p].version for p in point.parents}
        point.notes.append(f"Confirmed: {still_holds.strip()}")
        record.touch()
        _after_derive(record)
        return []

    if gate == "drop":
        if point.kind in ("root", "question"):
            raise RecordError("The root and the person's questions can't be dropped.")
        if not answer.reason.strip():
            raise RecordError("Say why a different answer here would change nothing for the person: reason.")
        for pid in [point.id, *descendants(record, point.id)]:
            record.points[pid].status = "dropped"
            record.points[pid].notes.append(f"Dropped: {answer.reason.strip()}")
        for entry_id in [m for m, e in record.manifest.items() if record.points.get(e.owner) and record.points[e.owner].status == "dropped"]:
            del record.manifest[entry_id]
        point.gate = "drop"
        record.touch()
        _after_derive(record)
        return []

    if gate == "consequence":
        if point.kind == "root":
            raise RecordError("The root is a decision, not a consequence.")
        if not answer.rule.strip():
            raise RecordError("A consequence states the rule that produces it and where the rule comes from: rule.")
        if not answer.manifest:
            raise RecordError("A consequence writes the values its rule yields into the manifest.")
        _check_sources(record, answer.sources)
    elif gate == "decide":
        _check_decision(record, point, answer)
    else:
        raise RecordError("gate is 'decide', 'consequence', or 'drop'.")
    _check_entries(record, point.id, answer.manifest)
    _check_openings(record, point.id, answer.opens)

    if point.answer:
        point.history.append(point.answer)
    for entry_id in [m for m, e in record.manifest.items() if e.owner == point.id and m not in {x.id for x in answer.manifest}]:
        del record.manifest[entry_id]
    for e in answer.manifest:
        previous = record.manifest.get(e.id)
        changed = previous is None or (previous.value, previous.note, previous.kind) != (e.value, e.note, e.kind)
        # a re-answered point's deferred values are observed again on the new build
        record.manifest[e.id] = e.model_copy(update={"owner": point.id, "version": (previous.version + 1 if previous and changed else previous.version if previous else 1)})
    point.answer = answer.model_copy(update={"opens": answer.opens})
    point.gate = gate
    point.status = "settled"
    point.version += 1
    point.inputs = {p: record.points[p].version for p in point.parents}

    opened = []
    for o in answer.opens:
        record.points[o.id] = Point(id=o.id, kind=o.kind, question=o.question.strip(), parents=o.parents or [point.id],
                                    aspect=o.aspect, raised_by=point.id)
        opened.append(o.id)

    if point.raised_by.startswith("gap:"):
        origin = next((o for o in record.orders if o.id == point.raised_by.removeprefix("gap:")), None)
        if origin:
            if point.kind in BUILT_KINDS and point.id not in origin.realizes:
                origin.realizes.append(point.id)
            origin.uses.extend(e.id for e in answer.manifest if e.id not in origin.uses)
    record.touch()
    _after_derive(record)
    return opened


def walk(record: Record, experience: str, construction: str, gaps: list[Opening] | None = None) -> list[str]:
    """Walk the settled graph. Gaps become open points; a clean walk sends the shape to review."""
    _require(record, "derive")
    waiting = unsettled(record)
    if waiting:
        raise RecordError(f"Settle the open points before walking: {_names(waiting)}.")
    if not experience.strip() or not construction.strip():
        raise RecordError("Walk both ways: the experience from the first moment to the purpose, and the construction a builder meets.")
    state = states(record)
    current = {pid: p for pid, p in record.points.items() if state[pid] == "current"}
    named = set(ID_MENTION.findall(experience)) | set(ID_MENTION.findall(construction))
    unknown = sorted(named - set(record.points))
    if unknown:
        raise RecordError(f"The walk names points that don't exist: {_names(unknown)}.")
    missed_situations = [pid for pid, p in current.items() if p.kind == "situation" and pid not in ID_MENTION.findall(experience)]
    missed_built = [pid for pid, p in current.items() if p.kind in BUILT_KINDS and pid not in ID_MENTION.findall(construction)]
    if missed_situations or missed_built:
        parts = []
        if missed_situations:
            parts.append(f"the experience walk must pass through every situation; it skips {_names(missed_situations)}")
        if missed_built:
            parts.append(f"the construction walk must pass through every family and job; it skips {_names(missed_built)}")
        raise RecordError("Name each point as [id]: " + "; ".join(parts) + ".")
    gaps = gaps or []
    for g in gaps:
        if not g.parents:
            raise RecordError(f"Gap '{g.id}' needs the settled points it is open under: parents.")
    _check_openings(record, "", gaps)
    record.walks.append(Walk(experience=experience.strip(), construction=construction.strip()))
    for g in gaps:
        record.points[g.id] = Point(id=g.id, kind=g.kind, question=g.question.strip(), parents=list(g.parents), aspect=g.aspect, raised_by="walk")
    if not gaps:
        if approval_valid(record):
            _after_derive(record)
        else:
            record.phase = "review"
    record.touch()
    return [g.id for g in gaps]


def decide(record: Record, approve: bool, reason: str = "", points: list[str] | None = None) -> None:
    """Record the person's judgment of the shape."""
    _require(record, "review")
    state = states(record)
    if approve:
        record.approved = {pid: p.version for pid, p in record.points.items() if p.kind in APPROVAL_KINDS and state[pid] == "current"}
        record.decisions.append(Decision(approve=True, reason=reason.strip()))
        built, unused = coverage_gaps(record)
        record.phase = "compile" if built or unused or not record.orders else "build"
    else:
        targets = [p.strip() for p in points or [] if p.strip()]
        if not reason.strip() or not targets:
            raise RecordError("A denial records the person's reason and the points it concerns.")
        for pid in targets:
            if state.get(pid) != "current":
                raise RecordError(f"'{pid}' is not a settled point.")
        for pid in targets:
            record.points[pid].status = "open"
            record.points[pid].notes.append(f"Denied by the person: {reason.strip()}")
        record.decisions.append(Decision(approve=False, reason=reason.strip(), points=targets))
        record.phase = "derive"
    record.touch()


def compile_orders(record: Record, orders: list[OrderInput], token_files: list[str] | None = None) -> None:
    """Replace the orders. Orders whose content is unchanged keep their completion."""
    _require(record, "compile")
    state = states(record)
    ids = [o.id.strip() for o in orders]
    if not orders:
        raise RecordError("Compile at least one order.")
    if len(set(ids)) != len(ids) or any(not ID.match(i) for i in ids):
        raise RecordError("Order ids must be unique: lowercase letters, digits, '.', '-', '_'.")
    for o in orders:
        bad = [pid for pid in o.realizes if pid not in record.points or record.points[pid].kind not in BUILT_KINDS or state[pid] != "current"]
        if not o.realizes or bad:
            raise RecordError(f"Order '{o.id}' realizes settled family and job points; {_names(bad) or 'it names none'}.")
        unknown = [m for m in o.uses if m not in record.manifest]
        if unknown:
            raise RecordError(f"Order '{o.id}' uses {_names(unknown)}, which are not in the manifest.")
        missing_after = [a for a in o.after if a not in ids or a == o.id]
        if missing_after:
            raise RecordError(f"Order '{o.id}' waits for {_names(missing_after)}, which are not other orders here.")
        if not [t for t in o.touches if t.strip()] or not o.checks.strip():
            raise RecordError(f"Order '{o.id}' names the files it touches and the check that shows its situations happen.")
    realized = {pid for o in orders for pid in o.realizes}
    used = {m for o in orders for m in o.uses}
    unbuilt = [pid for pid, p in record.points.items() if p.kind in BUILT_KINDS and state[pid] == "current" and pid not in realized]
    unused = [m for m, e in record.manifest.items() if state.get(e.owner) == "current" and m not in used]
    if unbuilt or unused:
        parts = ([f"no order realizes {_names(unbuilt)}"] if unbuilt else []) + ([f"no order uses {_names(unused)}"] if unused else [])
        raise RecordError("Every family and job is built and every manifest entry used: " + "; ".join(parts) + ".")
    # orders form no cycle, and an order that builds on another order's point waits for it
    after = {o.id: set(o.after) for o in orders}
    closure: dict[str, set[str]] = {}

    def reach(oid: str, trail: tuple[str, ...] = ()) -> set[str]:
        if oid in trail:
            raise RecordError(f"Orders wait on each other in a cycle: {' -> '.join((*trail, oid))}.")
        if oid not in closure:
            found: set[str] = set()
            for a in after[oid]:
                found |= {a} | reach(a, (*trail, oid))
            closure[oid] = found
        return closure[oid]

    owner = {pid: o.id for o in orders for pid in o.realizes}
    for o in orders:
        needed = {owner[a] for pid in o.realizes for a in ancestors(record, pid) if a in owner}
        needed |= {owner[record.manifest[m].owner] for m in o.uses if record.manifest[m].owner in owner}
        missing = sorted(needed - reach(o.id) - {o.id})
        if missing:
            raise RecordError(f"Order '{o.id}' builds on points or uses values that {_names(missing)} build; list them in its after.")
    previous = {o.id: o for o in record.orders}
    new_orders = []
    for o in orders:
        kept = previous.get(o.id)
        order = Order(**o.model_dump())
        if kept and kept.done and (kept.realizes, kept.uses, kept.touches) == (order.realizes, order.uses, order.touches):
            order.done, order.done_versions, order.summary, order.evidence = True, kept.done_versions, kept.summary, kept.evidence
        new_orders.append(order)
    record.orders = new_orders
    record.token_files = [t.strip() for t in token_files or [] if t.strip()]
    record.phase = "verify" if not ready_orders(record) else "build"
    record.touch()


def complete(record: Record, order_id: str, summary: str, evidence: str, deferred: dict[str, tuple[str, str]], findings: list) -> None:
    """Mark an order done once its deferred values are set and the scan of its files is clean."""
    _require(record, "build")
    order = record.order(order_id)
    if order.id not in {o.id for o in ready_orders(record)}:
        raise RecordError(f"'{order.id}' is not ready: it is done, or it waits for {_names(order.after)}.")
    if not summary.strip() or not evidence.strip():
        raise RecordError("Say what was built (summary) and what you observed that shows it works (evidence).")
    for mid, (value, observation) in deferred.items():
        entry = record.manifest.get(mid)
        if not entry or entry.kind != "deferred" or mid not in order.uses:
            raise RecordError(f"'{mid}' is not a deferred entry this order uses.")
        if not value.strip() or not observation.strip():
            raise RecordError(f"Deferred '{mid}' needs the value you set and the observation that settled it.")
    unset = [m for m in order.uses if record.manifest[m].kind == "deferred" and not record.manifest[m].value and m not in deferred]
    if unset:
        raise RecordError(f"Set the deferred values this order uses, each with the observation that settled it: {_names(unset)}.")
    if findings:
        lines = "\n".join(f"{f.path}:{f.line}: {f.literal} ({f.kind})" for f in findings[:40])
        more = f"\n...and {len(findings) - 40} more" if len(findings) > 40 else ""
        raise RecordError(
            "These values in the files this order touched did not come from the manifest. Refer to manifest values through the "
            f"token files, or raise a gap if the record never settled them:\n{lines}{more}"
        )
    for mid, (value, observation) in deferred.items():
        record.manifest[mid].value, record.manifest[mid].observation = value.strip(), observation.strip()
    order.done = True
    order.done_versions = {pid: record.points[pid].version for pid in order.realizes}
    order.summary, order.evidence = summary.strip(), evidence.strip()
    if not ready_orders(record):
        record.phase = "verify"
    record.touch()


def gap(record: Record, order_id: str, opening: Opening) -> None:
    """Something the order does not cover becomes an open point instead of a choice."""
    _require(record, "build")
    order = record.order(order_id)
    if not opening.parents:
        raise RecordError("A gap names the settled points it is open under: parents.")
    _check_openings(record, "", [opening])
    record.points[opening.id] = Point(id=opening.id, kind=opening.kind, question=opening.question.strip(),
                                      parents=list(opening.parents), aspect=opening.aspect, raised_by=f"gap:{order.id}")
    record.phase = "derive"
    record.touch()


def revise(record: Record, point_id: str, reason: str) -> list[str]:
    """Reopen a settled point an observation has undermined. Returns the points that become stale."""
    if record.phase == "review":
        raise RecordError("The shape is waiting for the person's decision; a denial reopens points.")
    if not reason.strip():
        raise RecordError("Say what observation shows the point is wrong: reason.")
    point = record.point(point_id)
    if states(record)[point.id] != "current":
        raise RecordError(f"'{point.id}' is not settled and current, so there is nothing to revise.")
    affected = [pid for pid in descendants(record, point.id) if states(record)[pid] == "current"]
    point.status = "open"
    point.notes.append(f"Revised: {reason.strip()}")
    record.phase = "derive"
    record.touch()
    return affected


def verify(record: Record, walk_text: str, evidence: str, review: str, findings: list) -> None:
    _require(record, "verify")
    built, unused = coverage_gaps(record)
    pending = [o.id for o in record.orders if not order_done(record, o)]
    unset = [m for m, e in record.manifest.items() if e.kind == "deferred" and not e.value]
    problems = []
    if built or unused:
        problems.append(f"not everything is built: {_names(built + unused)}")
    if pending:
        problems.append(f"orders not done: {_names(pending)}")
    if unset:
        problems.append(f"deferred values never set: {_names(unset)}")
    if findings:
        problems.append("values in the product that did not come from the manifest:\n" + "\n".join(f"{f.path}:{f.line}: {f.literal} ({f.kind})" for f in findings[:40]))
    if problems:
        raise RecordError("The traces are not clean: " + "; ".join(problems))
    state = states(record)
    situations = [pid for pid, p in record.points.items() if p.kind == "situation" and state[pid] == "current"]
    missed = [pid for pid in situations if pid not in ID_MENTION.findall(walk_text)]
    if missed:
        raise RecordError(f"Walk the built product through every situation, naming each as [id]; the walk skips {_names(missed)}.")
    if not evidence.strip():
        raise RecordError("Say what you observed with your tools on the built product: evidence.")
    if not review.strip():
        raise RecordError("Record who reviewed the product without having built it, and what they found: review.")
    record.verification = Verification(walk=walk_text.strip(), evidence=evidence.strip(), review=review.strip())
    record.phase = "done"
    record.touch()


# ---- storage -------------------------------------------------------------------------


class Store:
    """The record and its views live in .coherence/ inside the project."""

    def __init__(self, project: Path):
        self.project = project.resolve()
        self.dir = self.project / ".coherence"
        self.record_path = self.dir / "record.json"
        self.shape_path = self.dir / "shape.md"
        self.steps_path = self.dir / "steps.jsonl"
        self.packet_path = self.dir / "packet.txt"

    def _write(self, path: Path, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def exists(self) -> bool:
        return self.record_path.is_file()

    def load(self) -> Record:
        if not self.exists():
            raise RecordError(f"No record in {self.project}. Call begin with the person's request.")
        try:
            return Record.model_validate_json(self.record_path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise RecordError(f"The record in {self.record_path} can't be read: {error}") from None

    def save(self, record: Record) -> None:
        self._write(self.record_path, record.model_dump_json(indent=2))

    def archive(self) -> Path:
        target = self.dir / f"record.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
        os.replace(self.record_path, target)
        return target

    def write_shape(self, text: str) -> None:
        self._write(self.shape_path, text)

    def last_packet(self) -> str:
        return self.packet_path.read_text(encoding="utf-8") if self.packet_path.is_file() else ""

    def set_packet(self, text: str) -> None:
        self._write(self.packet_path, text)

    def log(self, entry: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.steps_path.open("a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
