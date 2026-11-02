"""The backward trace: find values in the product's files that did not come from the manifest.

Under the closed world, code refers to manifest values through the token files and states
no literal of its own. A literal color, length, duration, font, or media file outside the
token files is a value the builder supplied itself, which is what a silent default is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .record import Record

WEB = {".css", ".scss", ".sass", ".less", ".html", ".htm", ".vue", ".svelte", ".astro", ".js", ".jsx", ".mjs", ".ts", ".tsx"}
OTHER = {".gd", ".tscn", ".tres", ".cs", ".py", ".lua"}
SKIP_DIRS = {".git", ".coherence", "node_modules", "dist", "build", ".venv", "__pycache__"}
TRIVIAL = {"0", "0px", "0rem", "0em", "0s", "0ms", "100%"}

COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgba?|hsla?)\([^)]*\)")
LENGTH = re.compile(r"(?<![\w.#-])-?(?:\d+\.?\d*|\.\d+)(?:px|rem|em|vh|vw|vmin|vmax|pt)\b")
DURATION = re.compile(r"(?<![\w.#-])(?:\d+\.?\d*|\.\d+)(?:ms|s)\b")
FONT = re.compile(r"font-family\s*:\s*([^;}\n]+)|fontFamily\s*[:=]\s*['\"`]([^'\"`]+)['\"`]")
MEDIA = re.compile(r"[\w./-]+\.(?:png|jpe?g|gif|webp|avif|svg|mp3|wav|ogg|m4a|glb|gltf|fbx|obj|ttf|otf|woff2?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    literal: str
    kind: str


def _norm(value: str) -> str:
    return " ".join(value.strip().strip("'\"`").lower().split())


def _files(project: Path, patterns: list[str], skip: set[Path]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        pattern = pattern.strip().lstrip("./")
        if not pattern:
            continue
        candidates = [project / pattern] if not any(c in pattern for c in "*?[") else list(project.glob(pattern))
        for path in candidates:
            paths = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path] if path.is_file() else []
            for p in paths:
                resolved = p.resolve()
                if resolved in found or any(part in SKIP_DIRS for part in p.relative_to(project).parts):
                    continue
                if any(resolved == s or s in resolved.parents for s in skip):
                    continue
                if p.suffix.lower() in WEB | OTHER:
                    found.append(resolved)
    return found


def scan(record: Record, project: Path, patterns: list[str]) -> list[Finding]:
    """Literals in the given files that no manifest value accounts for."""
    project = project.resolve()
    values = [_norm(e.value) for e in record.manifest.values() if e.value]
    skip = {(project / t.strip().lstrip("./")).resolve() for t in record.token_files}
    work_paths = [p.strip().lstrip("./").lower() for e in record.manifest.values() if e.kind == "work" for p in e.paths]
    skip |= {(project / p).resolve() for p in work_paths}

    def traced(literal: str, kind: str) -> bool:
        lit = _norm(literal)
        if lit in TRIVIAL:
            return True
        if kind == "media":
            return any(wp and wp in lit for wp in work_paths) or any(lit in v or v.endswith(lit) for v in values)
        if kind == "font":
            return any(lit == v or lit in v for v in values)
        return lit in values

    findings: list[Finding] = []
    for path in _files(project, patterns, skip):
        web = path.suffix.lower() in WEB
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = path.relative_to(project).as_posix()
        for number, line in enumerate(lines, 1):
            hits: list[tuple[str, str]] = [(m.group(0), "color") for m in COLOR.finditer(line)]
            hits += [(m.group(0), "media") for m in MEDIA.finditer(line)]
            if web:
                hits += [(m.group(0), "length") for m in LENGTH.finditer(line)]
                hits += [(m.group(0), "duration") for m in DURATION.finditer(line)]
                hits += [((m.group(1) or m.group(2)).strip(), "font") for m in FONT.finditer(line)]
            for literal, kind in hits:
                if kind == "font" and literal.startswith(("var(", "theme(")):
                    continue
                if not traced(literal, kind):
                    findings.append(Finding(rel, number, literal, kind))
    return findings


def touched(record: Record, orders=None) -> list[str]:
    """The file patterns of the given orders, or of every order."""
    return [t for o in (orders if orders is not None else record.orders) for t in o.touches]
