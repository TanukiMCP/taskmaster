// Splits the design files into the pieces Taskmaster hands out one step at a time.
// Mirrors taskmaster/library.py; the text files are the authority and are never reworded.

export const SITUATIONS = {
  create: "Create",
  extend: "Extend",
  improve: "Improve",
  fix: "Fix",
  review: "Review",
} as const;

export const SCOPES = {
  component: "Component",
  page: "Page or view",
  flow: "Flow",
  "shared-styles": "Shared styles and assets",
  product: "Product",
} as const;

export type SituationKey = keyof typeof SITUATIONS;
export type ScopeKey = keyof typeof SCOPES;

export const FIRST_STEP = 0;
export const VERIFY_STEP = 10;

const STEP_HEADING = /^(\d{1,2})\. (.+)$/;
const NUMBERED_RULE = /^(\d{1,2})(?:–(\d{1,2}))?(?: [A-Za-z][A-Za-z ]*)?: (.+)$/;

export interface Step {
  number: number;
  name: string;
  text: string;
}

export interface Procedure {
  preamble: string;
  steps: Map<number, Step>;
  limits: string;
  fullText: string;
}

export interface SituationPrompt {
  key: SituationKey;
  title: string;
  header: string;
  diagnosis: string;
  rules: Map<number, string>;
  beforeK: string;
  atK: string;
  afterK: string;
  completion: string;
  fullText: string;
}

export interface ScopePrompt {
  key: ScopeKey;
  title: string;
  header: string;
  limits: Map<number, string>;
  expansion: string;
  fullText: string;
}

export interface Library {
  procedure: Procedure;
  matrix: string;
  situations: Record<SituationKey, SituationPrompt>;
  scopes: Record<ScopeKey, ScopePrompt>;
}

export function ruleFor(situation: SituationPrompt, step: number, k: number | null): string {
  if (k !== null && situation.atK) {
    if (step < k) return situation.beforeK;
    if (step === k) return situation.atK;
    if (step !== VERIFY_STEP) return situation.afterK;
  }
  return situation.rules.get(step) ?? "";
}

export function parseProcedure(text: string): Procedure {
  const lines = text.split("\n");
  const starts: Array<[number, number, string]> = [];
  let limitsAt = lines.length;
  lines.forEach((line, i) => {
    const match = STEP_HEADING.exec(line);
    if (match && Number(match[1]) === starts.length) {
      starts.push([i, Number(match[1]), match[2].trim()]);
    } else if (line.trim() === "Remaining limits" && starts.length) {
      limitsAt = i;
    }
  });
  if (starts.length !== VERIFY_STEP + 1) {
    throw new Error("process.txt must contain step headings 0. through 10. in order");
  }
  const steps = new Map<number, Step>();
  starts.forEach(([lineNo, number, name], index) => {
    const end = index + 1 < starts.length ? starts[index + 1][0] : limitsAt;
    steps.set(number, { number, name, text: lines.slice(lineNo, end).join("\n").trim() });
  });
  return {
    preamble: lines.slice(0, starts[0][0]).join("\n").trim(),
    steps,
    limits: lines.slice(limitsAt).join("\n").trim(),
    fullText: text.trim(),
  };
}

function sections(text: string, names: string[]): Record<string, string> {
  const found: Record<string, string[]> = { header: [] };
  let current = "header";
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

function pullLine(text: string, prefix: string): [string, string] {
  let pulled = "";
  const kept: string[] = [];
  for (const line of text.split("\n")) {
    if (!pulled && line.startsWith(prefix)) {
      pulled = line.slice(prefix.length).trim();
      continue;
    }
    kept.push(line);
  }
  return [pulled, kept.join("\n").trim()];
}

const afterColon = (line: string) => line.slice(line.indexOf(":") + 1).trim();

export function parseSituation(key: SituationKey, text: string): SituationPrompt {
  const parts = sections(text, ["Diagnosis", "Step rules"]);
  const [completion, rulesText] = pullLine(parts["Step rules"] ?? "", "Completion:");
  const rules = new Map<number, string>();
  let beforeK = "";
  let atK = "";
  let afterK = "";
  for (const raw of rulesText.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("Steps before k:")) beforeK = afterColon(line);
    else if (line.startsWith("Step k and every later step:")) atK = afterK = afterColon(line);
    else if (line.startsWith("Step k:")) atK = afterColon(line);
    else if (line.startsWith("Steps after k:")) afterK = afterColon(line);
    else {
      const match = NUMBERED_RULE.exec(line);
      if (!match) throw new Error(`Unreadable step rule in situation '${key}': ${line}`);
      const first = Number(match[1]);
      const last = Number(match[2] ?? first);
      for (let step = first; step <= last; step++) rules.set(step, match[3].trim());
    }
  }
  return {
    key,
    title: SITUATIONS[key],
    header: parts.header,
    diagnosis: parts["Diagnosis"] ?? "",
    rules,
    beforeK,
    atK,
    afterK,
    completion,
    fullText: text.trim(),
  };
}

export function parseScope(key: ScopeKey, text: string): ScopePrompt {
  const parts = sections(text, ["Step limits"]);
  const [expansion, limitsText] = pullLine(parts["Step limits"] ?? "", "Expansion:");
  const limits = new Map<number, string>();
  const notes: string[] = [];
  for (const raw of limitsText.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const match = NUMBERED_RULE.exec(line);
    if (match) limits.set(Number(match[1]), match[3].trim());
    else notes.push(line);
  }
  for (let step = FIRST_STEP; step <= VERIFY_STEP; step++) {
    if (!limits.has(step)) throw new Error(`Scope '${key}' has no limit for step ${step}`);
  }
  return {
    key,
    title: SCOPES[key],
    header: [parts.header, ...notes].join("\n\n").trim(),
    limits,
    expansion,
    fullText: text.trim(),
  };
}

export function loadLibrary(files: Record<string, string>): Library {
  const read = (name: string) => {
    const text = files[name];
    if (text === undefined) throw new Error(`Missing design file: ${name}`);
    return text.replace(/\r\n/g, "\n");
  };
  const situations = Object.fromEntries(
    (Object.keys(SITUATIONS) as SituationKey[]).map((k) => [k, parseSituation(k, read(`prompts/situations/${k}.txt`))]),
  ) as Record<SituationKey, SituationPrompt>;
  const scopes = Object.fromEntries(
    (Object.keys(SCOPES) as ScopeKey[]).map((k) => [k, parseScope(k, read(`prompts/scopes/${k}.txt`))]),
  ) as Record<ScopeKey, ScopePrompt>;
  return { procedure: parseProcedure(read("process.txt")), matrix: read("matrix.txt").trim(), situations, scopes };
}
