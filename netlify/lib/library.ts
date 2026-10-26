// Splits the design files into the pieces Taskmaster hands out one step at a time.
// Mirrors taskmaster/library.py; the text files are the authority and are never reworded.

export const SITUATIONS = {
  create: "Create",
  extend: "Extend",
  redesign: "Redesign",
  fix: "Fix",
  review: "Review",
} as const;

export const SCOPES = {
  element: "Element",
  component: "Component",
  section: "Section",
  page: "Page or view",
  flow: "Flow",
  product: "Product",
  "shared-styles": "Shared styles and assets",
} as const;

export type SituationKey = keyof typeof SITUATIONS;
export type ScopeKey = keyof typeof SCOPES;

export const FIRST_STEP = 0;
export const VERIFY_STEP = 10;

// Which procedure steps each "At this scope" line speaks to.
export const SCOPE_LABELS: Record<string, number[]> = {
  Question: [0],
  "Content and order": [1, 2],
  Components: [3],
  Foundations: [4, 5, 6, 7],
  Layout: [8],
  Behavior: [9],
  Verify: [10],
};

const STEP_HEADING = /^(\d{1,2})\. (.+)$/;
const SOP_HEADING = /^(\d{1,2})\. (.+?) \[process ([^\]]+)\](?: \((diagnose|trace|verify)\))?$/;
const PREAMBLE_SECTIONS = ["Purpose and working method", "The chain", "Running with Taskmaster", "Applying the methods", "Observable execution"];
const MODIFIERS = ["full", "keep", "produces"] as const;

export type StepKind = "work" | "diagnose" | "trace" | "verify";
export type Modifier = (typeof MODIFIERS)[number];

export interface Step {
  number: number;
  name: string;
  text: string;
}

export function paragraph(step: Step, prefix: string): string {
  return step.text.split("\n\n").find((block) => block.startsWith(prefix))?.trim() ?? "";
}

export interface Procedure {
  preamble: string;
  sections: Record<string, string>;
  steps: Map<number, Step>;
  limits: string;
  fullText: string;
  workingRules: string;
}

export interface SopStep {
  number: number;
  title: string;
  refs: string[];
  modifier: Modifier;
  kind: StepKind;
  instruction: string;
}

export function resolveRefs(step: SopStep, k: number | null): number[] {
  const steps: number[] = [];
  for (const ref of step.refs) {
    if (ref === "k") {
      if (k !== null) steps.push(k);
    } else if (ref === "k+") {
      if (k !== null) for (let n = k + 1; n < VERIFY_STEP; n++) steps.push(n);
    } else if (ref.includes("–")) {
      const [first, last] = ref.split("–").map(Number);
      for (let n = first; n <= last; n++) steps.push(n);
    } else {
      steps.push(Number(ref));
    }
  }
  return steps;
}

export const usesK = (step: SopStep) => step.refs.some((ref) => ref === "k" || ref === "k+");

export interface SituationSop {
  key: SituationKey;
  title: string;
  brief: string;
  mayChange: string;
  mustPreserve: string;
  steps: SopStep[];
  completion: string;
  fullText: string;
}

export interface ScopeSheet {
  key: ScopeKey;
  title: string;
  brief: string;
  fields: Record<string, string>;
  atScope: Record<string, string>;
  expansion: string;
  fullText: string;
}

export function scopeLinesFor(sheet: ScopeSheet, steps: number[]): Array<[string, string]> {
  const wanted = new Set(steps);
  return Object.entries(sheet.atScope).filter(([label]) => SCOPE_LABELS[label].some((n) => wanted.has(n)));
}

export interface Library {
  procedure: Procedure;
  matrix: string;
  situations: Record<SituationKey, SituationSop>;
  scopes: Record<ScopeKey, ScopeSheet>;
}

function splitSections(text: string, names: string[]): Record<string, string> {
  const found: Record<string, string[]> = { "": [] };
  let current = "";
  for (const line of text.split("\n")) {
    if (names.includes(line.trim())) {
      current = line.trim();
      found[current] = [];
      continue;
    }
    found[current].push(line);
  }
  return Object.fromEntries(Object.entries(found).map(([k, v]) => [k, v.join("\n").trim()]));
}

export function parseProcedure(text: string): Procedure {
  const lines = text.split("\n");
  const starts: Array<[number, number, string]> = [];
  let limitsAt = lines.length;
  lines.forEach((line, i) => {
    const match = STEP_HEADING.exec(line);
    if (match && Number(match[1]) === starts.length) starts.push([i, Number(match[1]), match[2].trim()]);
    else if (line.trim() === "Remaining limits" && starts.length) limitsAt = i;
  });
  if (starts.length !== VERIFY_STEP + 1) throw new Error("process.txt must contain step headings 0. through 10. in order");
  const steps = new Map<number, Step>();
  starts.forEach(([lineNo, number, name], index) => {
    const end = index + 1 < starts.length ? starts[index + 1][0] : limitsAt;
    steps.set(number, { number, name, text: lines.slice(lineNo, end).join("\n").trim() });
  });
  const preamble = lines.slice(0, starts[0][0]).join("\n").trim();
  const sections = splitSections(preamble, PREAMBLE_SECTIONS);
  const decideKeep = (sections["The chain"] ?? "")
    .split("\n\n")
    .filter((block) => block.startsWith("Decide:") || block.startsWith("Keep:"))
    .join("\n\n");
  const workingRules = [decideKeep, sections["Observable execution"] ?? ""].filter(Boolean).join("\n\n");
  return { preamble, sections, steps, limits: lines.slice(limitsAt).join("\n").trim(), fullText: text.trim(), workingRules };
}

function field(text: string, prefix: string): string {
  const line = text.split("\n").find((l) => l.startsWith(prefix));
  return line ? line.slice(prefix.length).trim() : "";
}

export function parseSituation(key: SituationKey, text: string): SituationSop {
  const split = text.indexOf("\nSOP\n");
  if (split < 0) throw new Error(`Situation '${key}' has no SOP section`);
  const head = text.slice(0, split);
  const rest = text.slice(split + "\nSOP\n".length);
  const blocks = head.split("\n\n").map((b) => b.trim()).filter(Boolean);
  const brief = blocks.slice(1).filter((b) => !b.startsWith("May change:") && !b.startsWith("Must preserve:")).join("\n\n");
  const completionAt = rest.indexOf("\nCompletion:");
  const sopText = completionAt >= 0 ? rest.slice(0, completionAt) : rest;
  const completion = completionAt >= 0 ? rest.slice(completionAt + "\nCompletion:".length).trim() : "";

  const steps: SopStep[] = [];
  let current: Omit<SopStep, "instruction"> | null = null;
  let body: string[] = [];
  const close = () => {
    if (current) steps.push({ ...current, instruction: body.join("\n").trim() });
  };
  for (const line of sopText.split("\n")) {
    const match = SOP_HEADING.exec(line.trim());
    if (match) {
      close();
      const [refsText, modifierText = ""] = match[3].split(":");
      const modifier = (modifierText.trim() || "full") as Modifier;
      if (!MODIFIERS.includes(modifier)) throw new Error(`Situation '${key}' step ${match[1]} has unknown modifier '${modifier}'`);
      current = {
        number: Number(match[1]),
        title: match[2].trim(),
        refs: refsText.split(",").map((r) => r.trim()).filter(Boolean),
        modifier,
        kind: (match[4] ?? "work") as StepKind,
      };
      body = [];
    } else if (current) {
      body.push(line);
    }
  }
  close();
  steps.forEach((s, i) => {
    if (s.number !== i + 1) throw new Error(`Situation '${key}' SOP steps must be numbered 1..n in order`);
  });
  if (!steps.some((s) => s.kind === "verify")) throw new Error(`Situation '${key}' needs a verify step`);
  if (steps.some(usesK) && !steps.some((s) => s.kind === "trace")) {
    throw new Error(`Situation '${key}' refers to the responsible step k without a trace step`);
  }
  return {
    key,
    title: SITUATIONS[key],
    brief,
    mayChange: field(head, "May change:"),
    mustPreserve: field(head, "Must preserve:"),
    steps,
    completion,
    fullText: text.trim(),
  };
}

export function parseScope(key: ScopeKey, text: string): ScopeSheet {
  const split = text.indexOf("\nAt this scope\n");
  if (split < 0) throw new Error(`Scope '${key}' has no 'At this scope' section`);
  const head = text.slice(0, split);
  const rest = text.slice(split + "\nAt this scope\n".length);
  const blocks = head.split("\n\n").map((b) => b.trim()).filter(Boolean);
  const fieldBlock = blocks.find((b) => b.startsWith("Parent:")) ?? "";
  const brief = blocks.slice(1).filter((b) => b !== fieldBlock).join("\n\n");
  const fields: Record<string, string> = {};
  for (const line of fieldBlock.split("\n")) {
    const at = line.indexOf(":");
    if (at > 0) fields[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  const expansionAt = rest.indexOf("\nExpansion:");
  const atText = expansionAt >= 0 ? rest.slice(0, expansionAt) : rest;
  const expansion = expansionAt >= 0 ? rest.slice(expansionAt + "\nExpansion:".length).trim() : "";
  const atScope: Record<string, string> = {};
  for (const line of atText.split("\n")) {
    const at = line.indexOf(":");
    if (at > 0 && line.slice(0, at).trim() in SCOPE_LABELS) atScope[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  const missing = Object.keys(SCOPE_LABELS).filter((label) => !(label in atScope));
  if (missing.length) throw new Error(`Scope '${key}' is missing 'At this scope' lines: ${missing.join(", ")}`);
  return { key, title: SCOPES[key], brief, fields, atScope, expansion, fullText: text.trim() };
}

export function loadLibrary(files: Record<string, string>): Library {
  const read = (name: string) => {
    const text = files[name];
    if (text === undefined) throw new Error(`Missing design file: ${name}`);
    return text.replace(/\r\n/g, "\n");
  };
  const situations = Object.fromEntries(
    (Object.keys(SITUATIONS) as SituationKey[]).map((k) => [k, parseSituation(k, read(`prompts/situations/${k}.txt`))]),
  ) as Record<SituationKey, SituationSop>;
  const scopes = Object.fromEntries(
    (Object.keys(SCOPES) as ScopeKey[]).map((k) => [k, parseScope(k, read(`prompts/scopes/${k}.txt`))]),
  ) as Record<ScopeKey, ScopeSheet>;
  return { procedure: parseProcedure(read("process.txt")), matrix: read("matrix.txt").trim(), situations, scopes };
}
