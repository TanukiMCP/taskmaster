// Sessions, matrix entries, plans, and SOP steps. Mirrors taskmaster/engine.py:
// it only sequences and never judges the work.

import {
  FIRST_STEP,
  SCOPES,
  SITUATIONS,
  VERIFY_STEP,
  resolveRefs,
  usesK,
  type Library,
  type ScopeKey,
  type SituationKey,
  type SopStep,
} from "./library.ts";

export class EngineError extends Error {}

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

export interface EntryInput {
  situation: SituationKey;
  scope: ScopeKey;
  goal: string;
}

export interface Handoff {
  sop_step: number;
  iteration: number;
  text: string;
  at: string;
}

export interface Verification {
  sop_step: number;
  iteration: number;
  outcome: string;
  findings: string;
  at: string;
}

export interface Entry extends EntryInput {
  status: "pending" | "active" | "done" | "escalated";
  phase: "plan" | "run";
  index: number;
  k: number | null;
  resume_at: number | null;
  iteration: number;
  plan: string[];
  plan_revisions: number;
  handoffs: Handoff[];
  verifications: Verification[];
  note: string;
}

export interface Session {
  id: string;
  created: string;
  updated: string;
  request: string;
  end_goal: string;
  conditions: string;
  entries: Entry[];
  current: number;
  status: "active" | "complete" | "ended";
  summary: string;
}

export const entryLabel = (e: EntryInput) => `${SITUATIONS[e.situation]} × ${SCOPES[e.scope]}`;

export function currentEntry(session: Session): Entry | null {
  if (session.status !== "active" || session.current < 0 || session.current >= session.entries.length) return null;
  return session.entries[session.current];
}

export const sopSteps = (lib: Library, entry: Entry) => lib.situations[entry.situation].steps;
export const currentSopStep = (lib: Library, entry: Entry) => sopSteps(lib, entry)[entry.index];

export function latestHandoffs(entry: Entry): Array<[number, Handoff]> {
  const latest = new Map<number, Handoff>();
  for (const h of entry.handoffs) latest.set(h.sop_step, h);
  return [...latest.entries()].sort((a, b) => a[0] - b[0]);
}

const newEntry = (e: EntryInput, note = ""): Entry => ({
  situation: e.situation,
  scope: e.scope,
  goal: e.goal.trim(),
  status: "pending",
  phase: "plan",
  index: 0,
  k: null,
  resume_at: null,
  iteration: 0,
  plan: [],
  plan_revisions: 0,
  handoffs: [],
  verifications: [],
  note,
});

function activate(session: Session, index: number): void {
  session.current = index;
  Object.assign(session.entries[index], { status: "active", phase: "plan", index: 0, k: null, resume_at: null, iteration: 1, plan: [] });
}

function finishEntry(session: Session): void {
  const entry = session.entries[session.current];
  if (entry.status === "active") entry.status = "done";
  const next = session.entries.findIndex((e) => e.status === "pending");
  if (next >= 0) activate(session, next);
  else session.status = "complete";
}

function requireEntry(session: Session): Entry {
  const entry = currentEntry(session);
  if (!entry) throw new EngineError(`Session ${session.id} is ${session.status}; there is no current step.`);
  return entry;
}

function requireRunning(lib: Library, session: Session): [Entry, SopStep] {
  const entry = requireEntry(session);
  if (entry.phase === "plan") {
    throw new EngineError(`Write the plan first: call submit_plan with ${sopSteps(lib, entry).length} items, one per SOP step of ${entryLabel(entry)}.`);
  }
  return [entry, currentSopStep(lib, entry)];
}

export function newSession(request: string, endGoal: string, entries: EntryInput[], conditions = ""): Session {
  if (!entries.length) throw new EngineError("A session needs at least one matrix entry. Use get_matrix to choose situation and scope.");
  const stamp = now();
  const session: Session = {
    id: crypto.randomUUID().replace(/-/g, "").slice(0, 12),
    created: stamp,
    updated: stamp,
    request: request.trim(),
    end_goal: endGoal.trim(),
    conditions: conditions.trim(),
    entries: entries.map((e) => newEntry(e)),
    current: 0,
    status: "active",
    summary: "",
  };
  activate(session, 0);
  return session;
}

export function submitPlan(lib: Library, session: Session, plan: string[]): boolean {
  const entry = requireEntry(session);
  const steps = sopSteps(lib, entry);
  const items = plan.map((item) => item.trim());
  if (items.length !== steps.length || items.some((item) => !item)) {
    const titles = steps.map((s) => `${s.number}. ${s.title}`).join("; ");
    throw new EngineError(`The plan needs exactly ${steps.length} non-empty items, one per SOP step in order (${titles}). Received ${items.length}.`);
  }
  const starting = entry.phase === "plan";
  entry.plan = items;
  if (starting) {
    entry.phase = "run";
    entry.index = 0;
  } else {
    entry.plan_revisions += 1;
  }
  session.updated = now();
  return starting;
}

function advance(session: Session, lib: Library, entry: Entry): void {
  entry.resume_at = null;
  if (entry.index + 1 < sopSteps(lib, entry).length) entry.index += 1;
  else finishEntry(session);
}

export function completeStep(lib: Library, session: Session, handoff = "", responsibleStep: number | null = null): void {
  const [entry, step] = requireRunning(lib, session);
  if (step.kind === "verify") {
    throw new EngineError(
      "This is a verify step. Finish it with report_verification: outcome 'done', or the number of the procedure step responsible for a discrepancy.",
    );
  }
  if (step.kind === "trace") {
    if (responsibleStep === null || responsibleStep < FIRST_STEP || responsibleStep >= VERIFY_STEP) {
      throw new EngineError("This trace step needs responsible_step: the procedure step (0–9) where the cause lies.");
    }
    entry.k = responsibleStep;
  }
  if (handoff.trim()) entry.handoffs.push({ sop_step: step.number, iteration: entry.iteration, text: handoff.trim(), at: now() });
  advance(session, lib, entry);
  session.updated = now();
}

function returnTarget(lib: Library, entry: Entry, k: number): number {
  const steps = sopSteps(lib, entry);
  const hit = steps.findIndex((s) => s.kind === "work" && resolveRefs(s, entry.k).includes(k));
  if (hit >= 0) return hit;
  const firstWork = steps.findIndex((s) => s.kind === "work");
  return firstWork >= 0 ? firstWork : 0;
}

export function reportVerification(lib: Library, session: Session, outcome: string, findings = ""): "done" | "rerun" {
  const [entry, step] = requireRunning(lib, session);
  if (step.kind !== "verify") {
    throw new EngineError(`report_verification belongs to a verify step; SOP step ${step.number} (${step.title}) finishes with complete_step.`);
  }
  const value = outcome.trim().toLowerCase();
  if (value === "done") {
    entry.verifications.push({ sop_step: step.number, iteration: entry.iteration, outcome: "done", findings: findings.trim(), at: now() });
    advance(session, lib, entry);
    session.updated = now();
    return "done";
  }
  if (!/^\d+$/.test(value)) throw new EngineError("outcome must be 'done' or a procedure step number from 0 to 9.");
  const k = Number(value);
  if (k < FIRST_STEP || k >= VERIFY_STEP) {
    throw new EngineError("A responsible step is a procedure step number from 0 to 9; step 10 itself cannot be the cause.");
  }
  if (entry.situation === "review") {
    throw new EngineError(
      "Review stops before implementation. Record each finding with its responsible step and report outcome 'done'; " +
        "acting on findings needs the user's authorization and a Fix or Redesign entry (add_entries).",
    );
  }
  entry.verifications.push({ sop_step: step.number, iteration: entry.iteration, outcome: String(k), findings: findings.trim(), at: now() });
  if (sopSteps(lib, entry).some(usesK)) entry.k = k;
  entry.index = returnTarget(lib, entry, k);
  entry.resume_at = k;
  entry.iteration += 1;
  session.updated = now();
  return "rerun";
}

export function addEntries(session: Session, entries: EntryInput[], position: "next" | "end" = "next"): void {
  if (!entries.length) throw new EngineError("No entries to add.");
  if (session.status === "ended") throw new EngineError(`Session ${session.id} has ended; start a new session.`);
  const added = entries.map((e) => newEntry(e));
  if (session.status === "complete") {
    session.entries.push(...added);
    session.status = "active";
    activate(session, session.entries.length - added.length);
  } else if (position === "end") {
    session.entries.push(...added);
  } else {
    session.entries.splice(session.current + 1, 0, ...added);
  }
  session.updated = now();
}

export function escalate(session: Session, reason: string, toScope: ScopeKey | null = null, toSituation: SituationKey | null = null): Entry {
  const entry = requireEntry(session);
  if (!toScope && !toSituation) throw new EngineError("Escalate to a scope, a situation, or both.");
  if (!reason.trim()) throw new EngineError("Say why the decision belongs elsewhere.");
  const target = { situation: toSituation ?? entry.situation, scope: toScope ?? entry.scope, goal: entry.goal };
  const replacement = newEntry(target, `Escalated from ${entryLabel(entry)}: ${reason.trim()}`);
  entry.status = "escalated";
  entry.note = `Escalated to ${entryLabel(target)}: ${reason.trim()}`;
  session.entries.splice(session.current + 1, 0, replacement);
  activate(session, session.current + 1);
  session.updated = now();
  return replacement;
}

export function endSession(session: Session, summary = ""): void {
  session.status = "ended";
  session.summary = summary.trim();
  session.updated = now();
}
