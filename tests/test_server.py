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
    return tmp_path


def text(result):
    assert not result.is_error, result
    return "\n".join(c.text for c in result.content if c.type == "text")


def session_id(started: str) -> str:
    return re.match(r"Session (\w+) started", started).group(1)


async def scenario(state_dir):
    async with Client(server.mcp) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"start", "compose", "next", "record", "revise", "finish", "library"}

        async def call(name, args):
            return text(await client.call_tool(name, args))

        assert "Prompt selector" in await call("library", {"ref": "design"})
        assert (await call("library", {"ref": "nowhere"})).startswith("Not done: 'nowhere' names nothing")

        started = await call("start", {
            "request": "The 'What people say' section on the food page shouldn't exist",
            "result": "The food page with each claim beside its ingredient and no separate claims section",
            "value": "Shoppers judge each ingredient with its evidence in one place",
            "starting": "Existing food page; identity is not open",
        })
        sid = session_id(started)
        assert "Dependency-ordered cognitive composition" in started and "# Now: derive the composition" in started
        assert "No operations yet" in await call("next", {"session_id": sid})

        # A second conversation's session runs alongside without disturbing the first.
        other = session_id(await call("start", {"request": "Ideas for a puzzle game", "result": "One concept", "value": "Players feel clever"}))
        assert other != sid

        entry = await call("library", {"ref": "design/fix/page"})
        ready_made = json.loads(entry[entry.index("[\n"):])
        for item in ready_made:
            item["does"] = f"{item['id']} for the claims section"
        unwritten = await call("compose", {"session_id": sid, "operations": [{"id": "problem", "produces": "p"}]})
        assert "needs does" in unwritten

        composed = await call("compose", {"session_id": sid, "operations": json.dumps(ready_made)})
        assert "Composition recorded: 6 operations." in composed
        assert "▶ problem (open, next)" in composed and "○ verify ← problem, reproduce, carry (open)" in composed
        assert "# Next: problem (open)" in composed and "## Guide: design/fix/page#problem" in composed
        assert "Built on it: 5 later operations" in composed

        early = await call("record", {"session_id": sid, "operation": "trace", "output": "too early", "preserves": "p"})
        assert early.startswith("Not done: 'trace' can't be recorded yet") and "Work on 'problem' first" in early

        await call("record", {"session_id": sid, "operation": "problem", "output": "Claims sit in their own band, away from ingredients.", "preserves": "names the judging task"})
        trace = await call("record", {
            "session_id": sid, "operation": "reproduce", "output": "Captured at three widths.", "preserves": "same task",
            "assumptions": json.dumps(["the band is not reused elsewhere"]),
        })
        assert "# Next: trace (open)" in trace
        assert "### problem (v1)\nClaims sit in their own band" in trace
        assert "Assumptions: the band is not reused elsewhere" in trace
        assert "## Guide: design/fix/page#trace" in trace and "### Procedure step 10: Verify and correct (verbatim)" in trace

        correct = await call("record", {"session_id": sid, "operation": "trace", "output": "Cause in procedure step 2: the band survived ranking.", "preserves": "p"})
        assert "# Next: correct (open)" in correct and "Works in procedure step: the step the trace named" in correct
        assert "Cause in procedure step 2" in correct

        for op_id in ("correct", "carry", "verify"):
            await call("record", {"session_id": sid, "operation": op_id, "output": f"{op_id} done", "preserves": "p"})
        assert "All 6 operations are current" in await call("next", {"session_id": sid})

        revised = await call("revise", {"session_id": sid, "operation": "reproduce", "reason": "the band is reused on the recipe page"})
        assert "Reopened 'reproduce'. Now stale: trace, correct, carry, verify." in revised
        assert "# Next: reproduce (revised)" in revised and "Revised: the band is reused" in revised

        await call("record", {"session_id": sid, "operation": "reproduce", "output": "Captured on both pages.", "preserves": "p"})
        stale = await call("next", {"session_id": sid})
        assert "# Next: trace (stale)" in stale and "'reproduce' changed (v1 → v2)" in stale and "still_holds" in stale
        confirmed = await call("record", {"session_id": sid, "operation": "trace", "still_holds": "the cause is the same on both pages"})
        assert confirmed.startswith("Confirmed 'trace' v1 still holds.") and "# Next: verify (stale)" in confirmed

        unfinished = await call("finish", {"session_id": sid, "delivered": "the page", "evidence": "walked it"})
        assert "'verify' is not current" in unfinished
        await call("record", {"session_id": sid, "operation": "verify", "output": "checked both pages", "preserves": "p"})
        finished = await call("finish", {"session_id": sid, "delivered": "The food page at /food", "evidence": "Walked both pages at three widths"})
        assert finished.startswith(f"Session {sid} is finished.")

        listing = await call("next", {})
        assert sid in listing and other in listing and "[finished]" in listing
        assert (await call("next", {"session_id": "nope"})).startswith("Not done: No session")

        (state_dir / "sessions" / "old.json").write_text(json.dumps({"id": "old", "request": "r", "end_goal": "g", "entries": []}))
        assert "earlier version of Taskmaster" in await call("next", {"session_id": "old"})

        resources = {str(r.uri) for r in (await client.list_resources()).resources}
        assert {"taskmaster://method", "taskmaster://design/process", "taskmaster://design/matrix"} <= resources
        assert any(p.name == "run" for p in (await client.list_prompts()).prompts)


def test_full_scenario_over_mcp(isolated_store):
    anyio.run(scenario, isolated_store)
