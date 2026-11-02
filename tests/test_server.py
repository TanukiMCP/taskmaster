"""The whole procedure through a real MCP client, in a temporary project folder."""

import json

import anyio
import pytest
from mcp import Client

import flow
from coherence import server


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project", tmp_path)
    return tmp_path


def text(result):
    assert not result.is_error, result
    return "\n".join(c.text for c in result.content if c.type == "text")


def args(answer):
    return {k: v for k, v in answer.model_dump(exclude_none=True).items() if v not in ("", [], False)}


async def scenario(project):
    async with Client(server.mcp) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert names == {"begin", "next", "settle", "walk", "decide", "compile", "complete", "gap", "revise", "verify", "read"}

        async def call(name, arguments=None):
            return text(await client.call_tool(name, arguments or {}))

        assert (await call("next")).startswith("Not done: No record")
        started = await call("begin", {"request": flow.REQUEST, "mode": "idea", "questions": json.dumps(flow.QUESTIONS)})
        assert "# Procedure" in started and "# Point [root] (root, open)" in started
        assert "Build me a puzzle game" in started and "[q1] How do players progress?" in started
        assert (await call("begin", {"request": "again", "mode": "idea"})).startswith("Not done: This project already has a record")

        wrong = await call("settle", {"point": "root", **args(flow.root().model_copy(update={"average": ""}))})
        assert wrong.startswith("Not done: Answer every question: average is empty")
        out = await call("settle", {"point": "root", **args(flow.root())})
        assert out.startswith("Settled 'root' (v1). Opened: first-board.") and "# Point [q1]" in out
        out = await call("settle", {"point": "q1", **args(flow.question())})
        assert "# Point [first-board] (situation, open)" in out and "## The root" in out
        out = await call("settle", {"point": "first-board", **args(flow.situation())})
        assert "# Point [ui-kit] (family, open)" in out and "## Settled beside it" not in out
        out = await call("settle", {"point": "ui-kit", **args(flow.family())})
        assert "# Point [board] (job, open)" in out and "[ui-kit] family: Kenney" in out
        out = await call("settle", {"point": "board", "aspect": "layout", **args(flow.job())})
        assert "# Walk the record" in out and "[first-board]" in out

        out = await call("walk", {"experience": flow.EXPERIENCE, "construction": flow.CONSTRUCTION})
        assert "# Review" in out and "## What it will be like" in out and "## The calls most likely to be wrong" in out
        shape = (project / ".coherence" / "shape.md").read_text()
        assert "## What this is for" in shape and "Kenney" in shape and "Long enough for a new player" in shape

        out = await call("decide", {"approve": True})
        assert "# Compile the orders" in out and "[board] job" in out
        out = await call("compile", {"orders": json.dumps([o.model_dump() for o in flow.ORDERS]), "token_files": ["styles/tokens.css"]})
        assert "# Order [foundations]" in out and "Token files" in out

        (project / "styles").mkdir()
        (project / "styles" / "tokens.css").write_text(":root { --ink: #1d2b53; }\n")
        out = await call("complete", {"order": "foundations", "summary": "tokens written", "evidence": "the file loads"})
        assert "# Order [board]" in out and "## It must not" in out and "## Guidance: design/layout" in out

        (project / "src").mkdir()
        (project / "src" / "board.js").write_text("rule.style.color = '#ff0000';\n")
        deferred = [{"id": "timing.reveal", "value": "240ms", "observation": "a new player read each result first"}]
        refused = await call("complete", {"order": "board", "summary": "board", "evidence": "shown", "deferred": deferred})
        assert refused.startswith("Not done: These values") and "src/board.js:1: #ff0000 (color)" in refused
        (project / "src" / "board.js").write_text("rule.style.color = 'var(--ink)';\n")
        out = await call("complete", {"order": "board", "summary": "board", "evidence": "shown", "deferred": deferred})
        assert "# Verify" in out and "scan of every file the orders touched is clean" in out

        out = await call("verify", {"walk": "[first-board] A new player read the rule and solved it.", "evidence": "ran it",
                                    "review": "A fresh agent compared it with the shape and found the pause readable"})
        assert out.startswith("Verified.") and "# Done" in out
        assert "## Built and checked" in (project / ".coherence" / "shape.md").read_text()

        assert (await call("read", {"ref": "design/color"})).startswith("7. Construct the color palette")
        steps = [json.loads(line) for line in (project / ".coherence" / "steps.jsonl").read_text().splitlines()]
        settled = [s for s in steps if s["tool"] == "settle" and s["ok"]]
        assert settled[0]["args"]["point"] == "root" and "# Point [root]" in settled[0]["context"]
        assert any(not s["ok"] for s in steps)
        assert any(r.name == "cohere" for r in (await client.list_prompts()).prompts)


def test_the_whole_procedure_over_mcp(project):
    anyio.run(scenario, project)
