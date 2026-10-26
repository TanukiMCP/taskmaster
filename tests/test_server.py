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
        assert {"get_matrix", "start_session", "complete_step", "report_verification", "current_step"} <= tools

        matrix = text(await client.call_tool("get_matrix", {}))
        assert "Prompt selector" in matrix

        started = text(await client.call_tool("start_session", {
            "request": "Use taskmaster to redesign the landing page",
            "end_goal": "Visitors can tell what the product does and start a trial",
            "entries": [{"situation": "improve", "scope": "page", "goal": "Landing page answers the visitor's question"}],
        }))
        assert "Working method" in started and "# Step 0: State the question" in started
        sid = session_id(started)

        # A second conversation's session runs alongside without disturbing the first.
        other = session_id(text(await client.call_tool("start_session", {
            "request": "Fix the modal",
            "end_goal": "Modal fits on phones",
            "entries": [{"situation": "fix", "scope": "component", "goal": "No overflow"}],
        })))
        assert other != sid

        diagnosis = text(await client.call_tool("complete_step", {"session_id": sid, "handoff": "Question stated."}))
        assert "Diagnosis (Improve)" in diagnosis

        rerun = text(await client.call_tool("report_verification", {"session_id": sid, "outcome": "3", "findings": "Hero text instead of components"}))
        assert "# Step 3: Name the jobs and adapt components from real products" in rerun

        assert "# Step 0" in text(await client.call_tool("current_step", {"session_id": other}))
        assert "Step 3" in text(await client.call_tool("current_step", {"session_id": sid}))

        # Arrays sent as JSON strings are accepted.
        added = text(await client.call_tool("add_entries", {
            "session_id": sid,
            "entries": json.dumps([{"situation": "extend", "scope": "page", "goal": "Pricing page"}]),
        }))
        assert "Extend × Page or view" in added

        status = text(await client.call_tool("get_status", {"session_id": sid}))
        assert "Hero text instead of components" in status

        listing = text(await client.call_tool("get_status", {}))
        assert sid in listing and other in listing

        wrong = text(await client.call_tool("report_verification", {"session_id": sid, "outcome": "done"}))
        assert wrong.startswith("Not done:")
        missing = text(await client.call_tool("current_step", {"session_id": "nope"}))
        assert missing.startswith("Not done: No session")

        resources = await client.list_resources()
        assert any(str(r.uri) == "taskmaster://design/process" for r in resources.resources)
        prompts = await client.list_prompts()
        assert any(p.name == "design" for p in prompts.prompts)


def test_full_scenario_over_mcp():
    anyio.run(scenario)
