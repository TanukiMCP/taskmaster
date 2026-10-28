// The Taskmaster MCP server: tools, resources, and prompt. Mirrors taskmaster/server.py.

import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import {
  CAPTURE_WIDTHS,
  EngineError,
  addCapture,
  addEntries,
  completeStep,
  currentEntry,
  currentSopStep,
  endSession,
  entryLabel,
  escalate,
  newSession,
  reportVerification,
  sopSteps,
  submitPlan,
  type Entry,
  type Session,
} from "./engine.ts";
import {
  SCOPES,
  SITUATIONS,
  VERIFY_STEP,
  paragraph,
  resolveRefs,
  scopeLinesFor,
  type Library,
  type ScopeKey,
  type SituationKey,
  type SopStep,
} from "./library.ts";
import type { Store } from "./store.ts";

export const VERSION = "2.0.0";

export const INSTRUCTIONS = `Taskmaster runs design work as standard operating procedures chosen from the scope and situation matrix. process.txt is the fixed design procedure; each situation has an SOP that sets the working path through it, and each scope sets how far the work reaches.

1. Call get_matrix. Choose each situation with its selector questions and the smallest scope that contains every decision to change.
2. Work backward from the end goal: list the matrix entries, in order, that get from the current state to the goal. "Redesign the landing page and add a pricing page" is redesign × page, then extend × page.
3. Call start_session with the user's request copied word for word, the end goal, and those entries. A constraint, such as keeping the existing identity, counts only with the user's own words quoted from the request. Taskmaster replies with a session_id, the working method, and the first entry's SOP and scope sheet. Pass that session_id to every later call; other conversations may run their own sessions at the same time.
4. Before any work, call submit_plan with one item per SOP step: the specific work you will do on this assignment, the questions you must answer, and the result that will show the step is complete.
5. Execute exactly the SOP step you are given, using the procedure text it includes as the authority. Announce it in chat first. When its result exists, call complete_step with a short handoff and the step's results, each citing the earlier results it builds on. Before a verify step finishes, capture the result and what it is compared with. Verify steps end with report_verification: 'ready' for the user's review, or the procedure step responsible for a discrepancy. Only the user marks work done.
6. When a step shows the decision belongs to a parent scope or another situation, call escalate instead of working around the boundary.
7. current_step re-issues the current step after an interruption or condensed context. get_status without a session_id lists recent sessions.

Do not keep your own tasklist or tracking document for this work; the plan lives in Taskmaster.`;

const situationKeys = Object.keys(SITUATIONS) as [SituationKey, ...SituationKey[]];
const scopeKeys = Object.keys(SCOPES) as [ScopeKey, ...ScopeKey[]];

const entrySchema = z.object({
  situation: z.enum(situationKeys).describe("create, extend, redesign, fix, or review — chosen with the matrix selector questions"),
  scope: z.enum(scopeKeys).describe("element, component, section, page, flow, product, or shared-styles — the smallest unit containing every decision to change"),
  goal: z.string().describe("What this entry must achieve, worked backward from the session's end goal"),
});
const entriesSchema = z.array(entrySchema).describe("Ordered matrix entries, each {situation, scope, goal}");
const constraintsSchema = z
  .array(z.object({ constraint: z.string(), quote: z.string().describe("The user's own words that say so, copied exactly from the request (at least three words)") }))
  .describe("Constraints the user stated, each with the user's own words quoted from the request");
const resultsSchema = z
  .array(
    z.object({
      statement: z.string().describe("One result of this step: a decision, a finding, or what is kept and why"),
      based_on: z.array(z.string()).describe("IDs of the earlier results, constraints (C1…), or 'request' this result builds on"),
    }),
  )
  .describe("This step's results, each {statement, based_on}");
const dropsSchema = z.array(z.object({ id: z.string(), reason: z.string() })).describe("Earlier results no later step will use, each {id, reason}");
const planSchema = z
  .array(z.string())
  .describe("One item per SOP step, in order: the specific work, the questions to answer, and the result that shows the step is complete");
const sessionIdSchema = z.string().describe("The session_id start_session returned");

const stepTag = (step: SopStep) => (step.kind === "work" ? "" : ` (${step.kind})`);

function plan(lib: Library, session: Session): string {
  return session.entries
    .map((entry, i) => {
      const marker = { done: "✓", active: "▶", pending: "·", escalated: "↑" }[entry.status];
      let where = "";
      if (entry.status === "active") {
        const total = sopSteps(lib, entry).length;
        where = entry.phase === "plan" ? " — writing the plan" : ` — SOP step ${entry.index + 1} of ${total}, pass ${entry.iteration}`;
      }
      return `${marker} ${i + 1}. ${entryLabel(entry)}: ${entry.goal}${where}`;
    })
    .join("\n");
}

function briefing(lib: Library, session: Session): string {
  const entry = currentEntry(session)!;
  const parts = [`# Entry ${session.current + 1} of ${session.entries.length}: ${entryLabel(entry)}`, `Entry goal: ${entry.goal}`];
  if (entry.note) parts.push(entry.note);
  parts.push(
    `## Situation SOP: ${SITUATIONS[entry.situation]}`,
    lib.situations[entry.situation].fullText,
    `## Scope: ${SCOPES[entry.scope]}`,
    lib.scopes[entry.scope].fullText,
  );
  return parts.join("\n\n");
}

function planRequest(lib: Library, session: Session): string {
  const entry = currentEntry(session)!;
  const steps = sopSteps(lib, entry);
  return [
    "## Write your plan before any work",
    `Call submit_plan(session_id='${session.id}', plan=[...]) with exactly ${steps.length} items, one per SOP step in this order:`,
    steps.map((s) => `${s.number}. ${s.title}${stepTag(s)}`).join("\n"),
    "Each item states the specific work you will do for that step on this assignment, the questions you must answer, " +
      "and the result that will show the step is complete. Write it from the SOP, the scope sheet, and what you already know " +
      "about the assignment; do not start the work until the plan is accepted.",
  ].join("\n\n");
}

function procedureBlocks(lib: Library, step: SopStep, numbers: number[]): string[] {
  if (!numbers.length) return ["## Procedure", "No procedure steps apply here."];
  return numbers.flatMap((n) => {
    const proc = lib.procedure.steps.get(n)!;
    if (step.modifier === "keep") {
      return [`## Procedure step ${n}: ${proc.name} — Keep rule (get_process_step(${n}) for the full step)`, paragraph(proc, "Keep:")];
    }
    if (step.modifier === "produces") {
      return [`## Procedure step ${n}: ${proc.name} — what it produces (get_process_step(${n}) for the full step)`, paragraph(proc, "Produces:")];
    }
    return [`## Procedure step ${n}: ${proc.name} (verbatim)`, proc.text];
  });
}

function closing(lib: Library, session: Session): string {
  if (session.status === "complete") {
    return (
      `All ${session.entries.length} entries are done for session ${session.id}.\n\n${plan(lib, session)}\n\n` +
      `Deliver the result as the final situation's completion describes, then call end_session(session_id='${session.id}') ` +
      "with a summary. Use add_entries if more work is needed."
    );
  }
  return `Session ${session.id} is ${session.status}.`;
}

function earlierResults(entry: Entry, steps: SopStep[]): string {
  const titles = new Map(steps.map((s) => [s.number, s.title]));
  const lines: string[] = [];
  let current: number | null = null;
  const sorted = [...entry.results].sort((a, b) => a.sop_step - b.sop_step || Number(a.id.split(".")[1]) - Number(b.id.split(".")[1]));
  for (const r of sorted) {
    if (r.sop_step !== current) {
      current = r.sop_step;
      lines.push(`SOP step ${current} (${titles.get(current) ?? ""}):`);
    }
    const mark = r.id in entry.dropped ? ` [dropped: ${entry.dropped[r.id]}]` : "";
    lines.push(`- ${r.id}: ${r.statement} (based on ${r.based_on.join(", ")})${mark}`);
  }
  return lines.join("\n");
}

function captureLines(entry: Entry): string {
  return entry.captures
    .map((c) => {
      const heights = c.widths.map((w) => `${w.width}: ${w.page_height}px${w.overflow ? " (scrolls sideways)" : ""}`).join(", ");
      const files = c.widths.map((w) => w.page?.file ?? "").join(", ");
      return `- ${c.kind} '${c.label}' ${c.url}${c.selector ? " " + c.selector : ""} — taken by ${c.taken_by} at ${c.taken_at}; page heights ${heights}; files ${files}`;
    })
    .join("\n");
}

function awaiting(session: Session, entry: Entry): string {
  const last = entry.verifications.at(-1);
  return [
    `# Waiting for the user's verdict — ${entryLabel(entry)}`,
    `Session ID: ${session.id}`,
    "The work is ready for the user's review. Tell the user it is ready, show them the captures, and report what was measured " +
      "and checked. Do not call it good, clean, better, or fixed, and do not continue until they decide.",
    "## Captures",
    captureLines(entry),
    last?.findings ? `## Your verification notes\n${last.findings}` : "",
    "The user records their verdict on their Taskmaster review page (/review/<their review token> on this connector's site). " +
      "You cannot record it for them.",
  ]
    .filter(Boolean)
    .join("\n\n");
}

export function renderStep(lib: Library, session: Session, opts: { briefing?: boolean; preamble?: boolean } = {}): string {
  const entry = currentEntry(session);
  if (!entry) return closing(lib, session);
  const parts: string[] = [];
  if (opts.preamble) parts.push("# Working method (process.txt, read once and keep as the authority)", lib.procedure.preamble);
  if (entry.phase === "plan") {
    parts.push(briefing(lib, session), planRequest(lib, session));
    return parts.filter(Boolean).join("\n\n");
  }
  if (opts.briefing) parts.push(briefing(lib, session));
  if (entry.awaiting_user) {
    parts.push(awaiting(session, entry));
    return parts.filter(Boolean).join("\n\n");
  }

  const steps = sopSteps(lib, entry);
  const step = currentSopStep(lib, entry);
  const numbers = resolveRefs(step, entry.k);
  const situation = SITUATIONS[entry.situation];
  const scope = lib.scopes[entry.scope];
  const where = numbers.map((n) => `${n} (${lib.procedure.steps.get(n)!.name})`).join(", ") || "none";

  parts.push(`# ${situation} step ${step.number} of ${steps.length}: ${step.title}${stepTag(step)}`);
  const context = [
    `Session ID: ${session.id} (pass session_id='${session.id}' with every call)`,
    `The user's words: ${session.request}`,
    `Session end goal: ${session.end_goal}`,
    `Entry ${session.current + 1} of ${session.entries.length}: ${entryLabel(entry)} — ${entry.goal}`,
    `Works in procedure step: ${where}`,
  ];
  if (session.constraints.length) {
    context.push("Constraints, in the user's words (anything not listed here is open):");
    for (const c of session.constraints) context.push(`- ${c.id}: ${c.text} — "${c.quote}"`);
  } else {
    context.push("Constraints: none quoted from the user, so no identity or other decision is kept on the user's say-so.");
  }
  if (session.conditions) context.push(`Task conditions: ${session.conditions}`);
  if (entry.k !== null) context.push(`Responsible procedure step (k): ${entry.k} (${lib.procedure.steps.get(entry.k)!.name})`);
  if (entry.iteration > 1 && entry.resume_at !== null) {
    context.push(`Pass ${entry.iteration}: verification returned procedure step ${entry.resume_at}; resume there. Earlier results are reused unchanged.`);
  }
  parts.push(context.join("\n"));

  parts.push(`## SOP step (${situation})`, step.instruction);
  if (entry.plan.length) parts.push("## Your plan for this step", entry.plan[entry.index]);

  const scopeLines = [`Boundary: ${scope.fields["Boundary"] ?? ""}`, ...scopeLinesFor(scope, numbers.length ? numbers : [VERIFY_STEP]).map(([l, t]) => `${l}: ${t}`)];
  parts.push(`## Scope: ${scope.title}`, scopeLines.join("\n"));

  const earlier = earlierResults(entry, steps);
  if (earlier) parts.push("## Earlier results in this entry (cite these IDs)", earlier);
  if (entry.captures.length) parts.push("## Captures in this entry", captureLines(entry));
  const last = entry.verifications.at(-1);
  if (last?.findings && step.kind !== "verify") {
    parts.push(last.outcome.startsWith("returned by the user") ? "## The user's reason for returning the work" : "## Latest verification findings", last.findings);
  }

  parts.push(...procedureBlocks(lib, step, numbers));
  parts.push("## Working rules", lib.procedure.workingRules);

  const citeRule =
    steps[0].number === step.number
      ? "cite 'request' or the constraint IDs it rests on"
      : "cite at least one earlier result ID it builds on (constraints and 'request' may be cited as well)";
  const resultsRule =
    `results=[{statement, based_on}, ...] lists this step's results; each result must ${citeRule}. ` +
    "dropped=[{id, reason}] sets aside an earlier result no later step will use; before verification every earlier result is used by a later step or dropped.";
  let finish: string;
  if (step.kind === "verify") {
    finish =
      entry.situation === "review"
        ? "Finish with report_verification(outcome='done', findings=...) listing each finding with its evidence, responsible step, and recommended change."
        : "Before finishing, capture the result (capture with kind 'result') after the last change, and what it is compared with: its references or " +
          "accepted views (kind 'comparison'), or the work before (kind 'before'). Then finish with report_verification: outcome 'ready' when nothing " +
          "remains to correct, or the number (0–9) of the procedure step responsible for the earliest discrepancy, with findings naming the evidence. " +
          "'ready' hands the work to the user; report what was measured and checked, never that it is good, clean, better, or fixed.";
  } else if (step.kind === "trace") {
    finish = `Finish with complete_step(handoff=..., results=..., responsible_step=<0–9>) naming the cause and the procedure step where it lies. ${resultsRule}`;
  } else {
    finish = `When this step's result exists, call complete_step with a short handoff naming the actual result and how the next step uses it. ${resultsRule}`;
  }
  finish +=
    " If the decision belongs to a parent scope or another situation, call escalate instead. If a discovery changes the plan, call submit_plan again with the revised plan.";
  const first = numbers.length ? numbers[0] : VERIFY_STEP;
  parts.push(
    "## Now",
    `Announce: "I'm on ${situation} step ${step.number}: ${step.title}, working in procedure step ${first} ([decide or keep]). ` +
      `This step requires [operation]. For this assignment, I'll [the planned action, made specific]."`,
    finish,
  );
  return parts.filter(Boolean).join("\n\n");
}

function afterMove(lib: Library, session: Session, index: number): string {
  if (session.current === index && session.status === "active") return renderStep(lib, session);
  const finished = entryLabel(session.entries[index]);
  if (session.status === "complete") return `${finished} is done.\n\n` + closing(lib, session);
  return `${finished} is done.\n\nEntries:\n${plan(lib, session)}\n\n` + renderStep(lib, session);
}

const text = (value: string) => ({ content: [{ type: "text" as const, text: value }] });

async function guarded(run: () => Promise<string>) {
  try {
    return text(await run());
  } catch (error) {
    if (error instanceof EngineError) return text(`Not done: ${error.message}`);
    throw error;
  }
}

export function createServer(lib: Library, store: Store, opts: { origin?: string } = {}): McpServer {
  const origin = opts.origin ?? "https://<this-site>";
  const server = new McpServer({ name: "taskmaster", version: VERSION }, { instructions: INSTRUCTIONS });

  const load = async (sessionId: string) => {
    const session = await store.load(sessionId.trim());
    if (!session) throw new EngineError(`No session '${sessionId}'. Call get_status without a session_id to list recent sessions.`);
    return session;
  };

  server.registerTool(
    "get_matrix",
    { description: "Return the scope and situation matrix with its selector questions. Call this before start_session." },
    async () =>
      text(
        `${lib.matrix}\n\nSituation values: ${Object.entries(SITUATIONS).map(([k, v]) => `${k} (${v})`).join(", ")}\n` +
          `Scope values: ${Object.entries(SCOPES).map(([k, v]) => `${k} (${v})`).join(", ")}`,
      ),
  );

  server.registerTool(
    "start_session",
    {
      description:
        "Start a design session and receive its session_id, the working method, and the first entry's SOP. request: the user's own words, " +
        "copied exactly. end_goal: the observable condition that holds when the work is complete. entries: the matrix entries in the order " +
        "they will run, worked backward from the end goal. task_conditions: device, platform, audience, available assets, and stage of " +
        "completion. constraints: what the user said must be kept or followed, such as an existing identity, each with the user's words " +
        "quoted from the request. A constraint without the user's words is refused; that decision stays open.",
      inputSchema: {
        request: z.string(),
        end_goal: z.string(),
        entries: entriesSchema,
        task_conditions: z.string().optional(),
        constraints: constraintsSchema.optional(),
      },
    },
    async ({ request, end_goal, entries, task_conditions, constraints }) =>
      guarded(async () => {
        const session = newSession(request, end_goal, entries, task_conditions ?? "", constraints ?? []);
        await store.save(session);
        return (
          `Session ${session.id} started. Pass session_id='${session.id}' with every call for this work.\n\nEntries:\n${plan(lib, session)}\n\n` +
          renderStep(lib, session, { preamble: true })
        );
      }),
  );

  server.registerTool(
    "submit_plan",
    {
      description: "Write or revise the plan for the current entry: one item per SOP step, in order. The first plan starts the work.",
      inputSchema: { session_id: sessionIdSchema, plan: planSchema },
    },
    async ({ session_id, plan: items }) =>
      guarded(async () => {
        const session = await load(session_id);
        const starting = submitPlan(lib, session, items);
        await store.save(session);
        return (starting ? "Plan accepted.\n\n" : "Plan revised. Continue with the current step.\n\n") + renderStep(lib, session);
      }),
  );

  server.registerTool(
    "current_step",
    {
      description: "Re-issue the current step with its SOP, plan item, procedure text, and earlier results. Use after an interruption or condensed context.",
      inputSchema: { session_id: sessionIdSchema },
    },
    async ({ session_id }) => guarded(async () => renderStep(lib, await load(session_id), { briefing: true })),
  );

  server.registerTool(
    "complete_step",
    {
      description:
        "Finish the current SOP step (not a verify step) and receive the next one. handoff: the actual result and how the next step uses it. " +
        "results: this step's results, each {statement, based_on}; based_on lists the IDs of the earlier results it builds on (shown in each " +
        "step as 2.1, 3.2, ...); the first step cites 'request' or constraint IDs. responsible_step: required on a trace step — the procedure " +
        "step (0–9) where the cause lies. dropped: earlier results no later step will use, each {id, reason}.",
      inputSchema: {
        session_id: sessionIdSchema,
        handoff: z.string(),
        results: resultsSchema,
        responsible_step: z.number().int().optional(),
        dropped: dropsSchema.optional(),
      },
    },
    async ({ session_id, handoff, results, responsible_step, dropped }) =>
      guarded(async () => {
        const session = await load(session_id);
        const index = session.current;
        completeStep(lib, session, handoff, responsible_step ?? null, results, dropped ?? []);
        await store.save(session);
        return afterMove(lib, session, index);
      }),
  );

  server.registerTool(
    "report_verification",
    {
      description:
        "Finish a verify step. outcome: 'ready' when nothing remains to correct, which hands the work to the user for their verdict; or the " +
        "number (0–9) of the procedure step responsible for the earliest discrepancy. A Review finishes with 'done' and its findings. " +
        "findings: each discrepancy with its evidence and responsible step, or what was measured and checked when ready.",
      inputSchema: { session_id: sessionIdSchema, outcome: z.string(), findings: z.string().optional() },
    },
    async ({ session_id, outcome, findings }) =>
      guarded(async () => {
        const session = await load(session_id);
        const index = session.current;
        reportVerification(lib, session, outcome, findings ?? "");
        await store.save(session);
        return afterMove(lib, session, index);
      }),
  );

  server.registerTool(
    "escalate",
    {
      description:
        "End the current entry because its decision belongs elsewhere, and start the right entry in its place. Use when the unit should not " +
        "exist or should move (escalate to its parent scope), or when a Fix needs the structure replaced (escalate to redesign). reason: what the step showed.",
      inputSchema: { session_id: sessionIdSchema, reason: z.string(), to_scope: z.enum(scopeKeys).optional(), to_situation: z.enum(situationKeys).optional() },
    },
    async ({ session_id, reason, to_scope, to_situation }) =>
      guarded(async () => {
        const session = await load(session_id);
        escalate(session, reason, to_scope ?? null, to_situation ?? null);
        await store.save(session);
        return `Escalated.\n\nEntries:\n${plan(lib, session)}\n\n` + renderStep(lib, session);
      }),
  );

  server.registerTool(
    "capture",
    {
      description:
        "Capture a page at 1440, 820 and 390 pixels wide for the current entry. kind: 'result' for the work as built (after its last change), " +
        "'comparison' for a reference or accepted view it is compared with, 'before' for the work before it changed. This connector can't open " +
        "your pages, so call it first without manifest to get the capture command, run that command, then call it again with manifest set to " +
        "the JSON the command printed. Captures recorded this way are marked as taken by the agent.",
      inputSchema: {
        session_id: sessionIdSchema,
        kind: z.enum(["result", "comparison", "before"]),
        url: z.string(),
        label: z.string().optional(),
        selector: z.string().optional(),
        manifest: z.union([z.string(), z.record(z.string(), z.any())]).optional(),
      },
    },
    async ({ session_id, kind, url, label, selector, manifest }) =>
      guarded(async () => {
        const session = await load(session_id);
        const entry = currentEntry(session);
        if (!entry) throw new EngineError(`Session ${session.id} is ${session.status}.`);
        if (!manifest) {
          const index = session.entries.indexOf(entry) + 1;
          const slug = (label || kind).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
          const name = `entry-${index}-${entry.captures.length + 1}-${kind}-${slug}`;
          const quoted = (v: string) => `'${v.replace(/'/g, "'\\''")}'`;
          return [
            "Run this where the page can be opened (it needs Node.js and Playwright):",
            `curl -fsSL ${origin}/capture.mjs -o taskmaster-capture.mjs && node taskmaster-capture.mjs --out taskmaster-captures/${session.id} ` +
              `--name ${name}${selector ? ` --selector ${quoted(selector)}` : ""} ${quoted(url)}`,
            `Then call capture again with the same session_id, kind '${kind}', url, label and selector, and manifest set to the JSON it printed.`,
          ].join("\n\n");
        }
        const parsed = typeof manifest === "string" ? JSON.parse(manifest) : manifest;
        if (parsed?.url && parsed.url !== url) throw new EngineError(`The manifest is for ${parsed.url}, not ${url}.`);
        const recorded = addCapture(session, kind, label ?? "", parsed, "agent");
        await store.save(session);
        return [
          `Recorded ${recorded.kind} '${recorded.label}' at ${CAPTURE_WIDTHS.join(", ")} (taken by the agent):`,
          ...recorded.widths.map((w) => `- ${w.width}: page ${w.page_height}px${w.overflow ? ", scrolls sideways" : ""} — ${w.page?.file ?? ""}`),
        ].join("\n");
      }),
  );

  server.registerTool(
    "get_process_step",
    {
      description: "Return one procedure step from process.txt in full (0–10), for steps an SOP step names only by its Keep rule.",
      inputSchema: { step: z.number().int() },
    },
    async ({ step }) =>
      guarded(async () => {
        const proc = lib.procedure.steps.get(step);
        if (!proc) throw new EngineError("Procedure steps are numbered 0 to 10.");
        return proc.text;
      }),
  );

  server.registerTool(
    "add_entries",
    {
      description:
        "Add matrix entries to a session, after the current entry ('next') or at the end. Use when the work needs another entry, " +
        "such as a Fix or Redesign the user authorized after a Review.",
      inputSchema: { session_id: sessionIdSchema, entries: entriesSchema, position: z.enum(["next", "end"]).optional() },
    },
    async ({ session_id, entries, position }) =>
      guarded(async () => {
        const session = await load(session_id);
        const wasComplete = session.status === "complete";
        addEntries(session, entries, position ?? "next");
        await store.save(session);
        let out = `Entries updated:\n${plan(lib, session)}`;
        if (wasComplete) out += "\n\n" + renderStep(lib, session);
        return out;
      }),
  );

  server.registerTool(
    "get_status",
    {
      description: "Show a session's goal, entries, plan, position, and recorded results. Without a session_id, list recent sessions.",
      inputSchema: { session_id: z.string().optional() },
    },
    async ({ session_id }) =>
      guarded(async () => {
        if (!session_id?.trim()) {
          const recent = await store.recent();
          if (!recent.length) return "No sessions yet. Call get_matrix, then start_session.";
          return "Recent sessions (pass one as session_id):\n" + recent.map((s) => `- ${s.id} [${s.status}] ${s.request.slice(0, 80)}`).join("\n");
        }
        const session = await load(session_id);
        const lines = [`Session ${session.id} [${session.status}]`, `Request: ${session.request}`, `End goal: ${session.end_goal}`];
        if (session.conditions) lines.push(`Task conditions: ${session.conditions}`);
        lines.push("", "Entries:", plan(lib, session));
        session.entries.forEach((entry, i) => {
          if (!entry.plan.length && !entry.handoffs.length && !entry.note) return;
          lines.push("", `Entry ${i + 1} (${entryLabel(entry)}):`);
          if (entry.note) lines.push(entry.note);
          const running = entry.status === "active" && entry.phase === "run";
          sopSteps(lib, entry).forEach((step, n) => {
            if (n >= entry.plan.length) return;
            const mark = running && n === entry.index ? "▶" : running && n > entry.index ? "·" : "✓";
            lines.push(`${mark} ${step.number}. ${step.title}: ${entry.plan[n]}`);
          });
          for (const h of entry.handoffs) lines.push(`- pass ${h.iteration}, SOP step ${h.sop_step}: ${h.text}`);
          const results = earlierResults(entry, sopSteps(lib, entry));
          if (results) lines.push("Results:", results);
          if (entry.captures.length) lines.push("Captures:", captureLines(entry));
          for (const v of entry.verifications) {
            lines.push(`- pass ${v.iteration}, verify at SOP step ${v.sop_step}: ${v.outcome}${v.findings ? ` — ${v.findings}` : ""}`);
          }
          if (entry.awaiting_user) lines.push("Waiting for the user's verdict.");
        });
        if (session.constraints.length) {
          lines.push("", "Constraints, in the user's words:", ...session.constraints.map((c) => `- ${c.id}: ${c.text} — "${c.quote}"`));
        }
        return lines.join("\n");
      }),
  );

  server.registerTool(
    "end_session",
    {
      description: "End a session. summary: what was delivered and any remaining limitations.",
      inputSchema: { session_id: sessionIdSchema, summary: z.string().optional() },
    },
    async ({ session_id, summary }) =>
      guarded(async () => {
        const session = await load(session_id);
        endSession(session, summary ?? "");
        await store.save(session);
        return `Session ${session.id} ended.\n\n${plan(lib, session)}`;
      }),
  );

  const plain = (uri: URL, body: string) => ({ contents: [{ uri: uri.href, mimeType: "text/plain", text: body }] });

  server.registerResource("process", "taskmaster://design/process", { description: "The full design procedure.", mimeType: "text/plain" }, async (uri) =>
    plain(uri, lib.procedure.fullText),
  );
  server.registerResource("matrix", "taskmaster://design/matrix", { description: "The scope and situation matrix.", mimeType: "text/plain" }, async (uri) =>
    plain(uri, lib.matrix),
  );
  server.registerResource(
    "situation",
    new ResourceTemplate("taskmaster://design/situations/{name}", { list: undefined }),
    { description: "A situation SOP: create, extend, redesign, fix, or review.", mimeType: "text/plain" },
    async (uri, { name }) => plain(uri, lib.situations[String(name) as SituationKey]?.fullText ?? `No situation ${name}`),
  );
  server.registerResource(
    "scope",
    new ResourceTemplate("taskmaster://design/scopes/{name}", { list: undefined }),
    { description: "A scope sheet: element, component, section, page, flow, product, or shared-styles.", mimeType: "text/plain" },
    async (uri, { name }) => plain(uri, lib.scopes[String(name) as ScopeKey]?.fullText ?? `No scope ${name}`),
  );

  server.registerPrompt(
    "design",
    { description: "Run a design request through Taskmaster.", argsSchema: { request: z.string() } },
    ({ request }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text:
              `Use Taskmaster for this design request: ${request}\n\n` +
              "Call get_matrix and choose the matrix entries that get from the current state to the end goal. " +
              "Call start_session, write the plan for each entry's SOP with submit_plan before any work, " +
              "then execute each step Taskmaster gives you in order.",
          },
        },
      ],
    }),
  );

  return server;
}
