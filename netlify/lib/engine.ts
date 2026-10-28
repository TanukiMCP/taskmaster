// Sessions, matrix entries, plans, and SOP steps. Mirrors taskmaster/engine.py:
// each step finishes with results that cite the earlier results they build on,
// and a verify step ends at "ready"; only the user's verdict marks work done.

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

// The rungs an entry may escalate to, from the matrix's Parent column.
export const PARENTS: Record<ScopeKey, ScopeKey[]> = {
  element: ["component", "section"],
  component: ["section", "page"],
  section: ["page"],
  page: ["flow", "product"],
  flow: ["product"],
  product: [],
  "shared-styles": ["product"],
};

export const CAPTURE_WIDTHS = [1440, 820, 390];
export type CaptureKind = "result" | "comparison" | "before";

const words = (text: string) =>
  text
    .toLowerCase()
    .replace(/[‘’‛`]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();

// A quote counts when it is at least three words and appears in the user's words.
export function quoteFound(quote: string, text: string): boolean {
  const q = words(quote).replace(/^["' .]+|["' .]+$/g, "");
  return q.split(" ").length >= 3 && words(text).includes(q);
}

export interface EntryInput {
  situation: SituationKey;
  scope: ScopeKey;
  goal: string;
}

export interface ConstraintInput {
  constraint: string;
  quote: string;
}

export interface ResultInput {
  statement: string;
  based_on?: string[];
}

export interface DropInput {
  id: string;
  reason: string;
}

export interface Constraint {
  id: string;
  text: string;
  quote: string;
}

export interface Handoff {
  sop_step: number;
  iteration: number;
  text: string;
  at: string;
}

export interface Result {
  id: string;
  sop_step: number;
  iteration: number;
  statement: string;
  based_on: string[];
  at: string;
}

export interface Verification {
  sop_step: number;
  iteration: number;
  outcome: string;
  findings: string;
  at: string;
}

export interface CaptureWidth {
  width: number;
  ok: boolean;
  error?: string;
  page_height?: number;
  element_height?: number | null;
  overflow?: boolean;
  page?: { file: string; sha256?: string };
  element?: { file: string; sha256?: string };
}

export interface Capture {
  kind: CaptureKind;
  label: string;
  url: string;
  selector: string | null;
  taken_by: "taskmaster" | "agent";
  taken_at: string;
  widths: CaptureWidth[];
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
  results: Result[];
  dropped: Record<string, string>;
  captures: Capture[];
  verifications: Verification[];
  awaiting_user: boolean;
  last_completed_at: string;
  note: string;
}

export interface Session {
  id: string;
  created: string;
  updated: string;
  request: string;
  end_goal: string;
  conditions: string;
  constraints: Constraint[];
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

// Every situation except Review ends its verify step with the user's verdict.
export const needsVerdict = (entry: Entry) => entry.situation !== "review";

// Sessions saved before results and captures existed load with empty ones.
export function upgrade(session: Session): Session {
  session.constraints ??= [];
  for (const e of session.entries) {
    e.results ??= [];
    e.dropped ??= {};
    e.captures ??= [];
    e.awaiting_user ??= false;
    e.last_completed_at ??= "";
  }
  return session;
}

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
  results: [],
  dropped: {},
  captures: [],
  verifications: [],
  awaiting_user: false,
  last_completed_at: "",
  note,
});

function activate(session: Session, index: number): void {
  session.current = index;
  Object.assign(session.entries[index], {
    status: "active",
    phase: "plan",
    index: 0,
    k: null,
    resume_at: null,
    iteration: 1,
    plan: [],
    awaiting_user: false,
  });
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

function waiting(entry: Entry): void {
  if (entry.awaiting_user) {
    throw new EngineError(
      "The work is ready for the user's review. Only the user marks it done or returns it to a step; show them the captures and wait for their verdict.",
    );
  }
}

function requireRunning(lib: Library, session: Session): [Entry, SopStep] {
  const entry = requireEntry(session);
  if (entry.phase === "plan") {
    throw new EngineError(`Write the plan first: call submit_plan with ${sopSteps(lib, entry).length} items, one per SOP step of ${entryLabel(entry)}.`);
  }
  waiting(entry);
  return [entry, currentSopStep(lib, entry)];
}

export function newSession(request: string, endGoal: string, entries: EntryInput[], conditions = "", constraints: ConstraintInput[] = []): Session {
  if (!entries.length) throw new EngineError("A session needs at least one matrix entry. Use get_matrix to choose situation and scope.");
  if (!request.trim()) throw new EngineError("request is the user's own words, copied exactly.");
  const recorded: Constraint[] = [];
  const problems: string[] = [];
  constraints.forEach((item, i) => {
    const n = i + 1;
    if (!item.constraint?.trim()) problems.push(`Constraint ${n} doesn't say what must be kept or followed.`);
    else if (!quoteFound(item.quote ?? "", request)) {
      problems.push(
        `Constraint ${n} ("${item.constraint.trim()}") has no quote from the request of at least three words. ` +
          "Without the user's own words it is not a constraint; leave that decision open.",
      );
    } else recorded.push({ id: `C${n}`, text: item.constraint.trim(), quote: item.quote.trim() });
  });
  if (problems.length) throw new EngineError(problems.join(" "));
  const stamp = now();
  const session: Session = {
    id: crypto.randomUUID().replace(/-/g, "").slice(0, 12),
    created: stamp,
    updated: stamp,
    request: request.trim(),
    end_goal: endGoal.trim(),
    conditions: conditions.trim(),
    constraints: recorded,
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
  waiting(entry);
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

export function completeStep(
  lib: Library,
  session: Session,
  handoff = "",
  responsibleStep: number | null = null,
  results: ResultInput[] = [],
  dropped: DropInput[] = [],
): void {
  const [entry, step] = requireRunning(lib, session);
  if (step.kind === "verify") {
    throw new EngineError(
      "This is a verify step. Finish it with report_verification: outcome 'ready', or the number of the procedure step responsible for a discrepancy.",
    );
  }
  if (!handoff.trim()) throw new EngineError("handoff is required: name the actual result and how the next step uses it.");
  if (step.kind === "trace" && (responsibleStep === null || responsibleStep < FIRST_STEP || responsibleStep >= VERIFY_STEP)) {
    throw new EngineError("This trace step needs responsible_step: the procedure step (0–9) where the cause lies.");
  }

  const items = results.filter((r) => r.statement?.trim());
  const firstStep = step.number === sopSteps(lib, entry)[0].number;
  const earlier = new Set(entry.results.filter((r) => r.sop_step < step.number).map((r) => r.id));
  const citable = new Set([...earlier, ...session.constraints.map((c) => c.id), "request"]);
  const problems: string[] = [];
  if (!items.length) problems.push("results are required: each result of this step as a statement with the IDs it is based on.");
  items.forEach((item, i) => {
    const n = i + 1;
    const cited = (item.based_on ?? []).map((c) => c.trim()).filter(Boolean);
    const unknown = cited.filter((c) => !citable.has(c));
    if (unknown.length) problems.push(`Result ${n} cites ${unknown.join(", ")}, which are not earlier results, constraints, or 'request'.`);
    if (!cited.length) problems.push(`Result ${n} cites nothing. Name the earlier results it builds on.`);
    else if (!firstStep && !cited.some((c) => earlier.has(c))) {
      problems.push(`Result ${n} cites no earlier result. Every step after the first builds on an earlier step's results.`);
    }
  });
  const drops: Record<string, string> = {};
  for (const d of dropped) {
    if (!earlier.has(d.id)) problems.push(`Dropped ${d.id} is not an earlier result.`);
    else if (!d.reason?.trim()) problems.push(`Dropping ${d.id} needs a reason.`);
    else drops[d.id] = d.reason.trim();
  }
  if (problems.length) throw new EngineError(problems.join(" "));

  if (step.kind === "trace") entry.k = responsibleStep;
  const stamp = now();
  entry.results = entry.results.filter((r) => r.sop_step !== step.number);
  items.forEach((item, i) => {
    entry.results.push({
      id: `${step.number}.${i + 1}`,
      sop_step: step.number,
      iteration: entry.iteration,
      statement: item.statement.trim(),
      based_on: (item.based_on ?? []).map((c) => c.trim()).filter(Boolean),
      at: stamp,
    });
  });
  Object.assign(entry.dropped, drops);
  entry.handoffs.push({ sop_step: step.number, iteration: entry.iteration, text: handoff.trim(), at: stamp });
  entry.last_completed_at = stamp;
  advance(session, lib, entry);
  session.updated = stamp;
}

// Results no later step cites and that were not dropped, apart from the last step before verification.
export function unusedResults(lib: Library, entry: Entry): Result[] {
  const steps = sopSteps(lib, entry);
  const verifyAt = steps.find((s) => s.kind === "verify")?.number;
  const before = verifyAt === undefined ? undefined : Math.max(...steps.filter((s) => s.number < verifyAt).map((s) => s.number));
  const cited = new Set(entry.results.flatMap((r) => r.based_on));
  return entry.results.filter((r) => !cited.has(r.id) && !(r.id in entry.dropped) && r.sop_step !== before);
}

function returnTarget(lib: Library, entry: Entry, k: number): number {
  const steps = sopSteps(lib, entry);
  const hit = steps.findIndex((s) => s.kind === "work" && resolveRefs(s, entry.k).includes(k));
  if (hit >= 0) return hit;
  const firstWork = steps.findIndex((s) => s.kind === "work");
  return firstWork >= 0 ? firstWork : 0;
}

function rerun(lib: Library, entry: Entry, step: SopStep, k: number, outcome: string, findings: string): void {
  entry.verifications.push({ sop_step: step.number, iteration: entry.iteration, outcome, findings, at: now() });
  if (sopSteps(lib, entry).some(usesK)) entry.k = k;
  entry.index = returnTarget(lib, entry, k);
  entry.resume_at = k;
  entry.iteration += 1;
}

function parseStep(value: string): number {
  if (!/^\d+$/.test(value)) throw new EngineError("outcome must be 'ready' or a procedure step number from 0 to 9.");
  const k = Number(value);
  if (k < FIRST_STEP || k >= VERIFY_STEP) throw new EngineError("A responsible step is a procedure step number from 0 to 9; step 10 itself cannot be the cause.");
  return k;
}

export function reportVerification(lib: Library, session: Session, outcome: string, findings = ""): "ready" | "done" | "rerun" {
  const [entry, step] = requireRunning(lib, session);
  if (step.kind !== "verify") {
    throw new EngineError(`report_verification belongs to a verify step; SOP step ${step.number} (${step.title}) finishes with complete_step.`);
  }
  const value = outcome.trim().toLowerCase();

  if (!needsVerdict(entry)) {
    if (value === "done" || value === "ready") {
      entry.verifications.push({ sop_step: step.number, iteration: entry.iteration, outcome: "done", findings: findings.trim(), at: now() });
      advance(session, lib, entry);
      session.updated = now();
      return "done";
    }
    parseStep(value);
    throw new EngineError(
      "Review stops before implementation. Record each finding with its responsible step and report outcome 'done'; " +
        "acting on findings needs the user's authorization and a Fix or Redesign entry (add_entries).",
    );
  }

  if (value === "ready" || value === "done") {
    const problems: string[] = [];
    const unused = unusedResults(lib, entry);
    if (unused.length) {
      problems.push(
        `These results are not used by any later step: ${unused.map((r) => `${r.id} (${r.statement.slice(0, 60)})`).join("; ")}. ` +
          "Use them, or drop them with a reason (complete_step's dropped) on a rerun.",
      );
    }
    if (!entry.captures.some((c) => c.kind === "result" && c.taken_at >= entry.last_completed_at)) {
      problems.push("Capture the result first (capture with kind 'result'), after the last change to the work.");
    }
    if (!entry.captures.some((c) => c.kind === "comparison" || c.kind === "before")) {
      problems.push(
        "Capture what the result is compared with: its references or accepted views (kind 'comparison'), or the work before (kind 'before').",
      );
    }
    if (problems.length) throw new EngineError(problems.join(" "));
    entry.verifications.push({ sop_step: step.number, iteration: entry.iteration, outcome: "ready", findings: findings.trim(), at: now() });
    entry.awaiting_user = true;
    session.updated = now();
    return "ready";
  }

  rerun(lib, entry, step, parseStep(value), value, findings.trim());
  session.updated = now();
  return "rerun";
}

// The user's verdict on work that is ready for review: 'done', or 'return' to a procedure step with a reason.
export function recordVerdict(lib: Library, session: Session, verdict: string, step: number | null = null, reason = ""): "done" | "return" {
  const entry = requireEntry(session);
  if (!entry.awaiting_user) throw new EngineError(`Session ${session.id} has no work waiting for a verdict.`);
  const sop = currentSopStep(lib, entry);
  const value = verdict.trim().toLowerCase();
  if (value === "done") {
    entry.awaiting_user = false;
    entry.verifications.push({ sop_step: sop.number, iteration: entry.iteration, outcome: "done (user)", findings: reason.trim(), at: now() });
    advance(session, lib, entry);
    session.updated = now();
    return "done";
  }
  if (value === "return") {
    if (step === null || Number.isNaN(step)) throw new EngineError("Say which procedure step (0–9) the work returns to.");
    if (!reason.trim()) throw new EngineError("Give the reason the work is returned.");
    const k = parseStep(String(step));
    entry.awaiting_user = false;
    rerun(lib, entry, sop, k, `returned by the user to step ${k}`, reason.trim());
    session.updated = now();
    return "return";
  }
  throw new EngineError("verdict is 'done' or 'return'.");
}

// Record one capture from the capture script's manifest. A capture that failed at any width is refused.
export function addCapture(session: Session, kind: CaptureKind, label: string, manifest: any, takenBy: "taskmaster" | "agent"): Capture {
  const entry = requireEntry(session);
  waiting(entry);
  if (entry.phase === "plan") throw new EngineError("Write the plan first.");
  const widths: CaptureWidth[] | undefined = Array.isArray(manifest?.widths) ? manifest.widths : undefined;
  const got = (widths ?? []).map((w) => w?.width).sort((a, b) => a - b);
  if (!widths || got.join() !== [...CAPTURE_WIDTHS].sort((a, b) => a - b).join()) {
    throw new EngineError(`A capture covers ${CAPTURE_WIDTHS.join(", ")} pixels wide; this manifest doesn't.`);
  }
  const failed = widths.filter((w) => !w.ok).map((w) => `${w.width}: ${w.error ?? "did not render"}`);
  if (failed.length) throw new EngineError(`The capture of ${manifest.url} failed at ${failed.join("; ")}. Fix the page or the selector and capture it again.`);
  const capture: Capture = {
    kind,
    label: label.trim() || kind,
    url: String(manifest.url ?? ""),
    selector: manifest.selector || null,
    taken_by: takenBy,
    taken_at: now(),
    widths,
  };
  entry.captures.push(capture);
  session.updated = now();
  return capture;
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
  waiting(entry);
  if (!toScope && !toSituation) throw new EngineError("Escalate to a scope, a situation, or both.");
  if (!reason.trim()) throw new EngineError("Say why the decision belongs elsewhere.");
  if (toScope && toScope !== entry.scope && !PARENTS[entry.scope].includes(toScope)) {
    throw new EngineError(`An entry escalates to its parent scope. The parent of ${entry.scope} is: ${PARENTS[entry.scope].join(", ") || "none"}.`);
  }
  if (entry.situation === "review" && toSituation && toSituation !== "review") {
    throw new EngineError(
      "A Review doesn't turn into changes on its own. Acting on findings needs the user's authorization and a Fix or Redesign entry (add_entries).",
    );
  }
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
