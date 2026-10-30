import assert from "node:assert/strict";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";

import { compose, finish, newSession, ready, record, revise, states, type OperationInput } from "../lib/engine.ts";
import { LIBRARY } from "../lib/library-data.ts";
import { SCOPES, SITUATIONS, composition, loadLibrary, readLibrary, type ScopeKey, type SituationKey } from "../lib/library.ts";
import { createServer } from "../lib/server.ts";
import { MemoryKeyValue, Store } from "../lib/store.ts";

const lib = loadLibrary(LIBRARY);
const textOf = (result: any) => result.content.map((c: any) => c.text).join("\n");
const op = (id: string, needs: string[] = []): OperationInput => ({ id, needs, does: "work", produces: "output" });

function game() {
  const session = newSession("Make a game concept", "One playable concept", "Players feel clever, not lucky");
  compose(session, [op("brief"), op("fantasy", ["brief"]), op("audience", ["brief"]), op("loop", ["fantasy"]), op("pitch", ["loop", "audience"])]);
  return session;
}
const done = (session: ReturnType<typeof game>, id: string, output = "out") => record(session, id, { output, preserves: "keeps the cleverness" });
function runAll(session: ReturnType<typeof game>) {
  while (ready(session).length) done(session, ready(session)[0].id);
}

test("library parses the method and every situation as a composition", () => {
  assert.match(lib.method, /^Dependency-ordered cognitive composition/);
  assert.equal(lib.procedure.steps.size, 11);
  assert.match(lib.procedure.workingRules, /Before each operation/);
  for (const sop of Object.values(lib.situations)) {
    assert.ok(sop.brief && sop.mayChange && sop.mustPreserve && sop.completion);
    assert.ok(sop.steps.every((s) => s.id && s.produces && s.instruction));
  }
  assert.deepEqual(lib.situations.review.steps.find((s) => s.id === "record")!.needs, ["question"]);
  assert.match(readLibrary(lib, "design/create/page#order")!, /### Procedure step 2: Order the information \(verbatim\)/);
  assert.match(readLibrary(lib, "design/fix/element#correct")!, /Works in procedure step: the step the trace named/);
  assert.equal(readLibrary(lib, "design/fix/page#nope"), null);
});

test("an operation waits for current inputs, and revision stales only what was built on it", () => {
  const session = game();
  assert.throws(() => done(session, "fantasy"), /it needs 'brief', which is not current\. Work on 'brief' first/);
  assert.throws(() => record(session, "brief", { output: "o" }), /still serves the value/);
  runAll(session);
  assert.deepEqual(revise(session, "playtest: reads as luck", "fantasy"), ["loop", "pitch"]);
  assert.deepEqual(states(session), { brief: "current", fantasy: "open", audience: "current", loop: "stale", pitch: "stale" });
  done(session, "fantasy", "a sharper fantasy");
  assert.equal(record(session, "loop", { still_holds: "the loop never depended on it" }), "confirmed");
  assert.ok(Object.values(states(session)).every((s) => s === "current"));
  assert.deepEqual(revise(session, "co-op now", "", "Friends feel clever together"), ["brief", "fantasy", "audience", "loop", "pitch"]);
});

test("recompose keeps, reopens, and retires; finish names what is unfinished", () => {
  const session = game();
  runAll(session);
  assert.throws(() => compose(session, [{ id: "brief" }]), /Say why/);
  const [reopened] = compose(
    session,
    [{ id: "brief" }, { ...op("fantasy", ["brief"]), does: "reworded" }, { ...op("loop", ["fantasy"]), produces: "a loop with a fail state" }, op("pitch", ["loop"])],
    "audience is out of scope",
  );
  assert.deepEqual(reopened, ["loop", "pitch"]);
  assert.deepEqual(session.retired.map((o) => o.id), ["audience"]);
  assert.throws(() => finish(session, "doc", "read it"), /'loop', 'pitch' are not current/);
  assert.deepEqual(finish(session, "doc", "read it", "stopped early"), ["loop", "pitch"]);
});

test("every design composition runs to the end", () => {
  for (const situation of Object.keys(SITUATIONS) as SituationKey[]) {
    for (const scope of Object.keys(SCOPES) as ScopeKey[]) {
      const session = newSession("design", "the work", "people can do what they came for");
      const [, warnings] = compose(session, composition(lib, situation, scope).map((o) => ({ ...o, does: `do ${o.id}` })));
      assert.deepEqual(warnings, []);
      runAll(session);
      assert.ok(Object.values(states(session)).every((s) => s === "current"), `${situation} × ${scope}`);
    }
  }
});

test("full flow through an MCP client", async () => {
  const kv = new MemoryKeyValue();
  const server = createServer(lib, new Store(kv));
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  const client = new Client({ name: "test", version: "1" });
  await client.connect(clientSide);
  const call = async (name: string, args: Record<string, unknown>) => textOf(await client.callTool({ name, arguments: args }));

  const tools = (await client.listTools()).tools.map((t) => t.name).sort();
  assert.deepEqual(tools, ["compose", "finish", "library", "next", "record", "revise", "start"]);
  assert.match(await call("library", { ref: "design" }), /Prompt selector/);

  const started = await call("start", {
    request: "The claims section shouldn't exist",
    result: "Claims beside their ingredients",
    value: "Shoppers judge each ingredient with its evidence in one place",
  });
  assert.match(started, /Dependency-ordered cognitive composition/);
  const sid = /Session (\w+) started/.exec(started)![1];

  const entry = await call("library", { ref: "design/fix/page" });
  const operations = JSON.parse(entry.slice(entry.indexOf("[\n"))).map((o: any) => ({ ...o, does: `${o.id} for the claims section` }));
  const composed = await call("compose", { session_id: sid, operations: JSON.stringify(operations) });
  assert.match(composed, /Composition recorded: 6 operations\./);
  assert.match(composed, /# Next: problem \(open\)/);

  assert.match(await call("record", { session_id: sid, operation: "trace", output: "early", preserves: "p" }), /^Not done: 'trace' can't be recorded yet/);
  await call("record", { session_id: sid, operation: "problem", output: "Claims sit apart.", preserves: "p" });
  const trace = await call("record", { session_id: sid, operation: "reproduce", output: "Captured.", preserves: "p", assumptions: ["band not reused"] });
  assert.match(trace, /### problem \(v1\)\nClaims sit apart\./);
  assert.match(trace, /Assumptions: band not reused/);
  for (const id of ["trace", "correct", "carry", "verify"]) await call("record", { session_id: sid, operation: id, output: `${id} done`, preserves: "p" });

  const revised = await call("revise", { session_id: sid, operation: "reproduce", reason: "the band is reused" });
  assert.match(revised, /Reopened 'reproduce'\. Now stale: trace, correct, carry, verify\./);
  await call("record", { session_id: sid, operation: "reproduce", output: "Captured on both pages.", preserves: "p" });
  assert.match(await call("next", { session_id: sid }), /'reproduce' changed \(v1 → v2\)/);
  assert.match(await call("record", { session_id: sid, operation: "trace", still_holds: "same cause" }), /^Confirmed 'trace' v1 still holds\./);
  await call("record", { session_id: sid, operation: "verify", output: "checked", preserves: "p" });
  assert.match(await call("finish", { session_id: sid, delivered: "the page", evidence: "walked it" }), /is finished/);

  assert.ok((await call("next", {})).includes(sid));
  assert.match(await call("next", { session_id: "nope" }), /^Not done: No session/);
  await kv.set("sessions/old", JSON.stringify({ id: "old", request: "r", end_goal: "g", entries: [] }));
  assert.match(await call("next", { session_id: "old" }), /earlier version of Taskmaster/);
  assert.ok((await client.listPrompts()).prompts.some((p) => p.name === "run"));
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
