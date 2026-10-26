"""End-to-end checks through a real MCP client session."""

import json
import re

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

        early = text(await call("complete_step", {"session_id": sid, "handoff": "too early"}))
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

        await call("complete_step", {"session_id": sid, "handoff": "Problem stated."})
        trace_step = text(await call("complete_step", {"session_id": sid, "handoff": "Reproduced and captured."}))
        assert "Fix step 3 of 6: Trace the cause (trace)" in trace_step

        missing_k = text(await call("complete_step", {"session_id": sid, "handoff": "Traced."}))
        assert "responsible_step" in missing_k

        correct = text(await call("complete_step", {"session_id": sid, "handoff": "Cause is step 2.", "responsible_step": 2}))
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
