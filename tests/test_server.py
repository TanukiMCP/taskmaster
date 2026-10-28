"""End-to-end checks through a real MCP client session."""

import functools
import http.server
import json
import re
import shutil
import subprocess
import sys
import threading

import anyio
import pytest
from mcp import Client

from taskmaster import server
from taskmaster.store import Store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_store", Store(tmp_path))


def text(result):
    assert not result.is_error, result
    return "\n".join(c.text for c in result.content if c.type == "text")


def session_id(started: str) -> str:
    return re.match(r"Session (\w+) started", started).group(1)


async def scenario():
    async with Client(server.mcp) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert {"get_matrix", "start_session", "submit_plan", "complete_step", "report_verification", "escalate", "get_process_step"} <= tools

        call = lambda name, args: client.call_tool(name, args)  # noqa: E731

        assert "Prompt selector" in text(await call("get_matrix", {}))

        started = text(await call("start_session", {
            "request": "The 'What people say' section on the food page shouldn't exist",
            "end_goal": "Claims appear with their ingredients and the page has no separate claims section",
            "entries": [{"situation": "fix", "scope": "page", "goal": "Remove the claims section and move claims to their ingredients"}],
        }))
        sid = session_id(started)
        assert "Working method" in started and "## Situation SOP: Fix" in started and "## Write your plan" in started

        # A second conversation's session runs alongside without disturbing the first.
        other = session_id(text(await call("start_session", {
            "request": "Audit the landing page",
            "end_goal": "Findings ordered by effect",
            "entries": [{"situation": "review", "scope": "page", "goal": "Findings"}],
        })))
        assert other != sid

        refused = text(await call("start_session", {
            "request": "Redesign the reviews band",
            "end_goal": "g",
            "entries": [{"situation": "redesign", "scope": "section", "goal": "g"}],
            "constraints": [{"constraint": "Keep the existing identity", "quote": "existing identity retained"}],
        }))
        assert refused.startswith("Not done:") and "no quote from the request" in refused

        early = text(await call("complete_step", {"session_id": sid, "handoff": "too early", "results": [{"statement": "x", "based_on": ["request"]}]}))
        assert early.startswith("Not done: Write the plan first")

        plan = [
            "State that the claims section duplicates content that belongs to ingredients.",
            "Reproduce on the food page at three widths and capture the section.",
            "Trace to step 2: the section survived ranking although step 1 placed claims with ingredients.",
            "Remove the section and attach each claim to its ingredient row.",
            "Carry into components, layout, and behavior only where the claim rows change them.",
            "Verify the page reads in order without the section.",
        ]
        accepted = text(await call("submit_plan", {"session_id": sid, "plan": json.dumps(plan)}))
        assert "# Fix step 1 of 6: State the problem" in accepted and plan[0] in accepted
        assert "The user's words: The 'What people say' section" in accepted
        assert "Constraints: none quoted from the user" in accepted

        def step(handoff, statement, based_on, **extra):
            return call("complete_step", {"session_id": sid, "handoff": handoff, "results": [{"statement": statement, "based_on": based_on}], **extra})

        uncited = text(await call("complete_step", {"session_id": sid, "handoff": "Problem stated.", "results": [{"statement": "The section duplicates claims"}]}))
        assert "cites nothing" in uncited
        await step("Problem stated.", "The claims section duplicates content that belongs to ingredients", ["request"])
        trace_step = text(await step("Reproduced and captured.", "The section shows at all three widths", ["1.1"]))
        assert "Fix step 3 of 6: Trace the cause (trace)" in trace_step
        assert "- 2.1: The section shows at all three widths (based on 1.1)" in trace_step

        missing_k = text(await step("Traced.", "Step 2 kept the section", ["2.1"]))
        assert "responsible_step" in missing_k

        correct = text(await step("Cause is step 2.", "Step 2 kept a region step 1 had placed with ingredients", ["2.1"], responsible_step=2))
        assert "Fix step 4 of 6: Correct the cause" in correct
        assert "## Procedure step 2: Order the information (verbatim)" in correct
        assert "should exist at all" in correct
        assert "Content and order:" in correct and "## Working rules" in correct

        assert "Write your plan" in text(await call("current_step", {"session_id": other}))
        assert "Correct the cause" in text(await call("current_step", {"session_id": sid}))

        full = text(await call("get_process_step", {"step": 8}))
        assert full.startswith("8. Construct layout")

        status = text(await call("get_status", {"session_id": sid}))
        assert "▶ 4. Correct the cause" in status and "Cause is step 2." in status
        listing = text(await call("get_status", {}))
        assert sid in listing and other in listing

        escalated = text(await call("escalate", {"session_id": sid, "reason": "The whole page structure is wrong", "to_situation": "redesign"}))
        assert "Redesign × Page or view" in escalated and "Write your plan" in escalated

        missing = text(await call("current_step", {"session_id": "nope"}))
        assert missing.startswith("Not done: No session")

        resources = await client.list_resources()
        assert any(str(r.uri) == "taskmaster://design/process" for r in resources.resources)
        prompts = await client.list_prompts()
        assert any(p.name == "design" for p in prompts.prompts)


def test_full_scenario_over_mcp():
    anyio.run(scenario)


needs_browser = pytest.mark.skipif(
    shutil.which("node") is None or subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode != 0,
    reason="needs Node.js and Playwright",
)


@pytest.fixture
def page_server(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text('<!doctype html><body><section id="s"><h1>Sources</h1><p>Copied from a review site.</p></section>')
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path / "site"))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()


async def ready_scenario(url):
    async with Client(server.mcp) as client:
        call = lambda name, args: client.call_tool(name, args)  # noqa: E731
        sid = session_id(text(await call("start_session", {
            "request": "The sources heading wraps on phones",
            "end_goal": "The heading fits at 390",
            "entries": [{"situation": "fix", "scope": "element", "goal": "Heading fits"}],
        })))
        await call("submit_plan", {"session_id": sid, "plan": ["a", "b", "c", "d", "e", "f"]})
        previous = "request"
        for n in range(1, 6):
            args = {"session_id": sid, "handoff": f"step {n}", "results": [{"statement": f"result {n}", "based_on": [previous]}]}
            if n == 3:
                args["responsible_step"] = 5
            assert not text(await call("complete_step", args)).startswith("Not done")
            previous = f"{n}.1"
        early = text(await call("report_verification", {"session_id": sid, "outcome": "ready"}))
        assert "Capture the result first" in early
        before = text(await call("capture", {"session_id": sid, "kind": "before", "url": url, "label": "before", "selector": "#s"}))
        assert "Captured before 'before'" in before and "scrolls sideways" not in before
        await call("capture", {"session_id": sid, "kind": "result", "url": url, "label": "after", "selector": "#s"})
        ready = text(await call("report_verification", {"session_id": sid, "outcome": "ready", "findings": "heading is one line at 390"}))
        assert "Waiting for the user's verdict" in ready and "Side-by-side page:" in ready
        blocked = text(await call("report_verification", {"session_id": sid, "outcome": "ready"}))
        assert "ready for the user's review" in blocked
        return sid


@needs_browser
def test_ready_needs_captures_and_the_user_decides(page_server, monkeypatch, capsys):
    sid = anyio.run(ready_scenario, page_server)
    side = list((server.store().root / "captures" / sid).glob("*side-by-side.html"))
    assert side and "<img" in side[0].read_text()
    monkeypatch.setattr(sys, "argv", ["taskmaster", "verdict", sid, "done"])
    server.main()
    assert "Marked done" in capsys.readouterr().out
    assert server.store().load(sid).status == "complete"
