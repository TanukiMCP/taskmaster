// Netlify Function serving the user's review page at /review/<token>, where the token is
// TASKMASTER_REVIEW_TOKEN. Agents connect through /mcp/<token> and are never given this one.

import type { Config, Context } from "@netlify/functions";

import { DESIGN } from "../lib/design-data.ts";
import { loadLibrary } from "../lib/library.ts";
import { blobs, sameToken } from "../lib/netlify.ts";
import { handleReview } from "../lib/review.ts";
import { Store } from "../lib/store.ts";

const library = loadLibrary(DESIGN);

export default async (request: Request, context: Context): Promise<Response> => {
  const expected = Netlify.env.get("TASKMASTER_REVIEW_TOKEN");
  if (!expected) return new Response("The review page is not configured: set TASKMASTER_REVIEW_TOKEN.", { status: 503 });
  if (expected === Netlify.env.get("TASKMASTER_TOKEN")) return new Response("TASKMASTER_REVIEW_TOKEN must differ from TASKMASTER_TOKEN.", { status: 503 });
  if (!sameToken(context.params.token ?? "", expected)) return new Response("Not found", { status: 404 });
  return handleReview(request, new Store(blobs()), library);
};

export const config: Config = {
  path: "/review/:token",
};
