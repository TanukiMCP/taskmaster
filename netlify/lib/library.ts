// Splits the library files into the pieces Taskmaster hands out with each operation.
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

export const ID_PATTERN = /^[a-z0-9][a-z0-9._-]*$/;

const STEP_HEADING = /^(\d{1,2})\. (.+)$/;
const SOP_HEADING = /^(\d{1,2})\. (.+?) \[process ([^\]]+)\](?: \((diagnose|trace|verify)\))?$/;
const PREAMBLE_SECTIONS = ["Purpose and working method", "The chain", "Running with Taskmaster", "Applying the methods", "Observable execution"];
const ENTRY_REF = /^design\/([a-z]+)\/([a-z-]+)(?:#([a-z0-9._-]+))?$/;
const STEP_REF = /^design\/process\/(\d{1,2})$/;
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
  id: string;
  title: string;
  refs: string[];
  modifier: Modifier;
  kind: StepKind;
  needs: string[];
  produces: string;
  instruction: string;
}

// The procedure steps an SOP step works in. The responsible step k is named by a trace at run time.
export function stepNumbers(step: SopStep): number[] {
  const found: number[] = [];
  for (const ref of step.refs) {
    if (ref === "k" || ref === "k+") continue;
    if (ref.includes("–")) {
      const [first, last] = ref.split("–").map(Number);
      for (let n = first; n <= last; n++) found.push(n);
    } else {
      found.push(Number(ref));
    }
  }
  return found;
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

export interface ReadyOperation {
  id: string;
  needs: string[];
  does: string;
  produces: string;
  guide: string;
}

export interface Library {
  method: string;
  procedure: Procedure;
  matrix: string;
  situations: Record<SituationKey, SituationSop>;
  scopes: Record<ScopeKey, ScopeSheet>;
}

export const INDEX = `Library references, for library(ref) and for an operation's guide:
- method: the working method Taskmaster runs.
- design: the design library's matrix, for choosing a situation and scope.
- design/<situation>/<scope>: that entry's SOP, scope sheet, and ready composition to adopt with compose.
- design/<situation>/<scope>#<id>: one operation's guide in that composition.
- design/process: the whole design procedure; design/process/<n>: one step of it (0–10).`;

const DESIGN_INDEX =
  "Reading the design library\n\n" +
  "Choose the situation and the smallest scope with the selector above, then read library('design/<situation>/<scope>') " +
  "for that entry's SOP, scope sheet, and ready composition. library('design/process/<n>') returns one procedure step in full.\n\n" +
  `Situations: ${Object.keys(SITUATIONS).join(", ")}\nScopes: ${Object.keys(SCOPES).join(", ")}`;

const COMPOSITION_NOTE =
  'Adopt this with compose. Write each operation\'s "does" for this assignment: the specific work it will do, the questions ' +
  'it must answer, and the result that will show it is complete. Make "produces" specific where you can. Keep the ids, needs, ' +
  "and guides unless the task needs a different derivation. For a request that spans several entries, prefix each entry's ids " +
  "with its name (pricing.question) and have the first operation of a later entry also need the last operation of the one before.";

// A matrix entry's ready composition: one operation per SOP step, for compose.
export function composition(lib: Library, situation: SituationKey, scope: ScopeKey): ReadyOperation[] {
  return lib.situations[situation].steps.map((s) => ({
    id: s.id,
    needs: [...s.needs],
    does: "",
    produces: s.produces,
    guide: `design/${situation}/${scope}#${s.id}`,
  }));
}

const isSituation = (key: string): key is SituationKey => key in SITUATIONS;
const isScope = (key: string): key is ScopeKey => key in SCOPES;

// The text a library reference names, or null when it names nothing.
export function readLibrary(lib: Library, reference: string): string | null {
  const ref = reference.trim().replace(/^\/+|\/+$/g, "");
  if (ref === "") return INDEX;
  if (ref === "method") return lib.method;
  if (ref === "design") return `${lib.matrix}\n\n${DESIGN_INDEX}`;
  if (ref === "design/process") return lib.procedure.fullText;
  const stepMatch = STEP_REF.exec(ref);
  if (stepMatch) return lib.procedure.steps.get(Number(stepMatch[1]))?.text ?? null;
  const match = ENTRY_REF.exec(ref);
  if (!match || !isSituation(match[1]) || !isScope(match[2])) return null;
  const [, situation, scope, stepId] = match as unknown as [string, SituationKey, ScopeKey, string | undefined];
  if (stepId === undefined) return entryText(lib, situation, scope);
  const step = lib.situations[situation].steps.find((s) => s.id === stepId);
  return step ? guideText(lib, situation, scope, step) : null;
}

function entryText(lib: Library, situation: SituationKey, scope: ScopeKey): string {
  const listing = "[\n" + composition(lib, situation, scope).map((op) => "  " + JSON.stringify(op)).join(",\n") + "\n]";
  return [
    `# ${SITUATIONS[situation]} × ${SCOPES[scope]}`,
    `## Situation SOP: ${SITUATIONS[situation]}`,
    lib.situations[situation].fullText,
    `## Scope: ${SCOPES[scope]}`,
    lib.scopes[scope].fullText,
    "## Ready composition",
    COMPOSITION_NOTE,
    listing,
  ].join("\n\n");
}

function guideText(lib: Library, situation: SituationKey, scope: ScopeKey, step: SopStep): string {
  const sop = lib.situations[situation];
  const sheet = lib.scopes[scope];
  const numbers = stepNumbers(step);
  const tag = step.kind === "work" ? "" : ` (${step.kind})`;
  const where = usesK(step)
    ? "the step the trace named" + (step.refs.includes("k+") ? ", then each later step" : "")
    : numbers.map((n) => `${n} (${lib.procedure.steps.get(n)!.name})`).join(", ");
  const parts = [
    `### ${sop.title} × ${sheet.title}, SOP step ${step.number} of ${sop.steps.length}: ${step.title}${tag}`,
    `Works in procedure step: ${where}\nMay change: ${sop.mayChange}\nMust preserve: ${sop.mustPreserve}`,
    "### SOP step",
    step.instruction,
  ];
  const lineSteps = usesK(step) ? Array.from({ length: VERIFY_STEP + 1 }, (_, n) => n) : numbers;
  const scopeLines = [`Boundary: ${sheet.fields["Boundary"] ?? ""}`, ...scopeLinesFor(sheet, lineSteps).map(([l, t]) => `${l}: ${t}`)];
  parts.push(`### Scope: ${sheet.title}`, scopeLines.join("\n"));
  for (const n of numbers) {
    const proc = lib.procedure.steps.get(n)!;
    if (step.modifier === "keep") {
      parts.push(`### Procedure step ${n}: ${proc.name}, Keep rule (library('design/process/${n}') for the full step)`, paragraph(proc, "Keep:"));
    } else if (step.modifier === "produces") {
      parts.push(`### Procedure step ${n}: ${proc.name}, what it produces (library('design/process/${n}') for the full step)`, paragraph(proc, "Produces:"));
    } else {
      parts.push(`### Procedure step ${n}: ${proc.name} (verbatim)`, proc.text);
    }
  }
  parts.push("### Working rules", lib.procedure.workingRules);
  if (step === sop.steps.at(-1)) parts.push("### Completion", sop.completion);
  return parts.filter(Boolean).join("\n\n");
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
        id: "",
        title: match[2].trim(),
        refs: refsText.split(",").map((r) => r.trim()).filter(Boolean),
        modifier,
        kind: (match[4] ?? "work") as StepKind,
        needs: [],
        produces: "",
      };
      body = [];
    } else if (current && !body.length && /^(Id|Needs|Produces):/.test(line)) {
      const at = line.indexOf(":");
      const name = line.slice(0, at);
      const value = line.slice(at + 1).trim();
      if (name === "Id") current.id = value;
      else if (name === "Needs") current.needs = value.split(",").map((n) => n.trim()).filter(Boolean);
      else current.produces = value;
    } else if (current) {
      body.push(line);
    }
  }
  close();

  const seen = new Set<string>();
  steps.forEach((s, i) => {
    if (s.number !== i + 1) throw new Error(`Situation '${key}' SOP steps must be numbered 1..n in order`);
    if (!ID_PATTERN.test(s.id) || seen.has(s.id)) throw new Error(`Situation '${key}' step ${s.number} needs a unique Id`);
    if (!s.produces) throw new Error(`Situation '${key}' step ${s.number} needs a Produces line`);
    const missing = s.needs.filter((n) => !seen.has(n));
    if (missing.length) throw new Error(`Situation '${key}' step ${s.number} needs ${missing.join(", ")}, which are not earlier steps`);
    seen.add(s.id);
  });
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
    if (text === undefined) throw new Error(`Missing library file: ${name}`);
    return text.replace(/\r\n/g, "\n");
  };
  const situations = Object.fromEntries(
    (Object.keys(SITUATIONS) as SituationKey[]).map((k) => [k, parseSituation(k, read(`design/situations/${k}.txt`))]),
  ) as Record<SituationKey, SituationSop>;
  const scopes = Object.fromEntries(
    (Object.keys(SCOPES) as ScopeKey[]).map((k) => [k, parseScope(k, read(`design/scopes/${k}.txt`))]),
  ) as Record<ScopeKey, ScopeSheet>;
  return {
    method: read("method.txt").trim(),
    procedure: parseProcedure(read("design/process.txt")),
    matrix: read("design/matrix.txt").trim(),
    situations,
    scopes,
  };
}
