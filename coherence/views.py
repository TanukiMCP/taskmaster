"""What the server hands the agent: one packet per step, and the shape the person reads.

Each packet is computed from the record, so the agent gets exactly what the step depends
on: no less, so nothing is defaulted, and no more, so it is not buried.
"""

from __future__ import annotations

import os

from .library import Library
from .record import (
    BUILT_KINDS,
    ID_MENTION,
    Order,
    Point,
    Record,
    ancestors,
    coverage_gaps,
    descendants,
    must_not,
    order_done,
    ready_orders,
    ready_points,
    risk,
    states,
    unsettled,
)

CONTEXT_LIMIT = 6000


def _budget() -> int:
    """The packet budget in characters (COHERENCE_PACKET_TOKENS, about four characters a token); 0 means none."""
    try:
        return max(0, int(os.environ.get("COHERENCE_PACKET_TOKENS", "0"))) * 4
    except ValueError:
        return 0


def _first_sentence(text: str) -> str:
    cut = text.find(". ")
    return text if cut < 0 else text[: cut + 1]


def _fit(required: list[str], optional: list[tuple[str, list[str]]], tail: list[str]) -> list[str]:
    """Keep every required and tail part, then add optional sections line by line while the budget allows.

    Each optional section is (heading, lines). What doesn't fit is named at the end so the agent knows it was left out.
    """
    budget = _budget()
    if not budget:
        return required + [part for heading, lines in optional if lines for part in (heading, "\n".join(lines))] + tail
    parts = list(required)
    used = sum(len(p) + 2 for p in required + tail) + 200  # room for the note naming what was left out
    left_out: list[str] = []
    for heading, lines in optional:
        kept: list[str] = []
        for line in lines:
            cost = len(line) + 1 + (len(heading) + 2 if not kept else 0)
            if used + cost > budget:
                break
            kept.append(line)
            used += cost
        if kept:
            parts += [heading, "\n".join(kept)]
        if len(kept) < len(lines):
            left_out.append(f"{len(lines) - len(kept)} of {len(lines)} from '{heading.lstrip('# ')}'")
    if left_out:
        parts.append("Left out to fit the packet budget: " + "; ".join(left_out) + ".")
    return parts + tail


def _counts(record: Record) -> str:
    state = states(record)
    settled = sum(1 for s in state.values() if s == "current")
    waiting = sum(1 for s in state.values() if s in ("open", "stale"))
    text = f"Phase: {record.phase}. Points: {settled} settled, {waiting} open."
    if record.orders:
        done = sum(1 for o in record.orders if order_done(record, o))
        text += f" Orders: {done} of {len(record.orders)} done."
    return text


def _brief(point: Point) -> str:
    a = point.answer
    if not a:
        return f"[{point.id}] {point.kind}: {point.question} (open)"
    if point.gate == "consequence":
        return f"[{point.id}] {point.kind}: {point.question} → consequence of: {a.rule}"
    text = f"[{point.id}] {point.kind}: {a.decision}"
    if a.excludes:
        text += f" (excludes: {'; '.join(a.excludes)})"
    return text


def _full(point: Point) -> str:
    a = point.answer
    if not a:
        return _brief(point)
    if point.gate == "consequence":
        return f"[{point.id}] {point.kind}: {point.question}\nRule: {a.rule}"
    lines = [f"[{point.id}] {point.kind}: {point.question}", f"Situation: {a.situation}", f"Average version: {a.average}",
             f"Decision: {a.decision}", f"Excludes: {'; '.join(a.excludes)}", f"Reason: {a.reason}"]
    if a.work:
        lines.append(f"Work: {a.work.chosen} ({a.work.license}). Keeps: {a.work.keep}. Changes: {a.work.change}.")
    if a.custom:
        lines.append(f"Custom: {a.custom.reason}. Condition: {a.custom.condition}.")
    lines.append(f"Wrong if: {a.wrong_if}")
    return "\n".join(lines)


def _entry(e) -> str:
    if e.kind == "deferred":
        value = f"set to {e.value} ({e.observation})" if e.value else "not set yet"
        return f"{e.id} (deferred, {value}). Condition: {e.note}"
    text = f"{e.id} ({e.kind}): {e.value}"
    if e.note:
        text += f". {e.note}"
    if e.paths:
        text += f". Lives in: {', '.join(e.paths)}"
    return text


def _request(record: Record) -> list[str]:
    parts = ["## The person's request, word for word", record.request]
    questions = [p for p in record.points.values() if p.kind == "question"]
    if questions:
        parts += ["## Their questions", "\n".join(f"[{q.id}] {q.question}" for q in questions)]
    if record.context:
        context = record.context if len(record.context) <= CONTEXT_LIMIT else record.context[:CONTEXT_LIMIT] + "\n[...context continues]"
        parts += ["## Conversation context (quote it exactly in conversation sources)", context]
    return parts


SETTLE_FORM = (
    "Call settle with point='{id}' and gate:\n"
    "- gate='drop' with reason, if a different answer would change nothing for the person.\n"
    "- gate='consequence' with rule, sources, and manifest, if only one answer is defensible given what is settled.\n"
    "- gate='decide' otherwise, answering in order: serves; situation (who is there, what they perceive, what they can do, what "
    "follows; not adjectives, jargon, or measurements); average (what the average version of this kind of project does here, "
    "before deciding); decision, excludes, reason, agrees_with_average; work (examined, chosen exact reference, license, keep, "
    "change) or custom (reason, condition){built}; wrong_if; opens (new points with id, kind, question). Also confidence, "
    "sources (user and conversation quotes must be exact; research needs a link and a passage; derived names settled points), "
    "and manifest entries for every concrete value the build will need."
)


def derive_packet(lib: Library, record: Record, point: Point) -> str:
    state = states(record)
    label = state[point.id]
    if label == "open" and point.answer:
        label = "reopened"
    parts = [f"# Point [{point.id}] ({point.kind}, {label})", _counts(record), f"Question: {point.question}"]
    if point.notes:
        parts.append(f"Note: {point.notes[-1]}")
    if label == "stale":
        changed = [p for p in point.parents if point.inputs.get(p) != record.points[p].version]
        parts.append(f"Its parents changed since it was answered ({', '.join(changed)}). Answer again, or confirm with still_holds if the answer still holds.")
    if point.answer:
        parts += ["## Its previous answer", _full(point)]
    parts += _request(record)
    root = record.points["root"]
    if point.id != "root" and root.answer:
        parts += ["## The root", _full(root)]
    chain = [record.points[pid] for pid in ancestors(record, point.id) if pid != "root" and pid not in point.parents]
    parents = [record.points[pid] for pid in point.parents if pid != "root"]
    siblings = [p for p in record.points.values()
                if p.id != point.id and state[p.id] == "current" and set(p.parents) & set(point.parents)]
    above = set(ancestors(record, point.id))
    entries = [e for e in record.manifest.values() if e.owner in above]
    built = "; families and jobs must answer this" if point.kind in BUILT_KINDS else ""
    if point.kind == "root":
        built = "; the root must quote the person with a user source"
    tail = ["## Now", SETTLE_FORM.format(id=point.id, built=built)]
    chain_head = "## Above it, toward the root"
    sibling_head = "## Settled beside it (stay consistent with these)"
    entry_head = "## Manifest entries already settled above it (reuse them; don't add near-duplicates)"
    if _budget():
        if parents:
            parts += ["## What it serves", "\n\n".join(_full(p) for p in parents)]
        guidance = [f"## Guidance: design/{point.aspect}", [lib.guidance(point.aspect)]] if point.aspect else ["", []]
        return "\n\n".join(_fit(parts, [
            (chain_head, [_brief(p) for p in chain]),
            (sibling_head, [_first_sentence(_brief(p)) for p in reversed(siblings)]),
            (entry_head, [_entry(e) for e in entries]),
            (guidance[0], guidance[1]),
        ], tail))
    if chain:
        parts += [chain_head, "\n".join(_brief(p) for p in chain)]
    if parents:
        parts += ["## What it serves", "\n\n".join(_full(p) for p in parents)]
    if siblings:
        parts += [sibling_head, "\n".join(_brief(p) for p in siblings)]
    if entries:
        parts += [entry_head, "\n".join(_entry(e) for e in entries)]
    if point.aspect:
        parts += [f"## Guidance: design/{point.aspect}", lib.guidance(point.aspect)]
    return "\n\n".join(parts + tail)


def walk_packet(record: Record) -> str:
    state = states(record)
    current = [p for p in record.points.values() if state[p.id] == "current"]
    situations = [p for p in current if p.kind == "situation"]
    built = [p for p in current if p.kind in BUILT_KINDS]
    parts = ["# Walk the record", _counts(record),
             "Nothing is open. Walk it both ways to find what is still undetermined. The experience walk follows a person from the "
             "first moment they meet the product to the moment the purpose is met; the construction walk follows a builder through "
             "what has to exist. Name each point you pass through as [id]. Wherever the settled points don't determine what happens "
             "next, report a gap (id, kind, question, parents)."]
    parts += _request(record)
    tail = ["## The experience walk must name", ", ".join(f"[{p.id}]" for p in situations) or "(no situations yet: that is a gap)",
            "## The construction walk must name", ", ".join(f"[{p.id}]" for p in built) or "(no families or jobs yet: that is a gap)",
            "## Now", "Call walk(experience=..., construction=..., gaps=[...]). A walk with no gaps sends the shape to the person."]
    if _budget():
        return "\n\n".join(_fit(parts, [("## Settled points", [_first_sentence(_brief(p)) for p in current])], tail))
    parts += ["## Settled points", "\n".join(_brief(p) for p in current)]
    return "\n\n".join(parts + tail)


def render_shape(record: Record) -> str:
    """The shape the person approves or denies: a view of the record, not a document the agent writes."""
    state = states(record)
    current = {pid: p for pid, p in record.points.items() if state[pid] == "current"}
    root = record.points["root"]

    def strip(text: str) -> str:
        return ID_MENTION.sub(lambda m: "", text).replace("  ", " ")

    def given(point: Point) -> bool:
        return any(s.kind in ("user", "conversation") for s in point.answer.sources) if point.answer else False

    parts = ["# The shape", "## What you asked for", record.request]
    if root.answer:
        a = root.answer
        parts += ["## What this is for", f"{a.situation}\n\n{a.decision}\n\nIt refuses to be: {'; '.join(a.excludes)}."]
    if record.walks:
        parts += ["## What it will be like", strip(record.walks[-1].experience)]
    questions = [p for p in current.values() if p.kind == "question"]
    if questions:
        parts += ["## Your questions", "\n\n".join(f"{q.question}\n{q.answer.decision}" for q in questions if q.answer)]
    families = [p for p in current.values() if p.kind == "family" and p.answer]
    if families:
        lines = []
        for f in families:
            if f.answer.work:
                w = f.answer.work
                lines.append(f"{f.question}\n{f.answer.decision} — {w.chosen} ({w.license}). Kept: {w.keep}. Changed: {w.change}.")
            else:
                lines.append(f"{f.question}\n{f.answer.decision} — made for this project: {f.answer.custom.reason}")
        parts += ["## What it's built from", "\n\n".join(lines)]
    tensions = [p for p in current.values() if p.kind == "tension" and p.answer]
    if tensions:
        parts += ["## Tensions and how they're resolved", "\n\n".join(f"{t.answer.situation}\n{t.answer.decision}" for t in tensions)]
    risky = [p for _, p in risk(record)[:5]]
    if risky:
        parts += ["## The calls most likely to be wrong",
                  "\n\n".join(f"{p.answer.decision} ({p.answer.confidence} confidence, {len(descendants(record, p.id))} things built on it)\n"
                              f"Why: {p.answer.reason}\nWrong if: {p.answer.wrong_if}" for p in risky)]
    spoke = [p for p in current.values() if p.kind in ("situation", "family", "tension") and p.answer and not given(p)]
    if spoke:
        parts += ["## Where it spoke for you", "These decisions at the level you approve cite none of your words:\n\n" +
                  "\n".join(f"{p.answer.decision}" for p in spoke)]
    deferred = [e for e in record.manifest.values() if e.kind == "deferred" and not e.value]
    if deferred:
        parts += ["## Settled during the build, by looking", "\n".join(f"{e.id}: {e.note}" for e in deferred)]
    if record.phase == "done" and record.verification:
        v = record.verification
        parts += ["## Built and checked", f"{strip(v.walk)}\n\nEvidence: {v.evidence}\n\nReviewed by: {v.review}"]
    else:
        parts += ["## Your decision", "Approve this, or say what's wrong. A denial reopens only what it touches."]
    parts.append(f"The full record is in .coherence/record.json ({len(current)} settled points, {len(record.manifest)} manifest entries).")
    return "\n\n".join(parts) + "\n"


def review_packet(record: Record) -> str:
    return "\n\n".join([
        "# Review", _counts(record),
        "The shape is written to .coherence/shape.md. Show it to the person exactly as it is and ask them to approve it or say "
        "what's wrong. Then call decide(approve=true), or decide(approve=false, reason=<their words>, points=[the points their "
        "reason concerns]). Do not decide for them.",
        "## The shape", render_shape(record),
    ])


def compile_packet(record: Record) -> str:
    state = states(record)
    built = [p for p in record.points.values() if p.kind in BUILT_KINDS and state[p.id] == "current"]
    lines = []
    for p in built:
        a = p.answer
        source = f"work {a.work.chosen}" if a and a.work else f"custom: {a.custom.condition}" if a and a.custom else "consequence"
        lines.append(f"[{p.id}] {p.kind} under {', '.join(p.parents)}: {a.decision if a and a.decision else a.rule if a else ''} ({source})")
    missing, unused = coverage_gaps(record)
    parts = ["# Compile the orders", _counts(record),
             "Approved. Turn the record into orders. Each order realizes a group of family and job points, uses the manifest entries "
             "it needs, lists the orders that must finish first (an order that builds on another order's point must wait for it), "
             "names the files it will touch, and states the check that shows its situations now happen. Every family and job must "
             "be realized and every manifest entry used. Name the token files where manifest values will be written; they are the "
             "only files where literal values may live."]
    parts += ["## Families and jobs to build", "\n".join(lines)]
    parts += ["## Manifest entries to use", "\n".join(_entry(e) for e in record.manifest.values())]
    if record.orders and (missing or unused):
        parts += ["## Not covered by the current orders", ", ".join(missing + unused)]
    parts += ["## Now", "Call compile(orders=[{id, realizes, uses, after, touches, checks}], token_files=[...]). "
                        "Orders unchanged from a previous compilation keep their completion."]
    return "\n\n".join(parts)


def build_packet(lib: Library, record: Record, order: Order) -> str:
    points = [record.points[pid] for pid in order.realizes]
    above = [record.points[pid] for pid in record.points if pid in {a for p in points for a in ancestors(record, p.id)}]
    parts = [f"# Order [{order.id}]", _counts(record), f"Touches: {', '.join(order.touches)}", f"Check: {order.checks}"]
    parts += ["## What it builds", "\n\n".join(_full(p) for p in points)]
    serve_head = "## What they serve, up to the root"
    if not _budget():
        parts += [serve_head, "\n".join(_brief(p) for p in above)]
    entries = [record.manifest[m] for m in order.uses if m in record.manifest]
    parts += ["## Manifest entries it may use (and nothing else)", "\n".join(_entry(e) for e in entries) or "(none)"]
    exclusions = must_not(record, order)
    if exclusions:
        parts += ["## It must not", "\n".join(exclusions)]
    if record.token_files:
        parts += ["## Token files (the only place literal values may live)", "\n".join(record.token_files)]
    aspects = []
    for p in points:
        if p.aspect and p.aspect not in aspects:
            aspects.append(p.aspect)
    if _budget():
        parts = _fit(parts, [(serve_head, [_first_sentence(_brief(p)) for p in above])] +
                     [(f"## Guidance: design/{aspect}", lib.guidance(aspect).split("\n")) for aspect in aspects], [])
        aspects = []
    for aspect in aspects:
        parts += [f"## Guidance: design/{aspect}", lib.guidance(aspect)]
    parts += ["## Now",
              "Build exactly this, using only the manifest entries above, written into the token files and referred to by name "
              "everywhere else. Never put a literal color, size, duration, font, or media file in code. Settle each deferred entry "
              "by looking at the built thing against its condition. Then call complete(order='" + order.id + "', summary, evidence, "
              "deferred=[{id, value, observation}]); the server scans the files this order touched. If something here is not "
              "covered, call gap instead of choosing. If an observation shows a settled point is wrong, call revise."]
    return "\n\n".join(parts)


def verify_packet(record: Record, findings: list) -> str:
    state = states(record)
    situations = [p for p in record.points.values() if p.kind == "situation" and state[p.id] == "current"]
    parts = ["# Verify", _counts(record)]
    if findings:
        parts += ["## The server's scan found untraced values", "\n".join(f"{f.path}:{f.line}: {f.literal} ({f.kind})" for f in findings[:40])]
    else:
        parts.append("The server's scan of every file the orders touched is clean.")
    parts += ["## Now",
              "Walk the built product with your tools, from the first moment toward the purpose, naming every situation as [id] "
              "and what you observed: " + ", ".join(f"[{p.id}]" for p in situations) + ". Then have someone who did not build it, "
              "a fresh agent or the person, compare the product with .coherence/shape.md. Call verify(walk, evidence, review)."]
    return "\n\n".join(parts)


def done_packet(record: Record) -> str:
    return "\n\n".join(["# Done", _counts(record), "The product is built, traced both ways, walked, and reviewed. The shape with the "
                        "verification is in .coherence/shape.md. Revise a point to change anything; exactly what depends on it reopens."])


def packet(lib: Library, record: Record, findings: list | None = None) -> str:
    """The current step, whatever phase the record is in."""
    if record.phase == "derive":
        ready = ready_points(record)
        if ready:
            return derive_packet(lib, record, ready[0])
        if unsettled(record):
            return f"# Waiting\n\n{_counts(record)}\n\nOpen points wait on others: {', '.join(unsettled(record))}."
        return walk_packet(record)
    if record.phase == "review":
        return review_packet(record)
    if record.phase == "compile":
        return compile_packet(record)
    if record.phase == "build":
        ready = ready_orders(record)
        return build_packet(lib, record, ready[0]) if ready else "# Build\n\nNo order is ready; call next."
    if record.phase == "verify":
        return verify_packet(record, findings or [])
    return done_packet(record)

