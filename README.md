# Taskmaster

Taskmaster is an MCP server that runs design work as an algorithm. A request like "redesign the landing page" or "build an app that does X" becomes an end goal plus an ordered plan of prompts from a scope and situation matrix. Taskmaster then hands the agent one procedure step at a time until the goal is reached.

```
result = verify( behavior( layout( color( imagery( typography( research( components( order( content( question ) ) ) ) ) ) ) ) ) )
```

The agent keeps no tasklist of its own. Taskmaster holds the sequence, gives the full text of each step when it is reached, and resumes exactly where the work stopped after an interruption.

## How it works

- **The matrix** ([design/matrix.txt](design/matrix.txt)) has five situations and five scopes.
  - Situations: create, extend, improve, fix, review.
  - Scopes: component, page, flow, shared-styles, product.
  - Every request maps to one or more entries.
- **The procedure** ([design/process.txt](design/process.txt)) is one fixed chain of steps 0–10. Every entry runs the whole chain. At each step it either decides or keeps the existing decision.
- **Situation prompts** ([design/prompts/situations](design/prompts/situations)) set which steps decide or keep, and where the run starts. Improve, Fix and Review inspect the existing work first.
- **Scope prompts** ([design/prompts/scopes](design/prompts/scopes)) set how far each step reaches.
- **Step 3** sources components rather than inventing them. It inventories sections, inventories the components each needs and the job of each, researches relevant examples, then adapts the established component that fits.
- **Step 10** returns `done`, or the number of the step that caused a problem. Taskmaster then reruns from that step forward.

## Tools

| Tool | Use |
|---|---|
| `get_matrix` | Read the selector before choosing entries |
| `start_session` | Request, end goal, and ordered entries (`situation`, `scope`, `goal`); returns a `session_id` |
| `complete_step` | Finish steps 0–9 with a short handoff; returns the next step |
| `report_verification` | Finish step 10: `done` or the responsible step number |
| `current_step` | Re-issue the current step after an interruption |
| `add_entries` | Add entries to the plan, such as a Fix after a Review |
| `get_status` | The plan, position, and recorded results; with no `session_id`, recent sessions |
| `end_session` | Close a session |

Every tool after `start_session` takes the `session_id`, so several conversations can run their own sessions at once against the same server.

The server also exposes the design files as resources under `taskmaster://design/...`, and a `design` prompt.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+.

```bash
uv sync
uv run taskmaster
```

That starts the server over stdio. For HTTP, use `uv run taskmaster --transport streamable-http --port 8080`; the endpoint is `/mcp`.

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

Sessions are saved in `.taskmaster/` in the folder the server starts from. Set `TASKMASTER_STATE_DIR` to change that, or `TASKMASTER_DESIGN_DIR` to use a different copy of the design files.

## Test

```bash
uv run pytest
```

## License

MIT
