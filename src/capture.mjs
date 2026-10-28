#!/usr/bin/env node
// Taskmaster capture runner. Renders each page Taskmaster asks for at 1440, 820 and 390
// pixels wide, takes the screenshots, and collects the measurements the checks use.
//
//   node capture.mjs <job-url>               fetch a job from a Taskmaster server and upload the results
//   node capture.mjs --job job.json --out d  run a job from a file and write the results into a folder
//
// Needs Playwright (npm i playwright) and its Chromium. TASKMASTER_CHROMIUM points at another Chromium binary.

import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const PROPS = [
  "font-family",
  "font-size",
  "font-weight",
  "line-height",
  "letter-spacing",
  "color",
  "background-color",
  "border-top-width",
  "border-top-color",
  "border-top-left-radius",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "margin-top",
  "margin-right",
  "margin-bottom",
  "margin-left",
  "row-gap",
  "column-gap",
];

async function loadPlaywright() {
  const tries = [() => import("playwright"), () => createRequire(join(process.cwd(), "noop.js"))("playwright"), () => createRequire(import.meta.url)("playwright")];
  for (const attempt of tries) {
    try {
      return await attempt();
    } catch {}
  }
  throw new Error("Playwright isn't installed. Run `npm i playwright && npx playwright install chromium`, then run this again.");
}

async function launch(chromium) {
  const executablePath = process.env.TASKMASTER_CHROMIUM;
  if (executablePath && !existsSync(executablePath)) throw new Error(`TASKMASTER_CHROMIUM points at ${executablePath}, which doesn't exist.`);
  return chromium.launch(executablePath ? { executablePath } : {});
}

// Runs inside the page. Collects every visible element under the selector with the
// build line and part it belongs to, its box, its own text, and its computed styles.
function measurePage({ selector, props, declared, collect }) {
  const root = selector ? document.querySelector(selector) : document.body;
  const doc = document.documentElement;
  const base = { scroll_width: doc.scrollWidth, client_width: doc.clientWidth, page_height: doc.scrollHeight };
  if (!root) return { ...base, found: false };
  const sx = window.scrollX;
  const sy = window.scrollY;
  const box = (r) => ({ x: Math.round(r.left + sx), y: Math.round(r.top + sy), w: Math.round(r.width), h: Math.round(r.height) });
  const read = (el) => {
    const cs = getComputedStyle(el);
    const out = {};
    for (const p of props) out[p] = cs.getPropertyValue(p);
    return out;
  };
  const result = { ...base, found: true, root: box(root.getBoundingClientRect()) };
  if (collect === "values") {
    const values = {};
    for (const el of [root, ...root.querySelectorAll("*")]) {
      const s = read(el);
      for (const p of props) (values[p] ??= new Set()).add(s[p]);
    }
    result.values = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, [...v]]));
    return result;
  }
  if (collect === "box") return result;

  const styleIndex = new Map();
  const styles = [];
  const styleOf = (el) => {
    const s = read(el);
    const key = JSON.stringify(s);
    if (!styleIndex.has(key)) {
      styleIndex.set(key, styles.length);
      styles.push(s);
    }
    return styleIndex.get(key);
  };
  const index = new Map();
  const elements = [];
  const all = [root, ...root.querySelectorAll("*")];
  for (const el of all) {
    if (elements.length >= 5000) break;
    const tag = el.tagName.toLowerCase();
    if (["script", "style", "template", "noscript", "head", "meta", "link"].includes(tag)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const own = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();
    const tmEl = el.closest("[data-tm]");
    const partEl = el.closest("[data-tm-part]");
    const leaf = el.children.length === 0;
    const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2 || 1;
    let parent = el.parentElement;
    while (parent && !index.has(parent) && parent !== root.parentElement) parent = parent.parentElement;
    index.set(el, elements.length);
    elements.push({
      tm: tmEl && root.contains(tmEl) ? tmEl.getAttribute("data-tm") : null,
      part: partEl && root.contains(partEl) ? partEl.getAttribute("data-tm-part") : null,
      tag,
      text: own.slice(0, 160),
      text_len: own.length,
      ...box(r),
      lines: own && leaf ? Math.max(1, Math.round(r.height / lh)) : 0,
      s: styleOf(el),
      pi: parent && index.has(parent) ? index.get(parent) : -1,
      tm_root: el.hasAttribute("data-tm"),
      part_root: el.hasAttribute("data-tm-part"),
    });
  }
  result.context = root.parentElement ? read(root.parentElement) : {};
  result.styles = styles;
  result.elements = elements;

  // Resolve each build line's declared values in place, so var(), rem and colour names
  // compare with what the browser computes.
  if (declared) {
    const resolved = {};
    const probe = document.createElement("div");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    root.appendChild(probe);
    const baseline = read(probe);
    for (const [line, values] of Object.entries(declared)) {
      const sets = {};
      for (const [prop, list] of Object.entries(values)) {
        for (const value of Array.isArray(list) ? list : [list]) {
          probe.removeAttribute("style");
          probe.style.position = "absolute";
          probe.style.visibility = "hidden";
          probe.style.setProperty(prop, value);
          const after = read(probe);
          for (const p of props) if (p === prop || after[p] !== baseline[p]) (sets[p] ??= new Set()).add(after[p]);
        }
      }
      resolved[line] = Object.fromEntries(Object.entries(sets).map(([k, v]) => [k, [...v]]));
    }
    probe.remove();
    result.declared = resolved;
  }
  return result;
}

async function runJob(job, sink) {
  const { chromium } = await loadPlaywright();
  const browser = await launch(chromium);
  try {
    for (const target of job.targets) {
      for (const width of job.widths) {
        const name = `${target.key}-${width}`;
        const result = { key: target.key, width, ok: false };
        const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
        const page = await context.newPage();
        try {
          const response = await page.goto(target.url, { waitUntil: "load", timeout: 45000 });
          if (response && response.status() >= 400) throw new Error(`the page answered ${response.status()}`);
          await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
          if (target.selector) {
            await page.waitForSelector(target.selector, { state: "visible", timeout: 10000 }).catch(() => {
              throw new Error(`nothing matches the selector ${target.selector}`);
            });
          }
          await page.waitForTimeout(400);
          const collect = target.kind === "source" ? "values" : target.kind === "reference" ? "box" : "elements";
          const measure = await page.evaluate(measurePage, { selector: target.selector, props: PROPS, declared: target.declared, collect });
          if (!measure.found) throw new Error(`nothing matches the selector ${target.selector}`);
          result.page_height = measure.page_height;
          result.element_height = measure.root.h;
          if (target.kind !== "source") {
            result.image = `${name}.jpg`;
            await sink.image(result.image, await page.screenshot({ fullPage: true, type: "jpeg", quality: 70 }));
            if (target.selector) {
              result.element_image = `${name}-el.jpg`;
              await sink.image(result.element_image, await page.locator(target.selector).first().screenshot({ type: "jpeg", quality: 80 }));
            }
          }
          result.measure = measure;
          result.ok = true;
        } catch (error) {
          result.error = String(error?.message ?? error).split("\n")[0];
        } finally {
          await context.close();
        }
        await sink.result(result);
        process.stderr.write(`${result.ok ? "captured" : "failed  "} ${target.kind} ${target.url} ${target.selector ?? ""} at ${width}${result.error ? ": " + result.error : ""}\n`);
      }
    }
  } finally {
    await browser.close();
  }
  await sink.done();
}

async function main() {
  const args = process.argv.slice(2);
  if (args[0] === "--job") {
    const job = JSON.parse(await readFile(args[1], "utf8"));
    const out = args[args.indexOf("--out") + 1];
    await mkdir(out, { recursive: true });
    const results = [];
    await runJob(job, {
      image: (name, bytes) => writeFile(join(out, name), bytes),
      result: async (r) => results.push(r),
      done: () => writeFile(join(out, "results.json"), JSON.stringify(results)),
    });
    return;
  }
  const jobUrl = args[0];
  if (!jobUrl) throw new Error("Usage: node capture.mjs <job-url>");
  const response = await fetch(jobUrl);
  if (!response.ok) throw new Error(`Taskmaster answered ${response.status}: ${await response.text()}`);
  const job = await response.json();
  const send = async (path, init) => {
    const r = await fetch(`${jobUrl}/${path}`, init);
    if (!r.ok) throw new Error(`Upload failed (${r.status}): ${await r.text()}`);
  };
  await runJob(job, {
    image: (name, bytes) => send(`image/${encodeURIComponent(name)}`, { method: "PUT", headers: { "content-type": "image/jpeg" }, body: bytes }),
    result: (r) => send("result", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(r) }),
    done: () => send("done", { method: "POST" }),
  });
  process.stderr.write("Done. Call submit_step again to continue.\n");
}

main().catch((error) => {
  process.stderr.write(`${error?.message ?? error}\n`);
  process.exit(1);
});
