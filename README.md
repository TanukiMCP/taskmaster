# Taskmaster

Taskmaster is an MCP server that runs design work as standard operating procedures. A request like "redesign the landing page" or "build an app that does X" becomes an end goal plus an ordered list of entries from a scope and situation matrix. For each entry, the agent writes a plan against that situation's SOP before any work starts, then Taskmaster hands it one SOP step at a time, with the design procedure's text for that step, until the goal is reached.

```
result = verify( behavior( layout( color( imagery( typography( research( components( order( content( question ) ) ) ) ) ) ) ) ) )
```

The agent keeps no tasklist of its own. Taskmaster holds the plan and the sequence, gives the full procedure text when each step is reached, and resumes exactly where the work stopped after an interruption.

## How it works

- **The procedure** ([design/process.txt](design/process.txt)) is the fixed rulebook for designing intentionally: one chain of steps 0–10, with the methods, rules, and order of the work. It is the same for every assignment.
- **The matrix** ([design/matrix.txt](design/matrix.txt)) is the selector. Every request maps to one or more entries, each a situation and a scope.
- **Situation SOPs** ([design/prompts/situations](design/prompts/situations)) set the working path through the procedure for each kind of job: a plain-language brief, then numbered SOP steps that each name the procedure step they work in.
  - **Create** builds from a brief.
  - **Extend** adds to an existing product and carries its design.
  - **Redesign** replaces what exists, using it as evidence.
  - **Fix** keeps what exists and repairs a specific problem at its cause.
  - **Review** inspects and recommends without changing anything.
- **Scope sheets** ([design/prompts/scopes](design/prompts/scopes)) set how far the work reaches. The scopes form a ladder:
  - element → component → section → page → flow → product
  - shared-styles cuts across every rung.
  
  Whether a unit should exist is decided by its parent, so an entry that finds its unit shouldn't exist escalates one rung.
- **Step 3** finds components rather than inventing them: name the job, look at how real products do it, then adapt the component they use.

## Tools

| Tool | Use |
|---|---|
| `get_matrix` | Read the selector before choosing entries |
| `start_session` | Request, end goal, and ordered entries (`situation`, `scope`, `goal`); returns a `session_id` and the first SOP |
| `submit_plan` | Write the plan, one item per SOP step, before any work; call again to revise it |
| `complete_step` | Finish an SOP step with a short handoff; a trace step also takes `responsible_step` |
| `report_verification` | Finish a verify step: `done` or the responsible procedure step number |
| `escalate` | End the entry and start the right one when the decision belongs to a parent scope or another situation |
| `get_process_step` | Read one procedure step in full |
| `current_step` | Re-issue the current step after an interruption |
| `add_entries` | Add entries, such as a Fix after a Review |
| `get_status` | Entries, plan, position, and recorded results; with no `session_id`, recent sessions |
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

The same server also runs as a Netlify Function (`netlify/`) for use as a Claude custom connector at `/mcp/<token>`, with the token set in `TASKMASTER_TOKEN`.

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
npm test
```

## License

MIT
