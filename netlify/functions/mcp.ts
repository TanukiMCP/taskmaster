// Netlify Function serving Taskmaster over stateless streamable HTTP at /mcp/<token>.
// The token is a secret path segment set in the TASKMASTER_TOKEN environment variable.

import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { getStore } from "@netlify/blobs";
import type { Config, Context } from "@netlify/functions";

import { DESIGN } from "../lib/design-data.ts";
import { loadLibrary } from "../lib/library.ts";
import { createServer } from "../lib/server.ts";
import { Store, type KeyValue } from "../lib/store.ts";

const library = loadLibrary(DESIGN);

function blobs(): KeyValue {
  const store = getStore({ name: "taskmaster", consistency: "strong" });
  return {
    get: (key) => store.get(key, { type: "text" }),
    set: async (key, value) => {
      await store.set(key, value);
    },
    delete: (key) => store.delete(key),
    keys: async (prefix) => (await store.list({ prefix })).blobs.map((b) => b.key),
  };
}

function sameToken(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < given.length; i++) diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}

export default async (request: Request, context: Context): Promise<Response> => {
  const expected = Netlify.env.get("TASKMASTER_TOKEN");
  if (!expected) return new Response("Taskmaster is not configured: set TASKMASTER_TOKEN.", { status: 503 });
  if (!sameToken(context.params.token ?? "", expected)) return new Response("Not found", { status: 404 });

  const server = createServer(library, new Store(blobs()));
  const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  await server.connect(transport);
  return transport.handleRequest(request);
};

export const config: Config = {
  path: "/mcp/:token",
};
