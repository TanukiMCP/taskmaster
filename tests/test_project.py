"""Which folder a call works in: the server's own project, or the one each call names under --any-project."""

import anyio
import pytest
from mcp import Client

import flow
from coherence import server


def text(result):
    assert not result.is_error, result
    return "\n".join(c.text for c in result.content if c.type == "text")


async def calls(*steps):
    async with Client(server.mcp) as client:
        return [text(await client.call_tool(name, arguments)) for name, arguments in steps]


@pytest.fixture
def fixed(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "_project", tmp_path)
    monkeypatch.setattr(server, "_any_project", False)
    return tmp_path


@pytest.fixture
def any_project(monkeypatch):
    monkeypatch.setattr(server, "_project", None)
    monkeypatch.setattr(server, "_any_project", True)


def test_every_step_takes_a_project_and_read_does_not():
    async def schemas():
        async with Client(server.mcp) as client:
            return {t.name: t.input_schema["properties"] for t in (await client.list_tools()).tools}

    props = anyio.run(schemas)
    assert all("project" in p for name, p in props.items() if name != "read")
    assert "project" not in props["read"] and "orders" in props["compile"]


def test_a_fixed_server_refuses_another_folder(fixed, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    same, elsewhere = anyio.run(calls, ("begin", {"request": flow.REQUEST, "mode": "idea", "project": str(fixed)}),
                                ("next", {"project": str(other)}))
    assert "# Point [root]" in same and not same.startswith("Project:")
    assert elsewhere.startswith(f"Not done: This server works in {fixed}")
    assert not (other / ".coherence").exists()


def test_any_project_needs_an_absolute_folder_on_every_call(any_project, tmp_path):
    folder = tmp_path / "bakery"
    missing, relative, existing, started, resumed = anyio.run(
        calls,
        ("next", {}),
        ("next", {"project": "bakery"}),
        ("begin", {"request": flow.REQUEST, "mode": "existing", "project": str(folder)}),
        ("begin", {"request": flow.REQUEST, "mode": "idea", "project": str(folder)}),
        ("next", {"project": str(folder)}),
    )
    assert missing.startswith("Not done: Name the project") and "ask them" in missing
    assert relative.startswith("Not done: project must be an absolute path")
    assert existing.startswith("Not done: There is no folder at")
    assert started.startswith(f"Project: {folder.resolve()}") and "# Point [root]" in started
    assert (folder / ".coherence" / "record.json").is_file()
    assert resumed.startswith(f"Project: {folder.resolve()}") and "# Point [root]" in resumed


def test_two_projects_on_one_server_keep_their_own_records(any_project, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    anyio.run(calls, ("begin", {"request": flow.REQUEST, "mode": "idea", "project": str(a)}),
              ("begin", {"request": "Make a site for my bike co-op", "mode": "idea", "project": str(b)}))
    assert "puzzle game" in (a / ".coherence" / "record.json").read_text()
    assert "bike co-op" in (b / ".coherence" / "record.json").read_text()
