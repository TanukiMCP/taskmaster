// Netlify-only helpers shared by the functions: the Blobs store and token comparison.

import { getStore } from "@netlify/blobs";

import type { KeyValue } from "./store.ts";

export function blobs(): KeyValue {
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

export function sameToken(given: string, expected: string): boolean {
  if (given.length !== expected.length) return false;
  let diff = 0;
  for (let i = 0; i < given.length; i++) diff |= given.charCodeAt(i) ^ expected.charCodeAt(i);
  return diff === 0;
}
