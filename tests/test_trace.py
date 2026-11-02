from pathlib import Path

from coherence import record as rec
from coherence.record import Entry
from coherence.trace import scan


def make(tmp_path: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def record_with(entries, token_files=()):
    r = rec.begin("make a page", "idea")
    for e in entries:
        r.manifest[e.id] = e
    r.token_files = list(token_files)
    return r


def test_literals_outside_the_manifest_are_found(tmp_path):
    project = make(tmp_path, {
        "src/app.css": ".title { color: #ff0000; margin: 12px; transition: opacity 180ms; font-family: Comic Sans MS; }\n",
        "src/app.js": "img.src = 'images/hero.png'; el.style.color = 'rgb(1, 2, 3)';\n",
    })
    found = {(f.path, f.literal, f.kind) for f in scan(record_with([]), project, ["src/**/*"])}
    assert ("src/app.css", "#ff0000", "color") in found
    assert ("src/app.css", "12px", "length") in found
    assert ("src/app.css", "180ms", "duration") in found
    assert ("src/app.css", "Comic Sans MS", "font") in found
    assert ("src/app.js", "images/hero.png", "media") in found
    assert ("src/app.js", "rgb(1, 2, 3)", "color") in found


def test_manifest_values_token_files_and_reused_work_are_traced(tmp_path):
    project = make(tmp_path, {
        "styles/tokens.css": ":root { --ink: #1d2b53; --gap: 24px; }\n",
        "src/app.css": ".title { color: var(--ink); margin: 0; padding: 24px; }\n",
        "src/app.js": "load('assets/kenney/panel.png'); font = 'Inter';\n",
        "assets/kenney/sheet.css": ".panel { color: #abcdef; }\n",
    })
    entries = [Entry(id="space.gap", kind="token", value="24px"),
               Entry(id="kit", kind="work", value="https://kenney.nl/assets/ui-pack", paths=["assets/kenney"])]
    assert scan(record_with(entries, ["styles/tokens.css"]), project, ["**/*"]) == []


def test_only_the_touched_files_are_scanned(tmp_path):
    project = make(tmp_path, {"a.css": "x { color: #123456; }", "b.css": "y { color: #654321; }"})
    assert [f.path for f in scan(record_with([]), project, ["a.css"])] == ["a.css"]
