import assert from "node:assert/strict";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";

import { DESIGN } from "../lib/design-data.ts";
import {
  addCapture,
  completeStep,
  currentSopStep,
  escalate,
  newSession,
  recordVerdict,
  reportVerification,
  sopSteps,
  submitPlan,
  type Session,
} from "../lib/engine.ts";
import { handleReview } from "../lib/review.ts";
import { SCOPE_LABELS, loadLibrary, resolveRefs } from "../lib/library.ts";
import { createServer } from "../lib/server.ts";
import { MemoryKeyValue, Store } from "../lib/store.ts";

const lib = loadLibrary(DESIGN);
const textOf = (result: any) => result.content.map((c: any) => c.text).join("\n");

test("library parses the procedure, every SOP, and every scope sheet", () => {
  assert.equal(lib.procedure.steps.size, 11);
  assert.equal(lib.procedure.steps.get(3)!.name, "Name the jobs and port components from real products");
  assert.match(lib.procedure.workingRules, /Keeping is a stated decision/);
  for (const sop of Object.values(lib.situations)) {
    assert.ok(sop.brief && sop.mayChange && sop.mustPreserve && sop.completion);
    assert.ok(sop.steps.some((s) => s.kind === "verify"));
  }
  for (const sheet of Object.values(lib.scopes)) assert.deepEqual(Object.keys(sheet.atScope).sort(), Object.keys(SCOPE_LABELS).sort());
  const fix = lib.situations.fix;
  assert.deepEqual(resolveRefs(fix.steps[4], 7), [8, 9]);
});

// One result citing the latest earlier result, or the request on the first step.
function step(session: Session, k: number | null = null) {
  const entry = session.entries[session.current];
  const number = currentSopStep(lib, entry).number;
  const earlier = entry.results.filter((r) => r.sop_step < number).map((r) => r.id);
  completeStep(lib, session, "handoff", k, [{ statement: `result ${number}`, based_on: earlier.slice(-1).length ? earlier.slice(-1) : ["request"] }]);
}

const manifest = (url: string) => ({ url, widths: [1440, 820, 390].map((width) => ({ width, ok: true, page_height: 900, page: { file: `${width}.jpg` } })) });

test("engine plans first, traces the cause, and returns to it on verification", () => {
  const session = newSession("fix", "goal", [{ situation: "fix", scope: "component", goal: "g" }]);
  assert.throws(() => completeStep(lib, session, "early", null, [{ statement: "x", based_on: ["request"] }]), /Write the plan first/);
  submitPlan(lib, session, sopSteps(lib, session.entries[0]).map((s) => `plan ${s.number}`));
  assert.throws(() => completeStep(lib, session, "stated", null, []), /results are required/);
  step(session);
  assert.throws(() => completeStep(lib, session, "reproduced", null, [{ statement: "x", based_on: ["request"] }]), /cites no earlier result/);
  step(session);
  assert.throws(() => step(session), /responsible_step/);
  step(session, 5);
  assert.equal(currentSopStep(lib, session.entries[0]).title, "Correct the cause");
  step(session);
  step(session);
  assert.equal(reportVerification(lib, session, "3", "control was the cause"), "rerun");
  assert.equal(session.entries[0].k, 3);
  assert.equal(currentSopStep(lib, session.entries[0]).title, "Correct the cause");
});

test("constraints count only with the user's words", () => {
  const request = "Redesign the sources tab but keep our existing typography as it is";
  const ok = newSession(request, "g", [{ situation: "redesign", scope: "section", goal: "g" }], "", [{ constraint: "Keep the type", quote: "keep our existing typography" }]);
  assert.equal(ok.constraints[0].id, "C1");
  assert.throws(
    () => newSession(request, "g", [{ situation: "redesign", scope: "section", goal: "g" }], "", [{ constraint: "Keep it", quote: "existing identity retained" }]),
    /no quote from the request/,
  );
});

test("verification ends ready, and only the user's verdict finishes or returns it", async () => {
  const session = newSession("heading wraps", "fits", [{ situation: "fix", scope: "element", goal: "g" }]);
  submitPlan(lib, session, sopSteps(lib, session.entries[0]).map((s) => `plan ${s.number}`));
  step(session);
  step(session);
  step(session, 5);
  step(session);
  step(session);
  assert.throws(() => reportVerification(lib, session, "ready"), /Capture the result first/);
  addCapture(session, "before", "before", manifest("http://x"), "agent");
  addCapture(session, "result", "after", manifest("http://x"), "agent");
  assert.equal(reportVerification(lib, session, "done"), "ready");
  assert.throws(() => reportVerification(lib, session, "ready"), /ready for the user's review/);

  const store = new Store(new MemoryKeyValue());
  await store.save(session);
  const listed = await (await handleReview(new Request("https://x.test/review/t"), store, lib)).text();
  assert.match(listed, /Work ready for your review/);
  assert.ok(listed.includes(session.id));
  const form = new URLSearchParams({ session_id: session.id, verdict: "return", step: "3", reason: "still wraps at 390" });
  const after = await (await handleReview(new Request("https://x.test/review/t", { method: "POST", body: form }), store, lib)).text();
  assert.match(after, /Sent .* back to step 3/);
  const returned = (await store.load(session.id))!;
  assert.equal(returned.entries[0].awaiting_user, false);
  assert.equal(returned.entries[0].verifications.at(-1)!.findings, "still wraps at 390");
  assert.throws(() => recordVerdict(lib, returned, "done"), /no work waiting/);
});

test("escalate goes to the parent only, and a review doesn't turn into a fix", () => {
  const review = newSession("r", "g", [{ situation: "review", scope: "page", goal: "g" }]);
  assert.throws(() => escalate(review, "found problems", null, "fix"), /user's authorization/);
  const session = newSession("r", "g", [{ situation: "redesign", scope: "section", goal: "g" }]);
  assert.throws(() => escalate(session, "wrong", "element"), /parent of section is: page/);
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
  for (const name of ["get_matrix", "start_session", "submit_plan", "complete_step", "report_verification", "escalate", "get_process_step", "capture"]) {
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

  const r = (statement: string, based_on: string[]) => [{ statement, based_on }];
  assert.match(await call("complete_step", { session_id: sid, handoff: "early", results: r("x", ["request"]) }), /^Not done: Write the plan first/);
  const plan = ["state", "reproduce", "trace", "correct", "carry", "verify"];
  const first = await call("submit_plan", { session_id: sid, plan });
  assert.match(first, /# Fix step 1 of 6: State the problem/);
  assert.match(first, /The user's words: The claims section shouldn't exist/);
  await call("complete_step", { session_id: sid, handoff: "stated", results: r("claims duplicate ingredients", ["request"]) });
  const trace = await call("complete_step", { session_id: sid, handoff: "reproduced", results: r("shows at every width", ["1.1"]) });
  assert.match(trace, /Trace the cause \(trace\)/);
  assert.match(trace, /- 2\.1: shows at every width \(based on 1\.1\)/);
  const correct = await call("complete_step", { session_id: sid, handoff: "cause in step 2", results: r("step 2 kept it", ["2.1"]), responsible_step: 2 });
  assert.match(correct, /Fix step 4 of 6: Correct the cause/);
  assert.match(correct, /## Procedure step 2: Order the information \(verbatim\)/);
  assert.match(correct, /should exist at all/);
  const command = await call("capture", { session_id: sid, kind: "before", url: "http://localhost:5173/food", selector: "#s" });
  assert.match(command, /curl -fsSL https:\/\/<this-site>\/capture\.mjs/);
  assert.match(command, /--selector '#s' 'http:\/\/localhost:5173\/food'/);
  assert.match(
    await call("capture", { session_id: sid, kind: "before", url: "http://localhost:5173/food", manifest: JSON.stringify(manifest("http://localhost:5173/food")) }),
    /Recorded before 'before'.*taken by the agent/,
  );
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
