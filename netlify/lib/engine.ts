// Operations, what each one needs, and whether its output is current. Mirrors taskmaster/engine.py:
// it keeps outputs, refuses work whose inputs are missing or stale, and never judges the work itself.

import { ID_PATTERN } from "./library.ts";

export class EngineError extends Error {}

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const names = (ids: string[]) => ids.map((i) => `'${i}'`).join(", ");

export interface OperationInput {
  id: string;
  needs?: string[];
  does?: string;
  produces?: string;
  guide?: string;
}

export interface Note {
  text: string;
  at: string;
}

export interface Result {
  version: number;
  output: string;
  check: string; // how the output was tested against the value: a check that could have failed
  assumptions: string[];
  evidence: string;
  inputs: Record<string, number>; // each needed operation's version this result was built on
  purpose: number; // the session's purpose version this result was built for
  at: string;
}

export interface Operation {
  id: string;
  needs: string[];
  does: string;
  produces: string;
  guide: string;
  open: boolean;
  results: Result[];
  notes: Note[];
}

export interface Session {
  id: string;
  created: string;
  updated: string;
  request: string;
  questions: string[];
  result: string;
  value: string;
  starting: string;
  purpose: number;
  operations: Operation[];
  retired: Operation[];
  log: Note[];
  status: "active" | "finished";
  delivered: string;
  evidence: string;
  review: string;
  answers: string[];
  limitations: string;
}

export type State = "current" | "stale" | "open";

const note = (text: string): Note => ({ text, at: now() });
export const latest = (op: Operation): Result | null => op.results.at(-1) ?? null;
export const version = (op: Operation) => latest(op)?.version ?? 0;
const touch = (session: Session) => {
  session.updated = now();
};

export function operation(session: Session, opId: string): Operation {
  const found = session.operations.find((op) => op.id === opId.trim());
  if (found) return found;
  const known = session.operations.map((op) => op.id).join(", ") || "none yet; call compose";
  throw new EngineError(`No operation '${opId}' in this session. Operations: ${known}.`);
}

// Current: recorded on inputs that are themselves current and unchanged. Stale: recorded, but
// something it was built on has changed. Open: not recorded, or reopened.
export function states(session: Session): Record<string, State> {
  const versions = Object.fromEntries(session.operations.map((op) => [op.id, version(op)]));
  const state: Record<string, State> = {};
  for (const op of session.operations) {
    const last = latest(op);
    if (op.open || !last) state[op.id] = "open";
    else if (last.purpose === session.purpose && op.needs.every((n) => state[n] === "current" && last.inputs[n] === versions[n])) state[op.id] = "current";
    else state[op.id] = "stale";
  }
  return state;
}

// Operations that are not current and whose needs all are, in composition order.
export function ready(session: Session, state = states(session)): Operation[] {
  return session.operations.filter((op) => state[op.id] !== "current" && op.needs.every((n) => state[n] === "current"));
}

// Everything an operation builds on, directly or through other operations, in composition order.
export function upstream(session: Session, opId: string): Operation[] {
  const byId = new Map(session.operations.map((op) => [op.id, op]));
  const found = new Set<string>();
  const pending = [...byId.get(opId)!.needs];
  while (pending.length) {
    const n = pending.pop()!;
    if (!found.has(n)) {
      found.add(n);
      pending.push(...byId.get(n)!.needs);
    }
  }
  return session.operations.filter((op) => found.has(op.id));
}

// Everything built on an operation, directly or through other operations, in composition order.
export function downstream(session: Session, opId: string): Operation[] {
  const found = new Set([opId]);
  const builtOn: Operation[] = [];
  for (const op of session.operations) {
    if (op.needs.some((n) => found.has(n))) {
      found.add(op.id);
      builtOn.push(op);
    }
  }
  return builtOn;
}

// Why a stale operation is stale.
export function changedInputs(session: Session, op: Operation): string[] {
  const last = latest(op);
  if (!last) return [];
  const state = states(session);
  const reasons: string[] = [];
  if (last.purpose !== session.purpose) reasons.push("the value or the requested result changed");
  for (const n of op.needs) {
    const dep = operation(session, n);
    const was = last.inputs[n] ?? 0;
    if (was !== version(dep)) reasons.push(`'${n}' changed (v${was} → v${version(dep)})`);
    else if (state[n] !== "current") reasons.push(`'${n}' is ${state[n]}`);
  }
  return reasons;
}

export function newSession(request: string, result: string, value: string, starting = "", questions: string[] = []): Session {
  for (const [name, text] of [["request", request], ["result", result], ["value", value]]) {
    if (!text.trim()) throw new EngineError(`start needs ${name}.`);
  }
  const stamp = now();
  return {
    id: crypto.randomUUID().replace(/-/g, "").slice(0, 12),
    created: stamp,
    updated: stamp,
    request: request.trim(),
    questions: questions.map((q) => q.trim()).filter(Boolean),
    result: result.trim(),
    value: value.trim(),
    starting: starting.trim(),
    purpose: 1,
    operations: [],
    retired: [],
    log: [],
    status: "active",
    delivered: "",
    evidence: "",
    review: "",
    answers: [],
    limitations: "",
  };
}

const isAre = (ids: string[]) => (ids.length === 1 ? "is" : "are");

// Set or revise the operations. Returns the ids reopened by the revision, a line for each change
// to an existing operation, and any warnings. An item with only an id keeps that existing operation
// as it is. A recorded operation whose needs or output change is reopened. An operation leaves the
// composition only when it is named in remove; leaving it out of the list is refused, so nothing is
// dropped silently.
export function compose(session: Session, items: OperationInput[], reason = "", remove: string[] = []): [string[], string[], string[]] {
  if (!items.length) throw new EngineError("A composition needs at least one operation.");
  const existing = new Map(session.operations.map((op) => [op.id, op]));
  if (existing.size && !reason.trim()) throw new EngineError("This session already has a composition. Say why it changes: reason.");
  const listed = new Set(items.map((item) => item.id.trim()));
  const removing = remove.map((r) => r.trim());
  const unknown = removing.filter((r) => !existing.has(r));
  if (unknown.length) throw new EngineError(`remove names ${names(unknown)}, which ${isAre(unknown)} not in the composition.`);
  const leftOut = [...existing.keys()].filter((id) => !listed.has(id) && !removing.includes(id));
  if (leftOut.length) {
    throw new EngineError(
      `${names(leftOut)} ${isAre(leftOut)} missing from the list. Keep ${leftOut.length === 1 ? "it" : "them"} ` +
        "(an item with only the id keeps an operation as it is), or name it in remove and say in reason why it is no longer needed.",
    );
  }
  const keptAndRemoved = removing.filter((r) => listed.has(r));
  if (keptAndRemoved.length) throw new EngineError(`${names(keptAndRemoved)} ${isAre(keptAndRemoved)} both listed and named in remove.`);

  const placed = new Map<string, Operation>();
  const reopened: string[] = [];
  const changes: string[] = [];
  for (const item of items) {
    const opId = item.id.trim();
    if (!ID_PATTERN.test(opId)) throw new EngineError(`'${item.id}' is not a usable id: use lowercase letters, digits, '.', '-', and '_'.`);
    if (placed.has(opId)) throw new EngineError(`'${opId}' appears twice.`);
    const old = existing.get(opId);
    let op: Operation;
    if (item.needs === undefined && !(item.does?.trim() || item.produces?.trim() || item.guide?.trim())) {
      if (!old) throw new EngineError(`'${opId}' is new, so it needs does and produces.`);
      op = structuredClone(old);
    } else {
      const needs = (item.needs ?? []).map((n) => n.trim());
      const does = (item.does ?? "").trim();
      const produces = (item.produces ?? "").trim();
      if (!does) throw new EngineError(`'${opId}' needs does: the specific work it does for this task and the questions it must answer.`);
      if (!produces) throw new EngineError(`'${opId}' needs produces: the concrete output the operations after it use.`);
      if (new Set(needs).size !== needs.length) throw new EngineError(`'${opId}' lists the same need twice.`);
      if (!old) {
        op = { id: opId, needs, does, produces, guide: (item.guide ?? "").trim(), open: true, results: [], notes: [] };
      } else {
        op = structuredClone(old);
        const fields: Array<[string, string, string]> = [
          ["needs", op.needs.join(", ") || "nothing", needs.join(", ") || "nothing"],
          ["does", op.does, does],
          ["produces", op.produces, produces],
        ];
        for (const [name, before, after] of fields) if (before !== after) changes.push(`'${opId}' ${name} was: ${before}\n  now: ${after}`);
        const sameNeeds = needs.length === op.needs.length && needs.every((n) => op.needs.includes(n));
        if (op.results.length && !op.open && (!sameNeeds || produces !== op.produces)) {
          op.open = true;
          op.notes.push(note(`Reopened by recomposition: ${reason.trim()}`));
          reopened.push(opId);
        }
        Object.assign(op, { needs, does, produces, guide: (item.guide ?? "").trim() });
      }
    }
    for (const n of op.needs) {
      if (n === opId) throw new EngineError(`'${opId}' can't need itself.`);
      if (!placed.has(n)) {
        const where = listed.has(n) ? "is listed after it" : "is not in the composition";
        throw new EngineError(`'${opId}' needs '${n}', which ${where}. List every operation after the operations it needs.`);
      }
    }
    placed.set(opId, op);
  }

  for (const opId of removing) {
    const op = existing.get(opId)!;
    op.notes.push(note(`Removed from the composition: ${reason.trim()}`));
    session.retired.push(op);
    changes.push(`'${opId}' removed; it produced: ${op.produces}`);
  }
  session.operations = [...placed.values()];
  session.log.push(note(existing.size ? [`Recomposed: ${reason.trim()}`, ...changes].join("\n") : `Composed ${placed.size} operations`));
  if (session.status === "finished") session.status = "active";
  touch(session);

  const used = new Set(session.operations.flatMap((op) => op.needs));
  const loose = session.operations.slice(0, -1).filter((op) => !used.has(op.id)).map((op) => op.id);
  const warnings = loose.length
    ? [`Nothing needs the output of ${names(loose)}. Every operation should feed later work or be the requested result; connect it or drop it.`]
    : [];
  return [reopened, changes, warnings];
}

function requireActive(session: Session): void {
  if (session.status === "finished") {
    throw new EngineError(`Session ${session.id} is finished. Call compose with a reason to reopen it, or start a new session.`);
  }
  if (!session.operations.length) throw new EngineError("There are no operations yet. Derive them and call compose.");
}

export interface RecordInput {
  output?: string;
  check?: string;
  assumptions?: string[];
  evidence?: string;
  still_holds?: string;
}

// Store an operation's output, or confirm that a stale output still holds.
export function record(session: Session, opId: string, input: RecordInput): "recorded" | "confirmed" {
  requireActive(session);
  const op = operation(session, opId);
  const state = states(session);
  const waiting = op.needs.filter((n) => state[n] !== "current");
  if (waiting.length) {
    throw new EngineError(
      `'${op.id}' can't be recorded yet: it needs ${names(waiting)}, which ${waiting.length === 1 ? "is" : "are"} not current. ` +
        `Work on '${ready(session, state)[0].id}' first.`,
    );
  }
  const inputs = Object.fromEntries(op.needs.map((n) => [n, version(operation(session, n))]));
  const stillHolds = (input.still_holds ?? "").trim();
  if (stillHolds) {
    const last = latest(op);
    if (!last) throw new EngineError(`'${op.id}' has no earlier output to confirm. Record its output.`);
    if (state[op.id] === "current") throw new EngineError(`'${op.id}' is already current; there is nothing to confirm.`);
    last.inputs = inputs;
    last.purpose = session.purpose;
    op.open = false;
    op.notes.push(note(`Confirmed v${last.version} still holds: ${stillHolds}`));
    touch(session);
    return "confirmed";
  }
  if (state[op.id] === "current") throw new EngineError(`'${op.id}' is already current. If its output has to change, revise it first and say why.`);
  const output = (input.output ?? "").trim();
  const check = (input.check ?? "").trim();
  if (!output) throw new EngineError(`Record the actual output of '${op.id}': ${op.produces}`);
  if (!check) {
    throw new EngineError(
      `Say how this output was checked against the value: ${session.value} Name a check that could have failed and ` +
        "what it showed. That the output exists, or fits the request or a reference, is not a check. If it fails, " +
        "change the work, or revise the value itself and say why.",
    );
  }
  op.results.push({
    version: version(op) + 1,
    output,
    check,
    assumptions: (input.assumptions ?? []).map((a) => a.trim()).filter(Boolean),
    evidence: (input.evidence ?? "").trim(),
    inputs,
    purpose: session.purpose,
    at: now(),
  });
  op.open = false;
  touch(session);
  return "recorded";
}

// Reopen an operation, or change the purpose itself. Returns the ids that were current and are now stale.
export function revise(session: Session, reason: string, opId = "", value = "", result = ""): string[] {
  if (!reason.trim()) throw new EngineError("Say what observation undermines it: reason.");
  const before = states(session);
  if (opId.trim()) {
    if (value.trim() || result.trim()) throw new EngineError("Revise one thing at a time: an operation, or the value and result.");
    const op = operation(session, opId);
    if (op.open) throw new EngineError(`'${op.id}' is already open; record its output.`);
    op.open = true;
    op.notes.push(note(`Revised: ${reason.trim()}`));
  } else if (value.trim() || result.trim()) {
    const changes: string[] = [];
    if (value.trim()) {
      changes.push(`value was: ${session.value}`);
      session.value = value.trim();
    }
    if (result.trim()) {
      changes.push(`result was: ${session.result}`);
      session.result = result.trim();
    }
    session.purpose += 1;
    session.log.push(note(`Purpose changed (${changes.join("; ")}): ${reason.trim()}`));
  } else {
    throw new EngineError("Name the operation to reopen, or give the new value or result.");
  }
  session.status = "active";
  touch(session);
  const after = states(session);
  return session.operations.filter((op) => before[op.id] === "current" && after[op.id] !== "current" && op.id !== opId.trim()).map((op) => op.id);
}

// Close the session. Returns the operations that were not current when it closed.
export function finish(session: Session, delivered: string, evidence: string, review: string, answers: string[] = [], limitations = ""): string[] {
  if (session.status === "finished") throw new EngineError(`Session ${session.id} is already finished.`);
  if (!delivered.trim()) throw new EngineError("Say what was delivered and how to reach it: delivered.");
  if (!evidence.trim()) {
    throw new EngineError("Say what was actually checked: that the result works as built, and separately that it achieves its purpose.");
  }
  if (!review.trim()) {
    throw new EngineError(
      "Every operation passing is not a review. Have someone who did not do the work review it, with the brief next gives, " +
        "and record who reviewed, what they found, and what was done about each finding: review.",
    );
  }
  const given = answers.map((a) => a.trim());
  if (given.length !== session.questions.length || given.some((a) => !a)) {
    const listed = session.questions.map((q, i) => `${i + 1}. ${q}`).join("; ");
    throw new EngineError(`Answer each of the user's questions, in order (${listed}): answers needs ${session.questions.length} items.`);
  }
  const state = states(session);
  const unfinished = session.operations.filter((op) => state[op.id] !== "current").map((op) => op.id);
  if (unfinished.length && !limitations.trim()) {
    throw new EngineError(
      `${names(unfinished)} ${unfinished.length === 1 ? "is" : "are"} not current. Finish them, or say in limitations why the session ends without them.`,
    );
  }
  Object.assign(session, {
    delivered: delivered.trim(),
    evidence: evidence.trim(),
    review: review.trim(),
    answers: given,
    limitations: limitations.trim(),
    status: "finished",
  });
  session.log.push(note("Finished" + (unfinished.length ? ` with ${names(unfinished)} not current` : "")));
  touch(session);
  return unfinished;
}
