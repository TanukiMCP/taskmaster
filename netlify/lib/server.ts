// The Taskmaster MCP server: tools, resources, and prompt. Mirrors taskmaster/server.py.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import {
  EngineError,
  changedInputs,
  compose,
  downstream,
  finish,
  latest,
  newSession,
  operation,
  ready,
  record,
  revise,
  states,
  upstream,
  version,
  type Operation,
  type Session,
} from "./engine.ts";
import { INDEX, readLibrary, type Library } from "./library.ts";
import type { Store } from "./store.ts";

export const VERSION = "3.0.0";

export const INSTRUCTIONS = `Taskmaster runs a task as a composition of operations, each building on the concrete results of the ones it needs. library('method') is the full working method.

1. start: the request, the concrete result it asks for, the value that makes that result worth having, and the starting information. You get a session_id; pass it to every later call. Other conversations may run their own sessions at the same time.
2. compose: derive the operations this task needs. Each has an id, the operations whose outputs it needs (listed before it), what it does for this task, and the concrete output it produces. For product or interface design work, read library('design') to choose a situation and scope, then adopt the ready composition from library('design/<situation>/<scope>').
3. Work the operation Taskmaster gives you, using the results it builds on and its guide. Announce it in chat first. When its output exists, call record with the output, how it still serves the value, and the assumptions it rests on. An operation can't be recorded until everything it needs is current.
4. When evidence shows an earlier output or assumption is wrong, call revise on that operation: everything built on it becomes stale and is redone or confirmed. When the work needs a missing operation or a different decomposition, call compose again with the reason.
5. When every operation is current, deliver the result and call finish with what was delivered, what was actually checked, and what remains limited.

next re-issues the current operation after an interruption or condensed context; without a session_id it lists recent sessions. Keep no other tasklist or tracking document: the composition lives in Taskmaster.`;

const COMPOSE_GUIDE = `Derive the operations this task needs from the request, the starting information, the result, and the value. Give each one:
- id: a short lowercase name.
- needs: the ids of the operations whose outputs it consumes, each listed before it. Leave out dependencies that aren't real.
- does: the specific work it does for this task and the questions it must answer.
- produces: the concrete output the operations after it use: a decision, a model, an artifact, or evidence, not another paragraph.
- guide (optional): a library reference whose text comes with the operation.
Then call compose(session_id, operations=[...]).

Ready compositions: for product or interface design work, read library('design') to choose a situation and scope, then library('design/<situation>/<scope>') and adopt its composition, writing each "does" for this task.`;

// Some clients send arrays as JSON strings; accept both.
const jsonList = <T extends z.ZodTypeAny>(schema: T) =>
  z.preprocess((value) => {
    if (typeof value !== "string") return value;
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }, schema);

const operationSchema = z.object({
  id: z.string().describe("Short lowercase name, unique in the session, such as 'question' or 'pricing.layout'"),
  needs: z.array(z.string()).optional().describe("Ids of the operations whose outputs this one consumes; each must be listed before it"),
  does: z.string().optional().describe("What this operation does for this task: the specific work and the questions it must answer"),
  produces: z.string().optional().describe("The concrete output it produces for the operations that need it"),
  guide: z.string().optional().describe("Optional library reference whose text comes with the operation, such as design/redesign/page#research"),
});
const operationsSchema = jsonList(z.array(operationSchema)).describe(
  "The operations in an order where each comes after what it needs. When revising, an item with only an id keeps that operation as it is.",
);
const sessionIdSchema = z.string().describe("The session_id start returned");

function header(session: Session): string {
  const lines = [
    `Session ${session.id}: pass session_id='${session.id}' with every call.`,
    `Result to produce: ${session.result}`,
    `Value to preserve: ${session.value}`,
  ];
  if (session.starting) lines.push(`Starting information: ${session.starting}`);
  return lines.join("\n");
}

export function overview(session: Session): string {
  const state = states(session);
  const first = ready(session, state)[0]?.id;
  const marks = { current: "✓", stale: "↻", open: "○" };
  const lines = session.operations.map((op) => {
    const needs = op.needs.length ? ` ← ${op.needs.join(", ")}` : "";
    const label = state[op.id] + (op.id === first ? ", next" : "");
    return `${op.id === first ? "▶" : marks[state[op.id]]} ${op.id}${needs} (${label})`;
  });
  const done = Object.values(state).filter((s) => s === "current").length;
  return `Operations, ${done} of ${session.operations.length} current:\n` + lines.join("\n");
}

function resultBlock(op: Operation): string {
  const last = latest(op)!;
  const lines = [`### ${op.id} (v${last.version})`, last.output];
  if (last.assumptions.length) lines.push("Assumptions: " + last.assumptions.join("; "));
  if (last.evidence) lines.push(`Evidence: ${last.evidence}`);
  return lines.join("\n");
}

function finished(session: Session): string {
  const lines = [`Session ${session.id} is finished.`, `Delivered: ${session.delivered}`, `Evidence: ${session.evidence}`];
  if (session.limitations) lines.push(`Limitations: ${session.limitations}`);
  return lines.join("\n");
}

// The operation to work on now. With full, the outputs it builds on come in full, for resuming after
// an interruption or condensed context; otherwise they are named, since the agent recorded them itself.
export function renderNext(lib: Library, session: Session, full = false): string {
  if (session.status === "finished") return finished(session);
  if (!session.operations.length) return `${header(session)}\n\nNo operations yet.\n\n${COMPOSE_GUIDE}`;
  const state = states(session);
  const candidates = ready(session, state);
  if (!candidates.length) {
    return (
      `All ${session.operations.length} operations are current.\n\nDeliver the result: ${session.result}\n\n` +
      `Then call finish(session_id='${session.id}', delivered=..., evidence=..., limitations=...): what was delivered and how to ` +
      "reach it; what was actually checked, that it works as built and separately that it achieves its purpose; and what remains limited."
    );
  }
  const op = candidates[0];
  const revised = state[op.id] === "open" && latest(op) !== null;
  const label = state[op.id] === "stale" ? "stale" : revised ? "revised" : "open";
  const parts = [`# Next: ${op.id} (${label})`, header(session)];

  const lines = [`Does: ${op.does}`, `Produces: ${op.produces}`];
  lines.push(op.needs.length ? `Needs: ${op.needs.join(", ")}` : "Needs: nothing; it starts from the starting information.");
  const builtOn = downstream(session, op.id);
  lines.push(
    builtOn.length
      ? `Built on it: ${builtOn.length} later operation${builtOn.length !== 1 ? "s" : ""} (${builtOn.map((o) => o.id).join(", ")}). ` +
          "Give it effort in proportion to that and to how uncertain it is."
      : "Built on it: nothing later; its output is the requested result.",
  );
  parts.push("## This operation", lines.join("\n"));

  if (state[op.id] === "stale") {
    parts.push(
      "## Why it is stale",
      `It was built on inputs that have changed: ${changedInputs(session, op).join("; ")}. Its earlier output is below. ` +
        "Record a new output, or confirm the earlier one with still_holds if it holds against the changed inputs.",
      resultBlock(op),
    );
  } else if (revised) {
    const why = [...op.notes].reverse().find((n) => n.text.startsWith("Revised") || n.text.startsWith("Reopened"))?.text ?? "";
    parts.push("## Why it is open again", `${why}\nIts previous output is below.`, resultBlock(op));
  }

  const builtFrom = upstream(session, op.id);
  if (builtFrom.length && full) {
    parts.push("## Working state it builds on", builtFrom.map(resultBlock).join("\n\n"));
  } else if (builtFrom.length) {
    const named = builtFrom.map((o) => `${o.id} (v${version(o)})`).join(", ");
    parts.push(
      "## Builds on",
      `${named}\nThese outputs are already recorded. If they are no longer in your context, call next(session_id='${session.id}') for them in full.`,
    );
  }

  if (op.guide) parts.push(`## Guide: ${op.guide}`, readLibrary(lib, op.guide) ?? "This guide reference no longer names anything in the library.");

  const now = [
    `Say in chat what '${op.id}' will establish for this task, then do the work.`,
    `When its output exists, call record(session_id='${session.id}', operation='${op.id}', output=..., preserves=..., assumptions=[...], evidence=...).`,
  ];
  if (latest(op)) now.push(`If the earlier output still holds, call record(session_id='${session.id}', operation='${op.id}', still_holds='why').`);
  now.push(
    "If the work shows an earlier output or assumption is wrong, call revise on that operation. If it shows a missing operation " +
      "or a better decomposition, call compose with the change and the reason.",
  );
  const others = candidates.slice(1).map((o) => o.id);
  if (others.length) now.push(`Also ready, and recordable in any order: ${others.join(", ")}.`);
  parts.push("## Now", now.join("\n"));
  return parts.join("\n\n");
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

  const load = async (sessionId: string) => {
    const session = await store.load(sessionId.trim());
    if (!session) throw new EngineError(`No session '${sessionId}'. Call next without a session_id to list recent sessions.`);
    if (!Array.isArray(session.operations)) {
      throw new EngineError(`Session '${sessionId}' was made by an earlier version of Taskmaster and can't continue here. Start a new session.`);
    }
    return session;
  };

  server.registerTool(
    "start",
    {
      description: "Start a session and receive its session_id and the working method. Then derive the operations and call compose.",
      inputSchema: {
        request: z.string().describe("The user's words"),
        result: z.string().describe("The concrete result the request asks for"),
        value: z.string().describe("What makes that result worth having: the purpose, appeal, or experience every operation must preserve"),
        starting: z.string().optional().describe("The starting information: what exists, constraints, conditions, and available evidence"),
      },
    },
    async ({ request, result, value, starting }) =>
      guarded(async () => {
        const session = newSession(request, result, value, starting ?? "");
        await store.save(session);
        return [
          `Session ${session.id} started. Pass session_id='${session.id}' with every call for this work.`,
          "# Working method (library('method'); read it once and keep it as the authority)",
          lib.method,
          "# Now: derive the composition",
          COMPOSE_GUIDE,
        ].join("\n\n");
      }),
  );

  server.registerTool(
    "compose",
    {
      description:
        "Set the session's operations, or revise them. Operations kept unchanged keep their results; a recorded operation whose needs or output change is reopened; one left out is retired.",
      inputSchema: {
        session_id: sessionIdSchema,
        operations: operationsSchema,
        reason: z.string().optional().describe("Required when revising: what the work showed that changes the composition"),
      },
    },
    async ({ session_id, operations, reason }) =>
      guarded(async () => {
        const session = await load(session_id);
        for (const item of operations) {
          if (item.guide?.trim() && readLibrary(lib, item.guide) === null) {
            throw new EngineError(`'${item.id}' has guide '${item.guide}', which names nothing in the library. library() lists the references.`);
          }
        }
        const revising = session.operations.length > 0;
        const [reopened, warnings] = compose(session, operations, reason ?? "");
        await store.save(session);
        let head = revising ? `Composition revised: ${(reason ?? "").trim()}` : `Composition recorded: ${session.operations.length} operations.`;
        if (reopened.length) head += `\nReopened: ${reopened.join(", ")}.`;
        return [head, ...warnings, overview(session), renderNext(lib, session)].join("\n\n");
      }),
  );

  server.registerTool(
    "next",
    {
      description:
        "Show where a session stands and re-issue the operation to work on now, with the results it builds on in full. Use after an interruption or condensed context.",
      inputSchema: { session_id: z.string().optional().describe("The session_id; leave empty to list recent sessions") },
    },
    async ({ session_id }) =>
      guarded(async () => {
        if (!session_id?.trim()) {
          const recent = await store.recent();
          if (!recent.length) return "No sessions yet. Call start.";
          return "Recent sessions (pass one as session_id):\n" + recent.map((s) => `- ${s.id} [${s.status}] ${s.request.slice(0, 80)}`).join("\n");
        }
        const session = await load(session_id);
        if (!session.operations.length || session.status === "finished") return renderNext(lib, session);
        return `${overview(session)}\n\n${renderNext(lib, session, true)}`;
      }),
  );

  server.registerTool(
    "record",
    {
      description: "Record an operation's output and receive the next operation. Refused while anything it needs is missing or stale.",
      inputSchema: {
        session_id: sessionIdSchema,
        operation: z.string().describe("The operation's id"),
        output: z.string().optional().describe("The actual output: the concrete result the operation produces"),
        preserves: z.string().optional().describe("How this output still serves the session's value"),
        assumptions: jsonList(z.array(z.string()))
          .optional()
          .describe("Provisional assumptions this output rests on; if one fails, this operation is the one to revise"),
        evidence: z.string().optional().describe("Sources, observations, or checks that support the output"),
        still_holds: z
          .string()
          .optional()
          .describe("For a stale or revised operation: why its earlier output still holds against the changed inputs. Leaves the operations built on it current."),
      },
    },
    async ({ session_id, operation: opId, ...input }) =>
      guarded(async () => {
        const session = await load(session_id);
        const outcome = record(session, opId, input);
        await store.save(session);
        const op = operation(session, opId);
        const head = outcome === "confirmed" ? `Confirmed '${op.id}' v${version(op)} still holds.` : `Recorded '${op.id}' v${version(op)}.`;
        return `${head}\n\n${renderNext(lib, session)}`;
      }),
  );

  server.registerTool(
    "revise",
    {
      description:
        "Reopen an operation whose output or assumption no longer holds; everything built on it becomes stale. Or, with value or result, change the purpose explicitly; every recorded operation becomes stale.",
      inputSchema: {
        session_id: sessionIdSchema,
        reason: z.string().describe("The observation that undermines the output or assumption"),
        operation: z.string().optional().describe("The operation to reopen"),
        value: z.string().optional().describe("A new value, only when evidence requires changing the purpose itself"),
        result: z.string().optional().describe("A new requested result, only when evidence requires changing it"),
      },
    },
    async ({ session_id, reason, operation: opId, value, result }) =>
      guarded(async () => {
        const session = await load(session_id);
        const stale = revise(session, reason, opId ?? "", value ?? "", result ?? "");
        await store.save(session);
        let head = opId?.trim() ? `Reopened '${opId.trim()}'.` : "Purpose changed.";
        head += stale.length ? ` Now stale: ${stale.join(", ")}.` : " Nothing else was built on it yet.";
        return `${head}\n\n${overview(session)}\n\n${renderNext(lib, session)}`;
      }),
  );

  server.registerTool(
    "finish",
    {
      description: "Close the session with the delivered result, its evidence, and its remaining limitations.",
      inputSchema: {
        session_id: sessionIdSchema,
        delivered: z.string().describe("What was delivered and how to reach or use it"),
        evidence: z.string().describe("What was actually checked: that it works as built, and separately that it achieves its purpose"),
        limitations: z.string().optional().describe("What remains limited or unchecked; required when operations are not current"),
      },
    },
    async ({ session_id, delivered, evidence, limitations }) =>
      guarded(async () => {
        const session = await load(session_id);
        const unfinished = finish(session, delivered, evidence, limitations ?? "");
        await store.save(session);
        return finished(session) + (unfinished.length ? `\nNot current when it closed: ${unfinished.join(", ")}.` : "");
      }),
  );

  server.registerTool(
    "library",
    {
      description: "Read the library: the working method, the design matrix, a design entry's ready composition, or one procedure step.",
      inputSchema: {
        ref: z.string().optional().describe("A library reference, such as method, design, design/redesign/page, or design/process/5; empty lists them"),
      },
    },
    async ({ ref }) =>
      guarded(async () => {
        const found = readLibrary(lib, ref ?? "");
        if (found === null) throw new EngineError(`'${ref}' names nothing in the library.\n\n${INDEX}`);
        return found;
      }),
  );

  const plain = (uri: URL, body: string) => ({ contents: [{ uri: uri.href, mimeType: "text/plain", text: body }] });
  server.registerResource("method", "taskmaster://method", { description: "The working method Taskmaster runs.", mimeType: "text/plain" }, async (uri) =>
    plain(uri, lib.method),
  );
  server.registerResource("process", "taskmaster://design/process", { description: "The full design procedure.", mimeType: "text/plain" }, async (uri) =>
    plain(uri, lib.procedure.fullText),
  );
  server.registerResource(
    "matrix",
    "taskmaster://design/matrix",
    { description: "The design library's scope and situation matrix.", mimeType: "text/plain" },
    async (uri) => plain(uri, lib.matrix),
  );

  server.registerPrompt(
    "run",
    { description: "Run a request through Taskmaster.", argsSchema: { request: z.string() } },
    ({ request }) => ({
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text:
              `Use Taskmaster for this request: ${request}\n\n` +
              "Call start with the request, the concrete result it asks for, the value that makes that result worth having, and the " +
              "starting information. Derive the operations and call compose (for design work, adopt a ready composition from " +
              "library('design')). Then work each operation Taskmaster gives you and record its actual output before the next.",
          },
        },
      ],
    }),
  );

  return server;
}
