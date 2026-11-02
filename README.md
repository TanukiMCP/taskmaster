# CoherenceMCP

CoherenceMCP is an MCP server that keeps an agent from building the average version of what you asked for. When an agent isn't told a value, it fills in the most probable answer from its training, which is generic. CoherenceMCP gives the agent a fixed procedure that settles every value of the project from a real source, keeps the result in a record the agent can't drift from, asks you for one approval at the foundation, and checks at the end that the built product contains nothing the record didn't settle.

Drop it into an existing project that needs to be made coherent, or start from an idea: "build me an app that does…", "a game that plays like…", "a website for my business that…".

## How it works

The server runs one state machine for every project:

1. **derive**: the agent answers the open points of the project, starting with what it's for and for whom, using the same seven questions every time: what the point serves, what happens to a person there, what the average version would do, what this project does instead and what that rules out, who has already done it well (reuse before custom), what would show it's wrong, and what it leaves open. Every answer needs a permitted source: your words, the conversation, research, existing work, settled points, or an observation.
2. **walk**: the agent walks the experience and the construction to find anything still undetermined. Gaps become new open points.
3. **review**: the server writes the shape to `.coherence/shape.md`. You approve it or deny it with a reason; a denial reopens only what it touches.
4. **compile**: after approval, the record becomes build orders, each carrying exactly the context it needs.
5. **build**: orders are carried out one at a time under a closed world. The product may only use what the manifest pins: exact references to existing work, tokens, content, and rules.
6. **verify**: the server scans the project for values that don't trace back to the record and checks that every settled point was built.

The server refuses calls out of order or in the wrong form and says why. `next` always returns the current step.

[docs/shape.md](docs/shape.md) is the full shape of the tool. [library/procedure.txt](library/procedure.txt) is what the agent follows, [library/method.txt](library/method.txt) is the working method underneath it, and [library/design/process.txt](library/design/process.txt) supplies design guidance for points about content, layout, type, color, imagery, and behavior.

## Tools

| Tool | Use |
|---|---|
| `begin` | Your request word for word, `idea` or `existing`, your questions, and any conversation context |
| `next` | The current step with the context it needs |
| `settle` | Answer an open point |
| `walk` | Report the experience and construction walks, and any gaps |
| `decide` | Record your approval or denial of the shape |
| `compile` | Turn the approved record into build orders |
| `complete` | Finish a build order |
| `gap` | Report something the record doesn't settle, instead of filling it |
| `revise` | Reopen a point that turned out wrong; what depends on it reopens too |
| `verify` | Check the built product against the record |
| `read` | Read the procedure, the method, or the design guidance |

The record lives in `.coherence/` in the project. The server also writes every step it hands out and every answer it accepts to `.coherence/steps.jsonl`.

## Run it

Requires [uv](https://docs.astral.sh/uv/) and Python 3.10+. The server runs in the project folder, because its final check reads the project's files.

```bash
uv sync
uv run coherence-mcp --project /path/to/your/project
```

That starts the server over stdio. Without `--project`, it uses `COHERENCE_PROJECT` or the current folder. Set `COHERENCE_LIBRARY_DIR` to use a different copy of the library.

### Connect to Claude Code

Add this to the project's `.mcp.json`, with the path to this repository:

```json
{
  "mcpServers": {
    "coherence": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/coherence-mcp", "coherence-mcp"]
    }
  }
}
```

## Test

```bash
uv run pytest
```

## License

MIT
