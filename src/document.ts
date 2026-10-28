// The design document and the rules that refuse a step. Pure functions: they read
// the document, the user's words and the library, and return what is wrong.

export const WIDTHS = [1440, 820, 390] as const;
export const FORMS = ["rows", "table", "list", "text", "heading", "graphic", "control", "layout"] as const;
const TEXTLESS_FORMS = new Set(["graphic", "control", "layout"]);

export type Form = (typeof FORMS)[number];
export type Cost = "low" | "medium" | "high";
export type Ruling = "keep" | "move" | "drop" | "add";
export type Tier = "accepted" | "library" | "outside";

export interface Problem {
  id: string;
  need: string;
}
export interface Constraint {
  id: string;
  rule: string;
  quote: string;
}
export interface AcceptedView {
  id: string;
  name: string;
  url: string;
  selector?: string;
  quote?: string;
}
export interface Item {
  id: string;
  what: string;
  problems: string[];
  kind?: "field" | "action" | "content";
  existing: boolean;
  ruling: Ruling;
  where?: string;
  count?: number;
  total?: number;
  query?: string;
  cost: Cost;
  cost_reason: string;
}
export interface Part {
  id: string;
  name: string;
  items: string[];
  primary: boolean;
  share: number;
  reason: string;
  cites: string[];
}
export interface HeightLimit {
  width: number;
  px: number;
  reason: string;
  cites: string[];
}
export interface Piece {
  id: string;
  name: string;
  what: string;
}
export interface Reference {
  id: string;
  part: string;
  problems: string[];
  tier: Tier;
  source: string;
  url: string;
  selector?: string;
  view?: string;
  library_id?: string;
  why_not_inside?: string;
  part_list: Piece[];
}
export interface Stop {
  part: string;
  reason: string;
}
export interface BuildLine {
  id: string;
  part: string;
  covers: string[];
  from: "accepted" | "new";
  source?: string;
  selector?: string;
  form: Form;
  text?: string;
  values?: Record<string, string | string[]>;
  reason: string;
  cites: string[];
}
export interface BuiltView {
  state: string;
  url: string;
  selector: string;
}

export interface Step1 {
  problems: Problem[];
  constraints: Constraint[];
  accepted_views: AcceptedView[];
}
export interface Step2 {
  mode: "data" | "content";
  items: Item[];
}
export interface Step3 {
  parts: Part[];
  height_limits: HeightLimit[];
}
export interface Step4 {
  references: Reference[];
  stops: Stop[];
}
export interface Step5 {
  build: BuildLine[];
}
export interface Step6 {
  views: BuiltView[];
}

export interface Doc {
  1?: Step1;
  2?: Step2;
  3?: Step3;
  4?: Step4;
  5?: Step5;
  6?: Step6;
}

// What the library contributes to validation: views the user already accepted for
// this product, approved references, and rejected ones.
export interface LibraryView {
  id: string;
  name: string;
  url: string;
  selector?: string;
}
export interface LibraryEntry {
  id: string;
  source: string;
  url: string;
  selector?: string;
}
export interface LibraryContext {
  views: LibraryView[];
  approved: LibraryEntry[];
  rejected: { url: string; selector?: string; reason: string }[];
}

export interface CaptureState {
  ok: boolean;
  error?: string;
}

// ---------- helpers ----------

export class Refusal extends Error {
  problems: string[];
  constructor(problems: string[]) {
    super(problems.join("\n"));
    this.problems = problems;
  }
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown) => (typeof v === "string" ? v.trim() : "");
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strings = (v: unknown): string[] => list(v).map(str).filter(Boolean);

export function normalizeWords(text: string): string {
  return text
    .toLowerCase()
    .replace(/[‘’‛′`]/g, "'")
    .replace(/[“”″]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

export function quoteFound(quote: string, words: string): boolean {
  const q = normalizeWords(quote).replace(/^["'\s]+|["'\s.]+$/g, "");
  return q.split(" ").length >= 3 && normalizeWords(words).includes(q);
}

export function normalizeUrl(url: string): string {
  try {
    const u = new URL(url.trim());
    u.hash = "";
    let out = `${u.protocol}//${u.host.toLowerCase()}${u.pathname.replace(/\/+$/, "")}${u.search}`;
    if (out.endsWith("//")) out = out.slice(0, -1);
    return out;
  } catch {
    return url.trim();
  }
}

export const componentKey = (url: string, selector?: string) => `${normalizeUrl(url)}|${(selector ?? "").trim()}`;

const isUrl = (v: string) => /^https?:\/\/\S+$/i.test(v);
const COMPONENT_WORDS =
  /\b(cards?|tables?|charts?|graphs?|modals?|banners?|carousels?|accordions?|badges?|buttons?|hero|sidebars?|tiles?|widgets?|gauges?|timelines?|dropdowns?|sliders?|toggles?|components?)\b/i;

function ids<T extends { id: string }>(items: T[], pattern: RegExp, label: string, out: string[]): Set<string> {
  const seen = new Set<string>();
  for (const item of items) {
    if (!pattern.test(item.id)) out.push(`${label} ID "${item.id}" should look like ${pattern.source.replace(/[\^$\\]/g, "").replace("d+", "1")}.`);
    if (seen.has(item.id)) out.push(`${item.id} is used twice.`);
    seen.add(item.id);
  }
  return seen;
}

// Every ID a later step may point at.
export function knownIds(doc: Doc, lib: LibraryContext): Set<string> {
  const known = new Set<string>();
  for (const p of doc[1]?.problems ?? []) known.add(p.id);
  for (const c of doc[1]?.constraints ?? []) known.add(c.id);
  for (const v of doc[1]?.accepted_views ?? []) known.add(v.id);
  for (const v of lib.views) known.add(v.id);
  for (const i of doc[2]?.items ?? []) known.add(i.id);
  for (const s of doc[3]?.parts ?? []) known.add(s.id);
  for (const r of doc[4]?.references ?? []) {
    known.add(r.id);
    for (const piece of r.part_list) known.add(piece.id);
  }
  return known;
}

export function allViews(doc: Doc, lib: LibraryContext): LibraryView[] {
  return [...lib.views, ...(doc[1]?.accepted_views ?? [])];
}

// ---------- step 1 ----------

export function checkStep1(raw: unknown, request: string): Step1 {
  if (!isObject(raw)) throw new Refusal(["Step 1 takes an object with problems, constraints and accepted_views."]);
  const out: string[] = [];
  const problems: Problem[] = list(raw.problems).map((p) => ({ id: str((p as any)?.id), need: str((p as any)?.need) }));
  const constraints: Constraint[] = list(raw.constraints).map((c) => ({
    id: str((c as any)?.id),
    rule: str((c as any)?.rule),
    quote: str((c as any)?.quote),
  }));
  const views: AcceptedView[] = list(raw.accepted_views).map((v) => ({
    id: str((v as any)?.id),
    name: str((v as any)?.name),
    url: str((v as any)?.url),
    selector: str((v as any)?.selector) || undefined,
    quote: str((v as any)?.quote),
  }));

  if (!problems.length) out.push("There are no problems. Write what a reader needs from this view before anything else.");
  ids(problems, /^P\d+$/, "Problem", out);
  ids(constraints, /^C\d+$/, "Constraint", out);
  ids(views, /^V\d+$/, "Accepted view", out);
  for (const p of problems) {
    if (!p.need) out.push(`${p.id} has no need written.`);
    const word = p.need.match(COMPONENT_WORDS);
    if (word) out.push(`${p.id} names a component ("${word[0]}"). Write what the reader needs, not what to build.`);
  }
  for (const c of constraints) {
    if (!c.rule) out.push(`${c.id} has no rule written.`);
    if (!quoteFound(c.quote, request))
      out.push(`${c.id}'s quote is not in the user's words, or is shorter than three words. Without the user's words it is not a constraint; leave it open.`);
  }
  for (const v of views) {
    if (!v.name) out.push(`${v.id} has no name.`);
    if (!isUrl(v.url)) out.push(`${v.id} needs a full URL.`);
    if (!quoteFound(v.quote ?? "", request))
      out.push(`${v.id}'s quote is not in the user's words, or is shorter than three words. A view counts as accepted only when the user said so.`);
  }
  if (out.length) throw new Refusal(out);
  return { problems, constraints, accepted_views: views };
}

// ---------- step 2 ----------

export function checkStep2(raw: unknown, doc: Doc): Step2 {
  if (!isObject(raw)) throw new Refusal(["Step 2 takes an object with mode and items."]);
  const out: string[] = [];
  const mode = str(raw.mode);
  if (mode !== "data" && mode !== "content") out.push('mode is "data" when catalogue data is behind the view, otherwise "content".');
  const problemIds = new Set((doc[1]?.problems ?? []).map((p) => p.id));
  const items: Item[] = list(raw.items).map((r) => {
    const i = r as any;
    const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
    return {
      id: str(i?.id),
      what: str(i?.what),
      problems: strings(i?.problems),
      kind: (["field", "action", "content"].includes(str(i?.kind)) ? str(i?.kind) : undefined) as Item["kind"],
      existing: i?.existing === true,
      ruling: (str(i?.ruling) || (i?.existing === true ? "" : "add")) as Ruling,
      where: str(i?.where) || undefined,
      count: num(i?.count),
      total: num(i?.total),
      query: str(i?.query) || undefined,
      cost: str(i?.cost) as Cost,
      cost_reason: str(i?.cost_reason),
    };
  });
  if (!items.length) out.push("There are no items.");
  ids(items, /^I\d+$/, "Item", out);
  const covered = new Set<string>();
  for (const i of items) {
    if (!i.what) out.push(`${i.id} doesn't say what it is.`);
    if (!i.problems.length) out.push(`${i.id} isn't tied to a problem.`);
    for (const p of i.problems) {
      if (!problemIds.has(p)) out.push(`${i.id} points at ${p}, which is not a problem from step 1.`);
      covered.add(p);
    }
    if (i.existing && !["keep", "move", "drop"].includes(i.ruling)) out.push(`${i.id} is on the current page and needs a ruling: keep, move or drop.`);
    if (!i.existing && i.ruling !== "add") out.push(`${i.id} is new, so its ruling is "add".`);
    if (i.ruling === "move" && !i.where) out.push(`${i.id} is moved but doesn't say where.`);
    if (!["low", "medium", "high"].includes(i.cost)) out.push(`${i.id} needs a cost: low, medium or high.`);
    if (!i.cost_reason) out.push(`${i.id} doesn't say what a wrong answer costs a reader.`);
    if (mode === "data" && i.kind !== "action") {
      if (i.count === undefined || i.total === undefined) out.push(`${i.id} needs a count and a total: how many records have a real answer.`);
      else if (i.count < 0 || i.total <= 0 || i.count > i.total) out.push(`${i.id}'s count must be between 0 and its total, and the total above 0.`);
      if (!i.query) out.push(`${i.id} needs the query that produced its count.`);
    }
  }
  for (const p of problemIds) if (!covered.has(p)) out.push(`${p} has no item. Every problem needs something that answers it.`);
  if (out.length) throw new Refusal(out);
  return { mode: mode as Step2["mode"], items };
}

// ---------- step 3 ----------

export function checkStep3(raw: unknown, doc: Doc, lib: LibraryContext): Step3 {
  if (!isObject(raw)) throw new Refusal(["Step 3 takes an object with parts and height_limits."]);
  const out: string[] = [];
  const known = knownIds(doc, lib);
  const parts: Part[] = list(raw.parts).map((r) => {
    const s = r as any;
    return {
      id: str(s?.id),
      name: str(s?.name),
      items: strings(s?.items),
      primary: s?.primary === true,
      share: typeof s?.share === "number" ? s.share : NaN,
      reason: str(s?.reason),
      cites: strings(s?.cites),
    };
  });
  const limits: HeightLimit[] = list(raw.height_limits).map((r) => {
    const h = r as any;
    return { width: Number(h?.width), px: Number(h?.px), reason: str(h?.reason), cites: strings(h?.cites) };
  });
  if (!parts.length) out.push("There are no parts.");
  ids(parts, /^S\d+$/, "Part", out);
  const primaries = parts.filter((s) => s.primary).length;
  if (primaries !== 1) out.push(`Exactly one part is the primary element; ${primaries} are marked.`);

  const items = new Map((doc[2]?.items ?? []).map((i) => [i.id, i]));
  const placed = new Map<string, string[]>();
  for (const s of parts) {
    if (!s.name) out.push(`${s.id} has no name.`);
    if (!(s.share > 0)) out.push(`${s.id} needs a share of the view's height above 0.`);
    if (!s.items.length) out.push(`${s.id} holds no items.`);
    for (const id of s.items) {
      if (!items.has(id)) out.push(`${s.id} holds ${id}, which is not an item from step 2.`);
      placed.set(id, [...(placed.get(id) ?? []), s.id]);
    }
    citeRules(s.id, s.reason, s.cites, known, true, out);
  }
  for (const item of items.values()) {
    const where = placed.get(item.id) ?? [];
    if ((item.ruling === "keep" || item.ruling === "add") && where.length !== 1)
      out.push(where.length ? `${item.id} is in two parts (${where.join(", ")}).` : `${item.id} is ruled "${item.ruling}" but is in no part.`);
    if ((item.ruling === "drop" || item.ruling === "move") && where.length)
      out.push(`${item.id} is ruled "${item.ruling}" but is in ${where.join(", ")}.`);
  }
  for (const h of limits) {
    if (!(WIDTHS as readonly number[]).includes(h.width)) out.push(`A height limit's width is one of ${WIDTHS.join(", ")}.`);
    if (!(h.px > 0)) out.push(`The height limit at ${h.width} needs px above 0.`);
    citeRules(`The height limit at ${h.width}`, h.reason, h.cites, known, true, out);
  }
  if (!allViews(doc, lib).length) {
    const missing = WIDTHS.filter((w) => !limits.some((h) => h.width === w));
    if (missing.length) out.push(`No accepted view sets the height limit, so give height_limits for ${missing.join(", ")}.`);
  }
  if (out.length) throw new Refusal(out);
  return { parts, height_limits: limits };
}

function citeRules(label: string, reason: string, cites: string[], known: Set<string>, needsNumber: boolean, out: string[]) {
  if (!reason) out.push(`${label} has no reason.`);
  if (!cites.length) out.push(`${label}'s reason cites no ID.`);
  for (const c of cites) if (!known.has(c)) out.push(`${label} cites ${c}, which is not an ID in the document.`);
  if (needsNumber && reason && !/\d/.test(reason)) out.push(`${label} sets a size, so its reason gives the number behind it.`);
}

// ---------- step 4 ----------

export interface Step4Context {
  captures: Map<string, CaptureState | undefined>; // componentKey -> state (undefined = not captured yet)
  failed: Record<string, { url: string; selector?: string; part: string }>;
}

export interface Step4Result {
  value: Step4;
  needsCapture: { url: string; selector?: string }[];
  failedNow: Record<string, { url: string; selector?: string; part: string; error: string }>;
  captureErrors: string[];
}

export function checkStep4(raw: unknown, doc: Doc, lib: LibraryContext, ctx: Step4Context): Step4Result {
  if (!isObject(raw)) throw new Refusal(["Step 4 takes an object with references and stops."]);
  const out: string[] = [];
  const known = knownIds(doc, lib);
  const views = new Map(allViews(doc, lib).map((v) => [v.id, v]));
  const approved = new Map(lib.approved.map((e) => [e.id, e]));
  const rejected = new Map(lib.rejected.map((r) => [componentKey(r.url, r.selector), r]));
  const parts = new Set((doc[3]?.parts ?? []).map((s) => s.id));
  const problems = new Set((doc[1]?.problems ?? []).map((p) => p.id));

  const references: Reference[] = list(raw.references).map((r) => {
    const x = r as any;
    const ref: Reference = {
      id: str(x?.id),
      part: str(x?.part),
      problems: strings(x?.problems),
      tier: str(x?.tier) as Tier,
      source: str(x?.source),
      url: str(x?.url),
      selector: str(x?.selector) || undefined,
      view: str(x?.view) || undefined,
      library_id: str(x?.library_id) || undefined,
      why_not_inside: str(x?.why_not_inside) || undefined,
      part_list: list(x?.part_list).map((p) => ({ id: str((p as any)?.id), name: str((p as any)?.name), what: str((p as any)?.what) })),
    };
    if (ref.tier === "accepted" && ref.view && views.has(ref.view) && !ref.url) ref.url = views.get(ref.view)!.url;
    if (ref.tier === "library" && ref.library_id && approved.has(ref.library_id)) {
      const e = approved.get(ref.library_id)!;
      if (!ref.url) ref.url = e.url;
      if (!ref.selector) ref.selector = e.selector;
      if (!ref.source) ref.source = e.source;
    }
    return ref;
  });
  const stops: Stop[] = list(raw.stops).map((s) => ({ part: str((s as any)?.part), reason: str((s as any)?.reason) }));

  ids(references, /^R\d+$/, "Reference", out);
  const byPart = new Map<string, Reference[]>();
  for (const r of references) {
    if (!parts.has(r.part)) out.push(`${r.id} is for ${r.part || "no part"}, which is not a part from step 3.`);
    byPart.set(r.part, [...(byPart.get(r.part) ?? []), r]);
    if (!r.problems.length) out.push(`${r.id} names no problem. A reference is found from a problem.`);
    for (const p of r.problems) if (!problems.has(p)) out.push(`${r.id} names ${p}, which is not a problem from step 1.`);
    if (!r.source) out.push(`${r.id} doesn't say what component it is and where it comes from.`);
    if (r.tier === "accepted") {
      if (!r.view || !views.has(r.view)) out.push(`${r.id} is from an accepted view, so "view" names one: ${[...views.keys()].join(", ") || "none listed"}.`);
      if (!r.selector) out.push(`${r.id} needs the selector of the component within its view.`);
    } else if (r.tier === "library") {
      if (!r.library_id || !approved.has(r.library_id)) out.push(`${r.id} is from the library, so "library_id" names an approved entry.`);
    } else if (r.tier === "outside") {
      if ((r.why_not_inside ?? "").length < 20)
        out.push(`${r.id} comes from outside, so "why_not_inside" says what you checked in the accepted views and the library and why none fits.`);
    } else out.push(`${r.id}'s tier is accepted, library or outside.`);
    if (!isUrl(r.url)) out.push(`${r.id} needs a full URL.`);
    if (!r.part_list.length) out.push(`${r.id} has no part list. Write down every visible piece of the component.`);
    const pieceIds = new Set<string>();
    for (const piece of r.part_list) {
      if (!new RegExp(`^${r.id}\\.[a-z]+$`).test(piece.id)) out.push(`Piece "${piece.id}" of ${r.id} should look like ${r.id}.a.`);
      if (pieceIds.has(piece.id)) out.push(`${piece.id} is used twice.`);
      pieceIds.add(piece.id);
      if (!piece.name) out.push(`${piece.id} has no name.`);
    }
    const bad = rejected.get(componentKey(r.url, r.selector));
    if (bad) out.push(`${r.id} (${r.url}${r.selector ? " " + r.selector : ""}) was rejected by the user: "${bad.reason}". Find another.`);
  }
  for (const s of stops) {
    if (!parts.has(s.part)) out.push(`A stop names ${s.part || "no part"}, which is not a part from step 3.`);
    if (!s.reason) out.push(`The stop for ${s.part} needs the reason nothing real fits.`);
    if (byPart.has(s.part)) out.push(`${s.part} has references and a stop. Either a real component fits or it doesn't.`);
  }
  for (const s of parts) if (!byPart.has(s) && !stops.some((x) => x.part === s)) out.push(`${s} has no reference and no stop.`);

  // A reference whose screenshot failed cannot be quietly replaced.
  for (const [id, f] of Object.entries(ctx.failed)) {
    if (stops.some((x) => x.part === f.part)) continue;
    const same = references.find((r) => r.id === id);
    if (!same || normalizeUrl(same.url) !== normalizeUrl(f.url))
      out.push(`${id} (${f.url}) failed to capture. A failed reference can't be swapped for another; fix its capture, or stop ${f.part} and tell the user.`);
  }
  if (out.length) throw new Refusal(out);

  const needsCapture: { url: string; selector?: string }[] = [];
  const failedNow: Step4Result["failedNow"] = {};
  const capError: string[] = [];
  for (const r of references) {
    const state = ctx.captures.get(componentKey(r.url, r.selector));
    if (!state) needsCapture.push({ url: r.url, selector: r.selector });
    else if (!state.ok) {
      failedNow[r.id] = { url: r.url, selector: r.selector, part: r.part, error: state.error ?? "did not render" };
      capError.push(`${r.id} didn't capture: ${state.error ?? "did not render"}.`);
    }
  }
  for (const v of allViews(doc, lib)) {
    const state = ctx.captures.get(componentKey(v.url, v.selector));
    if (!state) needsCapture.push({ url: v.url, selector: v.selector });
    else if (!state.ok) capError.push(`Accepted view ${v.id} (${v.name}) didn't capture: ${state.error ?? "did not render"}.`);
  }
  return { value: { references, stops }, needsCapture, failedNow, captureErrors: capError };
}

// ---------- step 5 ----------

export function checkStep5(raw: unknown, doc: Doc, lib: LibraryContext): Step5 {
  if (!isObject(raw)) throw new Refusal(["Step 5 takes an object with build."]);
  const out: string[] = [];
  const known = knownIds(doc, lib);
  const views = new Set(allViews(doc, lib).map((v) => v.id));
  const refs = doc[4]?.references ?? [];
  const refById = new Map(refs.map((r) => [r.id, r]));
  const pieceToRef = new Map<string, string>();
  for (const r of refs) for (const p of r.part_list) pieceToRef.set(p.id, r.id);

  const build: BuildLine[] = list(raw.build).map((r) => {
    const b = r as any;
    const values: Record<string, string | string[]> = {};
    if (isObject(b?.values))
      for (const [k, v] of Object.entries(b.values)) {
        if (typeof v === "string" && v.trim()) values[k.trim()] = v.trim();
        else if (Array.isArray(v)) {
          const vs = strings(v);
          if (vs.length) values[k.trim()] = vs;
        }
      }
    return {
      id: str(b?.id),
      part: str(b?.part),
      covers: strings(b?.covers),
      from: str(b?.from) as BuildLine["from"],
      source: str(b?.source) || undefined,
      selector: str(b?.selector) || undefined,
      form: str(b?.form) as Form,
      text: str(b?.text) || undefined,
      values: Object.keys(values).length ? values : undefined,
      reason: str(b?.reason),
      cites: strings(b?.cites),
    };
  });
  if (!build.length) out.push("There are no build lines.");
  ids(build, /^B\d+$/, "Build line", out);
  const covered = new Set<string>();
  const usedRefs = new Set<string>();
  const partsWithLines = new Set<string>();
  for (const b of build) {
    const label = b.id;
    if (!doc[3]?.parts.some((s) => s.id === b.part)) out.push(`${label} is for ${b.part || "no part"}, which is not a part from step 3.`);
    partsWithLines.add(b.part);
    if (!b.covers.length) out.push(`${label} covers no piece of a reference's part list.`);
    for (const c of b.covers) {
      const refId = pieceToRef.get(c);
      if (!refId) out.push(`${label} covers ${c}, which is not a piece on any reference's part list.`);
      else if (refById.get(refId)!.part !== b.part) out.push(`${label} covers ${c}, which belongs to a reference for ${refById.get(refId)!.part}, not ${b.part}.`);
      else {
        covered.add(c);
        usedRefs.add(refId);
      }
    }
    if (!(FORMS as readonly string[]).includes(b.form)) out.push(`${label}'s form is one of ${FORMS.join(", ")}.`);
    if (b.from === "accepted") {
      const ok = (b.source && views.has(b.source)) || (b.source && refById.get(b.source)?.tier === "accepted");
      if (!ok) out.push(`${label} is from an accepted component, so "source" names an accepted view or an accepted-tier reference.`);
      if (!b.selector) out.push(`${label} needs the selector of the accepted component it is built from.`);
    } else if (b.from === "new") {
      if (!b.values) out.push(`${label} is new, so it gives its exact values (font size, colour, spacing...).`);
    } else out.push(`${label}'s "from" is accepted or new.`);
    if (!b.text && !TEXTLESS_FORMS.has(b.form) && b.from === "new") out.push(`${label} shows text, so it gives the exact text.`);
    citeRules(label, b.reason, b.cites, known, false, out);
  }
  for (const refId of usedRefs) {
    const missing = refById.get(refId)!.part_list.filter((p) => !covered.has(p.id));
    for (const p of missing) out.push(`${p.id} (${p.name}) is on ${refId}'s part list but has no build line. Port every piece of the component.`);
  }
  for (const s of doc[3]?.parts ?? []) if (!partsWithLines.has(s.id)) out.push(`${s.id} has no build line.`);
  if (out.length) throw new Refusal(out);
  return { build };
}

// ---------- step 6 ----------

export function checkStep6(raw: unknown): Step6 {
  if (!isObject(raw)) throw new Refusal(["Step 6 takes an object with views."]);
  const out: string[] = [];
  const views: BuiltView[] = list(raw.views).map((v) => ({ state: str((v as any)?.state), url: str((v as any)?.url), selector: str((v as any)?.selector) }));
  if (!views.length) out.push("Give the URL of the built view, the default state first.");
  const states = new Set<string>();
  for (const v of views) {
    if (!v.state) out.push("Each view needs a state name.");
    if (states.has(v.state)) out.push(`State "${v.state}" is listed twice.`);
    states.add(v.state);
    if (!isUrl(v.url)) out.push(`State "${v.state}" needs a full URL.`);
    if (!v.selector) out.push(`State "${v.state}" needs the selector of the view's outer element.`);
  }
  if (out.length) throw new Refusal(out);
  return { views };
}
