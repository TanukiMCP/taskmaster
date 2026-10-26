// The Taskmaster MCP server: tools, resources, and prompt. Mirrors taskmaster/server.py.

import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import {
  EngineError,
  addEntries,
  completeStep,
  currentEntry,
  endSession,
  entryLabel,
  latestHandoffs,
  modeFor,
  newSession,
  reportVerification,
  type Session,
} from "./engine.ts";
import { SCOPES, SITUATIONS, VERIFY_STEP, ruleFor, type Library, type ScopeKey, type SituationKey } from "./library.ts";
import type { Store } from "./store.ts";

export const VERSION = "2.0.0";

export const INSTRUCTIONS = `Taskmaster runs design work as a sequence of prompts chosen from the scope and situation matrix.

1. Call get_matrix. Choose each situation with its selector questions and the smallest scope that contains every decision to change.
2. Work backward from the end goal: list the matrix entries, in order, that get from the current state to the goal. One entry per situation × scope; "redesign the landing page and add a pricing page" is improve × page, then extend × page.
3. Call start_session with the request, the end goal, and those entries. Taskmaster replies with the procedure's working method and the first step.
4. Execute exactly the step you are given, using its full text as the authority. Announce it in chat first. When its result exists, call complete_step with a one-to-three sentence handoff naming the actual result.
5. Step 10 ends with report_verification: 'done', or the number of the step responsible for a discrepancy. Taskmaster reruns from that step.
6. current_step re-issues the step after an interruption or condensed context. get_status shows the whole plan.

Do not keep your own tasklist or tracking document for this work; Taskmaster holds the sequence.`;

const situationKeys = Object.keys(SITUATIONS) as [SituationKey, ...SituationKey[]];
const scopeKeys = Object.keys(SCOPES) as [ScopeKey, ...ScopeKey[]];

const entrySchema = z.object({
  situation: z.enum(situationKeys).describe("create, extend, improve, fix, or review — chosen with the matrix selector questions"),
  scope: z.enum(scopeKeys).describe("component, page, flow, shared-styles, or product — the smallest unit containing every decision to change"),
  goal: z.string().describe("What this entry must achieve, worked backward from the session's end goal"),
});
const entriesSchema = z.array(entrySchema).describe("Ordered matrix entries, each {situation, scope, goal}");

function plan(session: Session): string {
  return session.entries
    .map((entry, i) => {
      const marker = { done: "✓", active: "▶", pending: "·" }[entry.status];
      let where = "";
      if (entry.status === "active" && entry.step !== null) {
        where = ` — step ${entry.step}${entry.phase === "diagnosis" ? " (diagnosis)" : ""}, pass ${entry.iteration}`;
      }
      return `${marker} ${i + 1}. ${entryLabel(entry)}: ${entry.goal}${where}`;
    })
    .join("\n");
}

function briefing(lib: Library, session: Session): string {
  const entry = currentEntry(session)!;
  const situation = lib.situations[entry.situation];
  const scope = lib.scopes[entry.scope];
  const parts = [
    `# Entry ${session.current + 1} of ${session.entries.length}: ${entryLabel(entry)}`,
    `Entry goal: ${entry.goal}`,
    "## Situation",
    situation.header,
  ];
  if (situation.completion) parts.push(`Completion: ${situation.completion}`);
  parts.push("## Scope", scope.header);
  if (scope.expansion) parts.push(`Expansion: ${scope.expansion}`);
  return parts.join("\n\n");
}

function closing(session: Session): string {
  if (session.status === "complete") {
    return (
      `All ${session.entries.length} entries are done for session ${session.id}.\n\n${plan(session)}\n\n` +
      "Deliver the result as the final situation's completion describes, then call end_session with a summary. " +
      "Use add_entries if more work is needed."
    );
  }
  return `Session ${session.id} is ${session.status}.`;
}

export function renderStep(lib: Library, session: Session, opts: { briefing?: boolean; preamble?: boolean } = {}): string {
  const entry = currentEntry(session);
  if (!entry || entry.step === null) return closing(session);
  const step = lib.procedure.steps.get(entry.step)!;
  const situation = lib.situations[entry.situation];
  const scope = lib.scopes[entry.scope];
  const mode = modeFor(lib, entry, entry.step);

  const parts: string[] = [];
  if (opts.preamble) parts.push("# Working method (process.txt, read once and keep as the authority)", lib.procedure.preamble);
  if (opts.briefing) parts.push(briefing(lib, session));

  parts.push(`# Step ${entry.step}: ${step.name} — ${mode}`);
  const context = [
    `Session end goal: ${session.end_goal}`,
    `Entry ${session.current + 1} of ${session.entries.length}: ${entryLabel(entry)} — ${entry.goal}`,
  ];
  if (session.conditions) context.push(`Task conditions: ${session.conditions}`);
  if (entry.iteration > 1 && entry.k !== null) {
    context.push(`Pass ${entry.iteration}: rerunning from step ${entry.k} after verification. Results before step ${entry.k} are reused unchanged.`);
  }
  parts.push(context.join("\n"));

  if (entry.phase === "diagnosis") parts.push(`## Diagnosis (${situation.title})`, situation.diagnosis);
  else parts.push(`## Situation rule (${situation.title}, step ${entry.step})`, ruleFor(situation, entry.step, entry.k) || "Follow the situation's permissions.");
  parts.push(`## Scope limit (${scope.title}, step ${entry.step})`, scope.limits.get(entry.step)!);

  const earlier = latestHandoffs(entry, entry.step);
  if (earlier.length) {
    parts.push(
      "## Earlier results in this entry",
      earlier.map(([n, h]) => `- Step ${n} (${lib.procedure.steps.get(n)!.name}): ${h.text}`).join("\n"),
    );
  }
  const last = entry.verifications.at(-1);
  if (last?.findings && entry.phase === "chain") parts.push("## Latest verification findings", last.findings);

  parts.push(`## Procedure step ${entry.step} (verbatim)`, step.text);

  let finish: string;
  if (entry.step === VERIFY_STEP) {
    if (entry.situation === "review") {
      finish = "Finish with report_verification(outcome='done', findings=...) listing each finding with its evidence, responsible step, and recommended change.";
    } else if (entry.phase === "diagnosis") {
      finish =
        "Finish with report_verification: the number (0–9) of the responsible step to rerun from, with findings listing each discrepancy and its step. Report 'done' only if nothing needs to change.";
    } else {
      finish =
        "Finish with report_verification: outcome 'done' when nothing remains to correct, or the number (0–9) of the step responsible for the earliest discrepancy, with findings naming the evidence.";
    }
  } else {
    finish = "When this step's result exists, call complete_step with a short handoff naming the actual result and how the next step uses it.";
  }
  parts.push(
    "## Now",
    `Announce: "I'm on step ${entry.step}: ${step.name}, ${mode}. This step requires [operation]. For this assignment, I'll [specific action]."`,
    finish,
  );
  return parts.filter(Boolean).join("\n\n");
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

export function createServer(lib: Library, store: Store): McpServer {
  const server = new McpServer({ name: "taskmaster", version: VERSION }, { instructions: INSTRUCTIONS });

  const active = async () => {
    const session = await store.active();
    if (!session) throw new EngineError("No active session. Call get_matrix, then start_session.");
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
        "Start a design session. request: the user's words. end_goal: the observable condition that holds when the work is complete. " +
        "entries: the matrix entries in the order they will run, worked backward from the end goal. task_conditions: device, platform, " +
        "audience, existing identity, available assets, stage of completion, and whether identity is open to change.",
      inputSchema: {
        request: z.string(),
        end_goal: z.string(),
        entries: entriesSchema,
        task_conditions: z.string().optional(),
      },
    },
    async ({ request, end_goal, entries, task_conditions }) =>
      guarded(async () => {
        const session = newSession(request, end_goal, entries, task_conditions ?? "");
        const previous = await store.active();
        await store.save(session);
        await store.setActive(session.id);
        const note =
          previous && previous.status === "active"
            ? `\n\nSession ${previous.id} was paused; resume_session('${previous.id}') returns to it.`
            : "";
        return `Session ${session.id} started.\n\nPlan:\n${plan(session)}${note}\n\n` + renderStep(lib, session, { briefing: true, preamble: true });
      }),
  );

  server.registerTool(
    "current_step",
    { description: "Re-issue the current step with its full text, rules, and earlier results. Use after an interruption or condensed context." },
    async () => guarded(async () => renderStep(lib, await active(), { briefing: true })),
  );

  server.registerTool(
    "complete_step",
    {
      description: "Finish the current step (not step 10) and receive the next one. handoff: one to three sentences naming the actual result and how the next step uses it.",
      inputSchema: { handoff: z.string().optional() },
    },
    async ({ handoff }) =>
      guarded(async () => {
        const session = await active();
        completeStep(session, handoff ?? "");
        await store.save(session);
        return renderStep(lib, session);
      }),
  );

  server.registerTool(
    "report_verification",
    {
      description:
        "Finish step 10. outcome: 'done', or the number (0–9) of the step responsible for the earliest discrepancy. " +
        "findings: each discrepancy with its evidence and responsible step, or what was checked when done.",
      inputSchema: { outcome: z.string(), findings: z.string().optional() },
    },
    async ({ outcome, findings }) =>
      guarded(async () => {
        const session = await active();
        const index = session.current;
        const result = reportVerification(session, outcome, findings ?? "");
        await store.save(session);
        if (result === "rerun") return renderStep(lib, session);
        const finished = entryLabel(session.entries[index]);
        if (session.status === "complete") return `${finished} is done.\n\n` + closing(session);
        return `${finished} is done.\n\nPlan:\n${plan(session)}\n\n` + renderStep(lib, session, { briefing: true });
      }),
  );

  server.registerTool(
    "add_entries",
    {
      description:
        "Add matrix entries to the active session's plan, after the current entry ('next') or at the end. " +
        "Use when the work needs another entry, such as a Fix or Improve the user authorized after a Review.",
      inputSchema: { entries: entriesSchema, position: z.enum(["next", "end"]).optional() },
    },
    async ({ entries, position }) =>
      guarded(async () => {
        const session = await active();
        const wasComplete = session.status === "complete";
        addEntries(session, entries, position ?? "next");
        await store.save(session);
        let out = `Plan updated:\n${plan(session)}`;
        if (wasComplete) out += "\n\n" + renderStep(lib, session, { briefing: true });
        return out;
      }),
  );

  server.registerTool(
    "get_status",
    { description: "Show the active session's goal, plan, position, and recorded results, or recent sessions when none is active." },
    async () => {
      const session = await store.active();
      if (!session) {
        const recent = await store.recent();
        if (!recent.length) return text("No sessions yet. Call get_matrix, then start_session.");
        return text("No active session. Recent sessions:\n" + recent.map((s) => `- ${s.id} [${s.status}] ${s.request.slice(0, 80)}`).join("\n"));
      }
      const lines = [`Session ${session.id} [${session.status}]`, `Request: ${session.request}`, `End goal: ${session.end_goal}`];
      if (session.conditions) lines.push(`Task conditions: ${session.conditions}`);
      lines.push("", "Plan:", plan(session));
      session.entries.forEach((entry, i) => {
        if (!entry.handoffs.length && !entry.verifications.length) return;
        lines.push("", `Entry ${i + 1} results (${entryLabel(entry)}):`);
        for (const h of entry.handoffs) {
          lines.push(`- pass ${h.iteration}, step ${h.step} ${lib.procedure.steps.get(h.step)!.name}: ${h.text}`);
        }
        for (const v of entry.verifications) {
          lines.push(`- pass ${v.iteration}, ${v.phase}: ${v.outcome}${v.findings ? ` — ${v.findings}` : ""}`);
        }
      });
      return text(lines.join("\n"));
    },
  );

  server.registerTool(
    "resume_session",
    { description: "Make an earlier session active again and re-issue its current step.", inputSchema: { session_id: z.string() } },
    async ({ session_id }) =>
      guarded(async () => {
        const session = await store.load(session_id.trim());
        if (!session) throw new EngineError(`No session ${session_id}. get_status lists recent sessions.`);
        if (session.status === "ended") throw new EngineError(`Session ${session.id} has ended; start a new session.`);
        await store.setActive(session.id);
        return `Resumed session ${session.id}.\n\nPlan:\n${plan(session)}\n\n` + renderStep(lib, session, { briefing: true, preamble: true });
      }),
  );

  server.registerTool(
    "end_session",
    { description: "End the active session. summary: what was delivered and any remaining limitations.", inputSchema: { summary: z.string().optional() } },
    async ({ summary }) =>
      guarded(async () => {
        const session = await active();
        endSession(session, summary ?? "");
        await store.save(session);
        await store.setActive(null);
        return `Session ${session.id} ended.\n\n${plan(session)}`;
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
    { description: "A situation prompt: create, extend, improve, fix, or review.", mimeType: "text/plain" },
    async (uri, { name }) => plain(uri, lib.situations[String(name) as SituationKey]?.fullText ?? `No situation ${name}`),
  );
  server.registerResource(
    "scope",
    new ResourceTemplate("taskmaster://design/scopes/{name}", { list: undefined }),
    { description: "A scope prompt: component, page, flow, shared-styles, or product.", mimeType: "text/plain" },
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
              "Call get_matrix, choose the matrix entries that get from the current state to the end goal, " +
              "then call start_session and execute each step it gives you in order.",
          },
        },
      ],
    }),
  );

  return server;
}
