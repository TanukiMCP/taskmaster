import assert from "node:assert/strict";
import { test } from "node:test";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";

import { DESIGN } from "../lib/design-data.ts";
import { completeStep, newSession, reportVerification } from "../lib/engine.ts";
import { loadLibrary } from "../lib/library.ts";
import { createServer } from "../lib/server.ts";
import { MemoryKeyValue, Store } from "../lib/store.ts";

const lib = loadLibrary(DESIGN);

const textOf = (result: any) => result.content.map((c: any) => c.text).join("\n");

test("library parses every step, situation, and scope", () => {
  assert.equal(lib.procedure.steps.size, 11);
  assert.equal(lib.procedure.steps.get(3)!.name, "Inventory sections and select components");
  for (const scope of Object.values(lib.scopes)) assert.equal(scope.limits.size, 11);
  for (const key of ["create", "extend", "review"] as const) assert.equal(lib.situations[key].rules.size, 11);
});

test("engine diagnoses Improve first and reruns from the reported step", () => {
  const session = newSession("redesign", "goal", [{ situation: "improve", scope: "page", goal: "g" }]);
  completeStep(session, "question");
  assert.equal(session.entries[0].phase, "diagnosis");
  assert.equal(reportVerification(session, "3", "free text"), "rerun");
  assert.equal(session.entries[0].step, 3);
  while ((session.entries[0].step as number) !== 10) completeStep(session);
  assert.equal(reportVerification(session, "done"), "done");
  assert.equal(session.status, "complete");
});

test("full flow through an MCP client", async () => {
  const server = createServer(lib, new Store(new MemoryKeyValue()));
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  const client = new Client({ name: "test", version: "1" });
  await client.connect(clientSide);

  const tools = (await client.listTools()).tools.map((t) => t.name);
  for (const name of ["get_matrix", "start_session", "complete_step", "report_verification", "current_step"]) {
    assert.ok(tools.includes(name), name);
  }
  assert.match(textOf(await client.callTool({ name: "get_matrix", arguments: {} })), /Prompt selector/);

  const started = textOf(
    await client.callTool({
      name: "start_session",
      arguments: {
        request: "Use taskmaster to redesign the landing page",
        end_goal: "Visitors can tell what the product does",
        entries: [{ situation: "improve", scope: "page", goal: "Landing page answers the question" }],
      },
    }),
  );
  assert.match(started, /Working method/);
  assert.match(started, /# Step 0: State the question/);

  assert.match(textOf(await client.callTool({ name: "complete_step", arguments: { handoff: "Question stated." } })), /Diagnosis \(Improve\)/);
  const rerun = textOf(await client.callTool({ name: "report_verification", arguments: { outcome: "3", findings: "Hero is free text" } }));
  assert.match(rerun, /# Step 3: Inventory sections and select components/);
  assert.match(textOf(await client.callTool({ name: "get_status", arguments: {} })), /Hero is free text/);
  assert.match(textOf(await client.callTool({ name: "report_verification", arguments: { outcome: "done" } })), /^Not done:/);

  const prompts = (await client.listPrompts()).prompts.map((p) => p.name);
  assert.ok(prompts.includes("design"));
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
