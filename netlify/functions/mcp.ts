// Netlify Function serving Taskmaster over stateless streamable HTTP at /mcp/<token>.
// The token is a secret path segment set in the TASKMASTER_TOKEN environment variable.

import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import type { Config, Context } from "@netlify/functions";

import { DESIGN } from "../lib/design-data.ts";
import { loadLibrary } from "../lib/library.ts";
import { blobs, sameToken } from "../lib/netlify.ts";
import { createServer } from "../lib/server.ts";
import { Store } from "../lib/store.ts";

const library = loadLibrary(DESIGN);

export default async (request: Request, context: Context): Promise<Response> => {
  const expected = Netlify.env.get("TASKMASTER_TOKEN");
  if (!expected) return new Response("Taskmaster is not configured: set TASKMASTER_TOKEN.", { status: 503 });
  if (!sameToken(context.params.token ?? "", expected)) return new Response("Not found", { status: 404 });

  const server = createServer(library, new Store(blobs()), { origin: new URL(request.url).origin });
  const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
  await server.connect(transport);
  return transport.handleRequest(request);
};

export const config: Config = {
  path: "/mcp/:token",
};
