# Taskmaster

Taskmaster is an MCP server that helps an AI agent do a task well. It breaks the work into steps where each step builds on real results from the steps before it, and it tracks which results are still good.

It runs one method, [library/method.txt](library/method.txt):

- **Work out the steps the task needs.** Each step says what it needs from earlier steps and what concrete result it produces.
- **A step can't be finished until what it needs exists and is up to date.**
- **When a result turns out wrong, revise it.** Everything built on it is flagged to redo or confirm; nothing else is touched.
- **Every step checks back against why the work matters**: the value the session started with.
- **The work ends with the result delivered**, what was actually checked, and what is still limited.

```
start → compose → next → (do the work) → record → next → … → finish
                              ↑
                 revise when a result turns out wrong
```

The agent keeps no tasklist of its own. Taskmaster holds the steps and their results, and after an interruption it gives back the current step with everything it builds on.

## When it helps

In a side-by-side test (October 2026), two agents got the same task: develop two game concepts for a three-person team. One was given only [library/method.txt](library/method.txt); the other used this server. Both came up with nearly the same steps, and the results were comparable. The method-only run cost about half as much. So the method does the thinking. The server's job is what a prompt can't do:

- **Keep the results** when the conversation is interrupted, condensed, or picked up later (`next`).
- **Flag exactly what to recheck when a result changes**, and record why each flagged step still holds (`revise`). The test agent found this the most useful part.
- **Hand out long procedures one step at a time**, as the design library does.
- **Leave a record you can inspect.**

For a short task that fits in one sitting, giving the agent `library/method.txt` as its instructions is enough.

## Tools

| Tool | Use |
|---|---|
| `start` | The request, the result it asks for, the value that makes that result worth having, and the starting information. Returns a `session_id` and the method. |
| `compose` | The steps (operations): an id, what each needs, what it does, and what it produces, each listed after what it needs. Call again with a `reason` to change them; unchanged steps keep their results. |
| `next` | The step to work on now, with the results it builds on and its guide. Without a `session_id`, lists recent sessions. |
| `record` | A step's actual output, how it still serves the value, and the assumptions it rests on. Refused until everything it needs is up to date. For a flagged step, `still_holds` confirms the earlier output instead. |
| `revise` | Reopen a step that turned out wrong; everything built on it is flagged. Or change the value or result itself, explicitly. |
| `finish` | What was delivered, what was checked, and what is still limited. |
| `library` | Read the method and the ready-made recipes. |

Every tool after `start` takes the `session_id`, so several conversations can run their own sessions against the same server at once.

## Ready-made recipes: design

The library includes a full recipe set for product and interface design, in [library/design](library/design):

- [process.txt](library/design/process.txt) is the design procedure: steps 0–10, from the question people arrive with through verification.
- [matrix.txt](library/design/matrix.txt) picks the situation (create, extend, redesign, fix, review) and the scope (element, component, section, page, flow, product, or shared styles).
- [situations/](library/design/situations) holds each situation as a ready-made set of steps, with what each step needs and produces.
- [scopes/](library/design/scopes) sets how far the work reaches.

For design work, the agent reads `library('design')` to choose, then `library('design/redesign/page')` (for example) for a set of steps to adopt with `compose`. Each step then arrives with its instructions, the procedure step in full, and the scope's limits.

Other work, such as game ideas, research, or writing, has the agent compose its own steps.

## Layout

- `library/` holds the text: the method and the design recipes. Both servers read these files; edit them here and nowhere else.
- `taskmaster/` is the Python server.
- `netlify/` is the same server as a Netlify Function, for use as a Claude custom connector. It mirrors the Python server, and the tests run against both.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```bash
uv sync
uv run taskmaster
```

That starts the server over stdio. For HTTP, use `uv run taskmaster --transport streamable-http --port 8080`; the endpoint is `/mcp`.

On Netlify the server is served at `/mcp/<token>`, with the token set in `TASKMASTER_TOKEN`.

### Connect to Claude Code

Add this to a project's `.mcp.json`, with the path to this repository:

```json
{
  "mcpServers": {
    "taskmaster": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/taskmaster", "taskmaster"]
    }
  }
}
```

Sessions are saved in `.taskmaster/` in the folder the server starts from. Set `TASKMASTER_STATE_DIR` to change that, or `TASKMASTER_LIBRARY_DIR` to use a different copy of the library. Sessions from version 2 can't be continued; start a new one.

## Test

```bash
uv run pytest
npm test
```

## License

MIT
