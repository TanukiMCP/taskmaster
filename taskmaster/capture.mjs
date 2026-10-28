#!/usr/bin/env node
// Taskmaster's capture script. Renders one page at 1440, 820 and 390 pixels wide, saves a
// full-page screenshot at each width (and the element's own screenshot when a selector is
// given), and prints a JSON manifest with page heights, sideways overflow and file hashes.
//
//   node capture.mjs --out <folder> --name <file-prefix> [--selector <css>] <url>
//
// Needs Playwright and its Chromium (npm i playwright && npx playwright install chromium).
// TASKMASTER_CHROMIUM points at a different Chromium binary.

import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const WIDTHS = [1440, 820, 390];

function parseArgs(argv) {
  const args = { url: "" };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") args.out = argv[++i];
    else if (a === "--name") args.name = argv[++i];
    else if (a === "--selector") args.selector = argv[++i];
    else args.url = a;
  }
  if (!args.url || !args.out || !args.name) throw new Error("Usage: node capture.mjs --out <folder> --name <file-prefix> [--selector <css>] <url>");
  return args;
}

async function loadPlaywright() {
  const attempts = [() => import("playwright"), () => createRequire(join(process.cwd(), "x.js"))("playwright"), () => createRequire(import.meta.url)("playwright")];
  for (const attempt of attempts) {
    try {
      return await attempt();
    } catch {}
  }
  throw new Error("Playwright isn't installed here. Run `npm i playwright && npx playwright install chromium`.");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { chromium } = await loadPlaywright();
  const executablePath = process.env.TASKMASTER_CHROMIUM;
  if (executablePath && !existsSync(executablePath)) throw new Error(`TASKMASTER_CHROMIUM points at ${executablePath}, which doesn't exist.`);
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const out = resolve(args.out);
  await mkdir(out, { recursive: true });
  const manifest = { url: args.url, selector: args.selector ?? null, taken_at: new Date().toISOString(), widths: [] };
  const save = async (file, bytes) => {
    await writeFile(join(out, file), bytes);
    return { file: join(out, file), sha256: createHash("sha256").update(bytes).digest("hex") };
  };
  try {
    for (const width of WIDTHS) {
      const entry = { width, ok: false };
      const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
      const page = await context.newPage();
      try {
        const response = await page.goto(args.url, { waitUntil: "load", timeout: 45000 });
        if (response && response.status() >= 400) throw new Error(`the page answered ${response.status()}`);
        await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
        if (args.selector) {
          const found = await page.waitForSelector(args.selector, { state: "visible", timeout: 10000 }).catch(() => null);
          if (!found) throw new Error(`nothing visible matches ${args.selector}`);
        }
        await page.waitForTimeout(400);
        const size = await page.evaluate((selector) => {
          const doc = document.documentElement;
          const el = selector ? document.querySelector(selector) : null;
          return {
            page_height: doc.scrollHeight,
            overflow: doc.scrollWidth > doc.clientWidth + 1,
            element_height: el ? Math.round(el.getBoundingClientRect().height) : null,
          };
        }, args.selector ?? null);
        Object.assign(entry, size);
        entry.page = await save(`${args.name}-${width}.jpg`, await page.screenshot({ fullPage: true, type: "jpeg", quality: 75 }));
        if (args.selector) entry.element = await save(`${args.name}-${width}-element.jpg`, await page.locator(args.selector).first().screenshot({ type: "jpeg", quality: 85 }));
        entry.ok = true;
      } catch (error) {
        entry.error = String(error?.message ?? error).split("\n")[0];
      } finally {
        await context.close();
      }
      manifest.widths.push(entry);
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(manifest));
}

main().catch((error) => {
  process.stderr.write(`${error?.message ?? error}\n`);
  process.exit(1);
});
