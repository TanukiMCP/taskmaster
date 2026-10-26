// Sessions, matrix entries, and how each situation walks the chain.
// Mirrors taskmaster/engine.py: it only sequences and never judges the work.

import {
  FIRST_STEP,
  SCOPES,
  SITUATIONS,
  VERIFY_STEP,
  ruleFor,
  type Library,
  type ScopeKey,
  type SituationKey,
} from "./library.ts";

const DIAGNOSE_FIRST = new Set<SituationKey>(["improve", "fix"]);

export class EngineError extends Error {}

const now = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");

export interface EntryInput {
  situation: SituationKey;
  scope: ScopeKey;
  goal: string;
}

export interface Handoff {
  step: number;
  iteration: number;
  text: string;
  at: string;
}

export interface Verification {
  iteration: number;
  phase: "diagnosis" | "verify";
  outcome: string;
  findings: string;
  at: string;
}

export interface Entry extends EntryInput {
  status: "pending" | "active" | "done";
  phase: "chain" | "diagnosis";
  step: number | null;
  k: number | null;
  iteration: number;
  handoffs: Handoff[];
  verifications: Verification[];
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

export function latestHandoffs(entry: Entry, before: number): Array<[number, Handoff]> {
  const latest = new Map<number, Handoff>();
  for (const h of entry.handoffs) if (h.step < before) latest.set(h.step, h);
  return [...latest.entries()].sort((a, b) => a[0] - b[0]);
}

const newEntry = (e: EntryInput): Entry => ({
  situation: e.situation,
  scope: e.scope,
  goal: e.goal.trim(),
  status: "pending",
  phase: "chain",
  step: null,
  k: null,
  iteration: 0,
  handoffs: [],
  verifications: [],
});

function activate(session: Session, index: number): void {
  session.current = index;
  Object.assign(session.entries[index], { status: "active", phase: "chain", step: FIRST_STEP, k: null, iteration: 1 });
}

function finishEntry(session: Session): void {
  const entry = session.entries[session.current];
  entry.status = "done";
  entry.step = null;
  const next = session.entries.findIndex((e) => e.status === "pending");
  if (next >= 0) activate(session, next);
  else session.status = "complete";
}

function requireEntry(session: Session): Entry {
  const entry = currentEntry(session);
  if (!entry) throw new EngineError(`Session ${session.id} is ${session.status}; there is no current step.`);
  return entry;
}

export function newSession(request: string, endGoal: string, entries: EntryInput[], conditions = ""): Session {
  if (!entries.length) {
    throw new EngineError("A session needs at least one matrix entry. Use get_matrix to choose situation and scope.");
  }
  const stamp = now();
  const session: Session = {
    id: crypto.randomUUID().replace(/-/g, "").slice(0, 12),
    created: stamp,
    updated: stamp,
    request: request.trim(),
    end_goal: endGoal.trim(),
    conditions: conditions.trim(),
    entries: entries.map(newEntry),
    current: 0,
    status: "active",
    summary: "",
  };
  activate(session, 0);
  return session;
}

export function completeStep(session: Session, handoff = ""): void {
  const entry = requireEntry(session);
  if (entry.step === VERIFY_STEP) {
    throw new EngineError(
      "Step 10 ends with report_verification: outcome 'done', or the number of the step responsible for a discrepancy.",
    );
  }
  if (handoff.trim()) entry.handoffs.push({ step: entry.step!, iteration: entry.iteration, text: handoff.trim(), at: now() });
  if (entry.step === FIRST_STEP && DIAGNOSE_FIRST.has(entry.situation) && entry.k === null) {
    entry.phase = "diagnosis";
    entry.step = VERIFY_STEP;
  } else {
    entry.step = entry.step! + 1;
  }
  session.updated = now();
}

export function reportVerification(session: Session, outcome: string, findings = ""): "done" | "rerun" {
  const entry = requireEntry(session);
  if (entry.step !== VERIFY_STEP) {
    throw new EngineError(
      `report_verification belongs to step 10; the current step is ${entry.step}. Finish this step with complete_step.`,
    );
  }
  const value = outcome.trim().toLowerCase();
  const phase = entry.phase === "diagnosis" ? "diagnosis" : "verify";
  if (value === "done") {
    entry.verifications.push({ iteration: entry.iteration, phase, outcome: "done", findings: findings.trim(), at: now() });
    finishEntry(session);
    session.updated = now();
    return "done";
  }
  if (!/^\d+$/.test(value)) throw new EngineError("outcome must be 'done' or a step number from 0 to 9.");
  const k = Number(value);
  if (k < FIRST_STEP || k >= VERIFY_STEP) {
    throw new EngineError("A responsible step is a number from 0 to 9; step 10 itself cannot be the cause.");
  }
  if (entry.situation === "review") {
    throw new EngineError(
      "Review stops before implementation. Record each finding with its responsible step and report outcome 'done'; " +
        "acting on findings needs the user's authorization and a Fix or Improve entry (add_entries).",
    );
  }
  entry.verifications.push({ iteration: entry.iteration, phase, outcome: String(k), findings: findings.trim(), at: now() });
  Object.assign(entry, { k, phase: "chain", step: k, iteration: entry.iteration + 1 });
  session.updated = now();
  return "rerun";
}

export function addEntries(session: Session, entries: EntryInput[], position: "next" | "end" = "next"): void {
  if (!entries.length) throw new EngineError("No entries to add.");
  if (session.status === "ended") throw new EngineError(`Session ${session.id} has ended; start a new session.`);
  const added = entries.map(newEntry);
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

export function endSession(session: Session, summary = ""): void {
  session.status = "ended";
  session.summary = summary.trim();
  for (const entry of session.entries) if (entry.status === "active") entry.step = null;
  session.updated = now();
}

export function modeFor(library: Library, entry: Entry, step: number): string {
  if (entry.phase === "diagnosis") return "diagnose the existing work";
  const rule = ruleFor(library.situations[entry.situation], step, entry.k);
  const firstSentence = rule.split(".")[0].toLowerCase();
  let mode: string;
  if (firstSentence.startsWith("record")) mode = "record";
  else if (firstSentence.startsWith("keep")) mode = "keep";
  else if (` ${firstSentence} `.includes(" only ") || rule.toLowerCase().includes("otherwise keep")) mode = "decide or keep";
  else mode = "decide";
  const limit = library.scopes[entry.scope].limits.get(step)!.toLowerCase();
  if (mode.startsWith("decide")) {
    if (limit.startsWith("keep")) mode = "keep";
    else if (limit.includes("otherwise keep")) mode = "decide or keep";
  }
  return mode;
}
