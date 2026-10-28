// Step 6's trace and step 7's checks, computed from what the capture runner measured.
// Pure: no judgement of quality, only whether the page matches the document.

import { WIDTHS, type BuildLine, type Doc } from "./document.ts";

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}
export interface ElementM extends Rect {
  tm: string | null;
  part: string | null;
  tag: string;
  text: string;
  text_len: number;
  lines: number;
  s: number;
  pi: number;
  tm_root: boolean;
  part_root: boolean;
}
export interface ElementsMeasure {
  found: boolean;
  scroll_width: number;
  client_width: number;
  page_height: number;
  root: Rect;
  context: Record<string, string>;
  styles: Record<string, string>[];
  elements: ElementM[];
  declared?: Record<string, Record<string, string[]>>;
}
export interface ValuesMeasure {
  found: boolean;
  values: Record<string, string[]>;
}

export interface EvalInput {
  doc: Doc;
  // One entry per state of the built view, default first.
  built: { state: string; widths: Record<number, ElementsMeasure | undefined> }[];
  // Measured values of the accepted component each "from accepted" build line names.
  sources: Record<string, Record<number, ValuesMeasure | undefined>>;
  // Accepted views at each width: their height sets the limit, their left edges are compared.
  views: { id: string; name: string; widths: Record<number, { height: number; measure?: ElementsMeasure } | undefined> }[];
}

export interface WidthSummary {
  height: number;
  limit: number | null;
  limit_from: string;
  page_height: number;
  parts: { id: string; planned: number; actual: number }[];
  left_edges: number;
  view_left_edges: { name: string; count: number }[];
  largest_gap: number;
}

export interface Evaluation {
  trace: string[];
  failures: string[];
  notes: string[];
  widths: Record<number, WidthSummary>;
}

const ALWAYS = new Set(["0px", "normal", "auto", "none", "rgba(0, 0, 0, 0)", "transparent", "0", "medium", "initial"]);
const INHERITED = new Set(["font-family", "font-size", "font-weight", "line-height", "letter-spacing", "color"]);

type Sets = Map<string, Set<string>>;

function addAll(target: Sets, values: Record<string, string[]> | undefined) {
  for (const [prop, list] of Object.entries(values ?? {})) {
    if (!target.has(prop)) target.set(prop, new Set());
    for (const v of list) target.get(prop)!.add(v);
  }
}

function allowedFor(line: BuildLine, input: EvalInput, m: ElementsMeasure): Sets {
  const sets: Sets = new Map();
  if (line.from === "accepted") for (const w of WIDTHS) addAll(sets, input.sources[line.id]?.[w]?.values);
  else addAll(sets, m.declared?.[line.id]);
  return sets;
}

const describe = (e: ElementM) => `<${e.tag}${e.text ? ` "${e.text.slice(0, 40)}"` : ""}>`;

function traceWidth(input: EvalInput, state: string, width: number, m: ElementsMeasure, lines: Map<string, BuildLine>, seen: Map<string, string>) {
  const allowed = new Map<string, Sets>();
  const frame: Sets = new Map();
  for (const line of lines.values()) {
    const sets = allowedFor(line, input, m);
    allowed.set(line.id, sets);
    for (const [prop, values] of sets) addAll(frame, { [prop]: [...values] });
  }
  const note = (key: string, text: string) => {
    if (!seen.has(key)) seen.set(key, `${text} (${state}, ${width})`);
  };
  for (const e of m.elements) {
    const styles = m.styles[e.s] ?? {};
    let sets: Sets;
    let parentStyles: Record<string, string> = m.context;
    if (e.tm === null) {
      if (e.text_len > 0) note(`text|${e.text}`, `Text ${describe(e)} sits under no build line`);
      sets = frame;
    } else if (!lines.has(e.tm)) {
      note(`tm|${e.tm}`, `data-tm="${e.tm}" is not a build line`);
      continue;
    } else {
      sets = allowed.get(e.tm)!;
      let at: ElementM | undefined = e;
      while (at && !(at.tm_root && at.tm === e.tm)) at = at.pi >= 0 ? m.elements[at.pi] : undefined;
      const parent = at && at.pi >= 0 ? m.elements[at.pi] : undefined;
      parentStyles = parent ? (m.styles[parent.s] ?? m.context) : m.context;
    }
    for (const [prop, value] of Object.entries(styles)) {
      if (ALWAYS.has(value) || value === m.context[prop] || sets.get(prop)?.has(value)) continue;
      if (INHERITED.has(prop) && value === parentStyles[prop]) continue;
      if (prop === "border-top-color" && styles["border-top-width"] === "0px") continue;
      if ((prop === "margin-left" || prop === "margin-right") && styles["margin-left"] === styles["margin-right"]) continue;
      const owner = e.tm ?? "no build line";
      note(`${owner}|${prop}|${value}`, `${prop} ${value} on ${describe(e)} traces to ${e.tm ? `nothing in ${e.tm}` : "no build line"}`);
    }
  }
}

function partBounds(m: ElementsMeasure) {
  const bounds = new Map<string, { top: number; bottom: number; left: number }>();
  for (const e of m.elements) {
    if (!e.part_root || !e.part) continue;
    const b = bounds.get(e.part) ?? { top: Infinity, bottom: -Infinity, left: Infinity };
    b.top = Math.min(b.top, e.y);
    b.bottom = Math.max(b.bottom, e.y + e.h);
    b.left = Math.min(b.left, e.x);
    bounds.set(e.part, b);
  }
  return bounds;
}

function leftEdges(m: ElementsMeasure | undefined): number {
  if (!m?.elements) return 0;
  return new Set(m.elements.filter((e) => e.text_len > 0).map((e) => Math.round(e.x / 2))).size;
}

function largestGap(m: ElementsMeasure): number {
  const spans = m.elements
    .filter((e) => (e.text_len > 0 || e.tag === "img" || e.tag === "svg") && e.h > 0)
    .map((e) => [e.y, e.y + e.h] as [number, number])
    .sort((a, b) => a[0] - b[0]);
  let gap = 0;
  let end = m.root.y;
  for (const [top, bottom] of spans) {
    if (top > end) gap = Math.max(gap, top - end);
    end = Math.max(end, bottom);
  }
  return gap;
}

export function evaluate(input: EvalInput): Evaluation {
  const doc = input.doc;
  const lines = new Map((doc[5]?.build ?? []).map((b) => [b.id, b]));
  const parts = doc[3]?.parts ?? [];
  const pieces = new Map((doc[4]?.references ?? []).flatMap((r) => r.part_list.map((p) => [p.id, p.name] as const)));
  const trace = new Map<string, string>();
  const failures: string[] = [];
  const notes: string[] = [];
  const widths: Record<number, WidthSummary> = {};

  for (const view of input.built) {
    for (const w of WIDTHS) {
      const m = view.widths[w];
      if (!m?.found) {
        failures.push(`The ${view.state} state didn't render at ${w}.`);
        continue;
      }
      traceWidth(input, view.state, w, m, lines, trace);
      if (m.scroll_width > m.client_width + 1) failures.push(`The page scrolls sideways at ${w} in the ${view.state} state (${m.scroll_width}px wide in ${m.client_width}px).`);
    }
  }

  const main = input.built[0];
  const shareTotal = parts.reduce((sum, s) => sum + s.share, 0) || 1;
  for (const w of WIDTHS) {
    const m = main?.widths[w];
    if (!m?.found) continue;
    const override = doc[3]?.height_limits.find((h) => h.width === w);
    const viewHeights = input.views.map((v) => ({ name: v.name, h: v.widths[w]?.height ?? 0 })).filter((v) => v.h > 0);
    const tallest = viewHeights.sort((a, b) => b.h - a.h)[0];
    const limit = override ? override.px : tallest ? tallest.h : null;
    const limitFrom = override ? "your height limit" : tallest ? tallest.name : "nothing";
    if (limit === null) failures.push(`There is no height limit at ${w}.`);
    else if (m.root.h > limit + 1) failures.push(`At ${w} the view is ${m.root.h}px tall; the limit is ${limit}px (${limitFrom}).`);

    const bounds = partBounds(m);
    const present = parts.filter((s) => bounds.has(s.id));
    for (const s of parts) if (!bounds.has(s.id)) failures.push(`${s.id} (${s.name}) isn't on the page at ${w}; mark its outer element data-tm-part="${s.id}".`);
    const onPage = [...present].sort((a, b) => {
      const A = bounds.get(a.id)!;
      const B = bounds.get(b.id)!;
      return Math.round(A.top / 8) - Math.round(B.top / 8) || A.left - B.left;
    });
    if (onPage.map((s) => s.id).join() !== present.map((s) => s.id).join())
      failures.push(`At ${w} the parts read ${onPage.map((s) => s.id).join(", ")}; step 3's order is ${present.map((s) => s.id).join(", ")}.`);

    const heights = new Map(present.map((s) => [s.id, bounds.get(s.id)!.bottom - bounds.get(s.id)!.top]));
    const primary = parts.find((s) => s.primary);
    if (primary && heights.has(primary.id)) {
      const bigger = present.filter((s) => s.id !== primary.id && heights.get(s.id)! > heights.get(primary.id)!);
      if (bigger.length) failures.push(`At ${w} the primary part ${primary.id} (${heights.get(primary.id)}px) is smaller than ${bigger.map((s) => `${s.id} (${heights.get(s.id)}px)`).join(", ")}.`);
    }
    const heightTotal = [...heights.values()].reduce((a, b) => a + b, 0) || 1;
    const shares: WidthSummary["parts"] = [];
    for (const s of present) {
      const planned = s.share / shareTotal;
      const actual = heights.get(s.id)! / heightTotal;
      shares.push({ id: s.id, planned: Math.round(planned * 100), actual: Math.round(actual * 100) });
      if (actual < planned / 2 || actual > planned * 2)
        failures.push(`At ${w} ${s.id} takes ${Math.round(actual * 100)}% of the height; its share is ${Math.round(planned * 100)}%.`);
    }

    for (const line of lines.values()) {
      const shown = m.elements.some((e) => e.tm_root && e.tm === line.id && e.w > 0 && e.h > 0);
      if (!shown)
        failures.push(`${line.id} (${line.covers.map((c) => `${c} ${pieces.get(c) ?? ""}`.trim()).join(", ")}) isn't on the page at ${w}; mark its outer element data-tm="${line.id}".`);
    }
    for (const e of m.elements) {
      if (e.text_len <= 120) continue;
      const line = e.tm ? lines.get(e.tm) : undefined;
      if (!line || line.form !== "text") failures.push(`At ${w} ${describe(e)} is a ${e.text_len}-character paragraph inside ${line ? `${line.id}, a ${line.form} line` : "no build line"}.`);
    }

    widths[w] = {
      height: m.root.h,
      limit,
      limit_from: limitFrom,
      page_height: m.page_height,
      parts: shares,
      left_edges: leftEdges(m),
      view_left_edges: input.views.map((v) => ({ name: v.name, count: leftEdges(v.widths[w]?.measure) })),
      largest_gap: largestGap(m),
    };
  }

  const wide = main?.widths[1440];
  if (wide?.found) {
    const counts = new Map<string, number>();
    for (const e of wide.elements) {
      const t = e.text.trim();
      if (t.length >= 4 && !/^[\d\s.,%:/-]+$/.test(t)) counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    const repeats = [...counts].filter(([, n]) => n > 1).sort((a, b) => b[1] - a[1]);
    if (repeats.length) notes.push(`Repeated text: ${repeats.slice(0, 8).map(([t, n]) => `"${t.slice(0, 40)}" ×${n}`).join(", ")}.`);
  }
  for (const w of WIDTHS) {
    const m = main?.widths[w];
    if (!m?.found) continue;
    const wrapped = m.elements.filter((e) => e.text_len > 0 && e.text_len <= 30 && e.lines >= 2);
    if (wrapped.length) notes.push(`Wrapped labels at ${w}: ${wrapped.slice(0, 6).map((e) => `"${e.text}"`).join(", ")}.`);
    const s = widths[w];
    if (s) {
      const others = s.view_left_edges.map((v) => `${v.name} ${v.count}`).join(", ");
      notes.push(`At ${w}: ${s.height}px tall (limit ${s.limit ?? "none"}px), ${s.left_edges} left edges${others ? ` (${others})` : ""}, largest gap ${s.largest_gap}px.`);
    }
  }

  return { trace: [...trace.values()], failures, notes, widths };
}
