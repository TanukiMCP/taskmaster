import assert from "node:assert/strict";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";

import { DESIGN } from "../lib/design-data.ts";
import { completeStep, currentSopStep, escalate, newSession, reportVerification, sopSteps, submitPlan } from "../lib/engine.ts";
import { SCOPE_LABELS, loadLibrary, resolveRefs } from "../lib/library.ts";
import { createServer } from "../lib/server.ts";
import { MemoryKeyValue, Store } from "../lib/store.ts";

const lib = loadLibrary(DESIGN);
const textOf = (result: any) => result.content.map((c: any) => c.text).join("\n");

test("library parses the procedure, every SOP, and every scope sheet", () => {
  assert.equal(lib.procedure.steps.size, 11);
  assert.equal(lib.procedure.steps.get(3)!.name, "Name the jobs and adapt components from real products");
  assert.match(lib.procedure.workingRules, /Keeping is a stated decision/);
  for (const sop of Object.values(lib.situations)) {
    assert.ok(sop.brief && sop.mayChange && sop.mustPreserve && sop.completion);
    assert.ok(sop.steps.some((s) => s.kind === "verify"));
  }
  for (const sheet of Object.values(lib.scopes)) assert.deepEqual(Object.keys(sheet.atScope).sort(), Object.keys(SCOPE_LABELS).sort());
  const fix = lib.situations.fix;
  assert.deepEqual(resolveRefs(fix.steps[4], 7), [8, 9]);
});

test("engine plans first, traces the cause, and returns to it on verification", () => {
  const session = newSession("fix", "goal", [{ situation: "fix", scope: "component", goal: "g" }]);
  assert.throws(() => completeStep(lib, session, "early"), /Write the plan first/);
  submitPlan(lib, session, sopSteps(lib, session.entries[0]).map((s) => `plan ${s.number}`));
  completeStep(lib, session, "stated");
  completeStep(lib, session, "reproduced");
  assert.throws(() => completeStep(lib, session, "traced"), /responsible_step/);
  completeStep(lib, session, "traced", 5);
  assert.equal(currentSopStep(lib, session.entries[0]).title, "Correct the cause");
  completeStep(lib, session, "corrected");
  completeStep(lib, session, "carried");
  assert.equal(reportVerification(lib, session, "3", "control was the cause"), "rerun");
  assert.equal(session.entries[0].k, 3);
  assert.equal(currentSopStep(lib, session.entries[0]).title, "Correct the cause");
});

test("escalate replaces a section entry with its page", () => {
  const session = newSession("r", "g", [{ situation: "redesign", scope: "section", goal: "g" }]);
  escalate(session, "the section should not exist", "page");
  assert.equal(session.entries[0].status, "escalated");
  assert.equal(session.entries[1].scope, "page");
  assert.equal(session.current, 1);
});

test("full flow through an MCP client", async () => {
  const server = createServer(lib, new Store(new MemoryKeyValue()));
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  const client = new Client({ name: "test", version: "1" });
  await client.connect(clientSide);
  const call = async (name: string, args: Record<string, unknown>) => textOf(await client.callTool({ name, arguments: args }));

  const tools = (await client.listTools()).tools.map((t) => t.name);
  for (const name of ["get_matrix", "start_session", "submit_plan", "complete_step", "report_verification", "escalate", "get_process_step"]) {
    assert.ok(tools.includes(name), name);
  }
  assert.match(await call("get_matrix", {}), /Prompt selector/);

  const started = await call("start_session", {
    request: "The claims section shouldn't exist",
    end_goal: "Claims appear with their ingredients",
    entries: [{ situation: "fix", scope: "page", goal: "Remove the claims section" }],
  });
  assert.match(started, /## Situation SOP: Fix/);
  assert.match(started, /## Write your plan/);
  const sid = /Session (\w+) started/.exec(started)![1];

  const other = /Session (\w+) started/.exec(
    await call("start_session", { request: "Audit", end_goal: "Findings", entries: [{ situation: "review", scope: "page", goal: "Findings" }] }),
  )![1];
  assert.notEqual(other, sid);

  assert.match(await call("complete_step", { session_id: sid, handoff: "early" }), /^Not done: Write the plan first/);
  const plan = ["state", "reproduce", "trace", "correct", "carry", "verify"];
  assert.match(await call("submit_plan", { session_id: sid, plan }), /# Fix step 1 of 6: State the problem/);
  await call("complete_step", { session_id: sid, handoff: "stated" });
  assert.match(await call("complete_step", { session_id: sid, handoff: "reproduced" }), /Trace the cause \(trace\)/);
  const correct = await call("complete_step", { session_id: sid, handoff: "cause in step 2", responsible_step: 2 });
  assert.match(correct, /Fix step 4 of 6: Correct the cause/);
  assert.match(correct, /## Procedure step 2: Order the information \(verbatim\)/);
  assert.match(correct, /should exist at all/);
  assert.match(await call("current_step", { session_id: other }), /Write your plan/);
  assert.match(await call("get_process_step", { step: 8 }), /^8\. Construct layout/);
  assert.match(await call("get_status", { session_id: sid }), /▶ 4\. Correct the cause/);
  const listing = await call("get_status", {});
  assert.ok(listing.includes(sid) && listing.includes(other));
  assert.match(await call("escalate", { session_id: sid, reason: "structure is wrong", to_situation: "redesign" }), /Redesign × Page or view/);
  assert.match(await call("current_step", { session_id: "nope" }), /^Not done: No session/);
  assert.ok((await client.listPrompts()).prompts.some((p) => p.name === "design"));
  await client.close();
});

test("stateless HTTP transport answers a JSON-RPC request", async () => {
  const server = createServer(lib, new Store(new MemoryKeyValue()));
  const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  await server.connect(transport);
  const response = await transport.handleRequest(
    new Request("https://example.test/mcp/token", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "t", version: "1" } },
      }),
    }),
  );
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.result.serverInfo.name, "taskmaster");
});
