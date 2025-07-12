Hello! We are about to embark on a fascinating and advanced project. I need you to act as an expert software engineer and build a new Model Context Protocol (MCP) server from scratch. This server's architecture is crucial: it will act as a **cognitive planner**, not an executor.

**Project Name:** `turingmcp`

**Core Philosophy:**
The goal of `turingmcp` is to create a **cognitive, Turing-complete planning engine** for an LLM agent. The server's role is to maintain an internal "world model" of the environment and, based on a goal, decide the single next logical action to take.

Crucially, **the server does not execute anything itself**. It does not touch the file system or run shell commands. Instead, it returns a structured JSON object describing the action that the MCP *client* (e.g., an IDE or CLI tool) should perform. This creates a secure separation between the "brain" (the MCP server) and the "hands" (the MCP client).

This is the fundamental architectural pattern:

```ascii
      +---------------------+         +----------------------+
      |       Planner       |         |       Executor       |
      |   (Cognitive MCP    |         |   (Agentic Client    |
      |       Server)       |         |      IDE / CLI)      |
      +---------------------+         +----------------------+
      | - Internal World Model|         | - Real File System   |
      | - Internal CWD State  |         | - Real Terminal      |
      | - Reasoning Engine    |         | - User Permissions   |
      +---------------------+         +----------------------+
            (THINKS)                        (DOES)
```

**Architectural Concepts:**

1.  **The "World Model"**: The server must maintain an internal, in-memory representation of the client's file system structure and current working directory (CWD). This model is updated based on the results of actions reported back by the client.

    ```ascii
    +----------------------------------+
    |         Server Memory            |
    | +------------------------------+ |
    | |      Internal World Model    | |
    | | +--------------------------+ | |
    | | | CWD: /workspace/app      | | |
    | | +--------------------------+ | |
    | | | Files:                   | | |
    | | |   - /workspace/README.md | | |
    | | |   - /workspace/app/      | | |
    | | +--------------------------+ | |
    | +------------------------------+ |
    +----------------------------------+
    ```

2.  **The "Cognitive Head"**: This is the server's internal concept of the agent's CWD. This state must be persisted across calls.

3.  **The "Action Plan" Tools**: The MCP tools you implement will not perform actions. They will return a JSON object describing a single, primitive action for the client to execute.

**The Cognitive Loop:**

The interaction between the server and client creates a turn-based feedback loop:

```ascii
+-----------------+       1. Plan (JSON Action)     +-----------------+
|   Planner       | ------------------------------> |    Executor     |
| (turingmcp)     |                                 | (Client)        |
|                 | <------------------------------ |                 |
+-----------------+    2. Result of Executed Action +-----------------+
```

**Technical Specifications:**

*   **Framework:** Use Python with the `@FastMCP` library.
*   **Endpoint:** The server must expose a single `/mcp` endpoint for all communication.
*   **Streaming:** All tool responses should be streamable to provide real-time feedback.
*   **State Management:** The server must manage the agent's CWD *within its internal world model*. The initial CWD should be the root of the workspace.

**The Cognitive Primitive Tools to Implement:**

You will implement the following tools in a `server.py` file. Each tool's function is to return a JSON object representing an "Action Plan."

1.  `plan_read_at_head(path: str) -> dict`:
    *   **Purpose**: To generate a plan for the client to read a file or directory.
    *   **Output**:
        ```json
        {
          "action_plan": {
            "tool": "read",
            "path": "path/to/read"
          },
          "reasoning": "I need to read this file to understand its contents."
        }
        ```

2.  `plan_write_at_head(path: str, content: str) -> dict`:
    *   **Purpose**: To generate a plan for the client to write content to a file.
    *   **Output**:
        ```json
        {
          "action_plan": {
            "tool": "write",
            "path": "path/to/write",
            "content": "Content to be written to the file."
          },
          "reasoning": "To create the new module, I must write this content to the file."
        }
        ```

3.  `plan_move_head(new_path: str) -> dict`:
    *   **Purpose**: To generate a plan for the client to change its CWD.
    *   **Logic**: Before generating the plan, the server should update its *internal* CWD state to reflect the new focus for subsequent planning.
    *   **Output**:
        ```json
        {
          "action_plan": {
            "tool": "change_directory",
            "path": "path/to/move/to"
          },
          "reasoning": "My next actions will concern files in this directory, so I need to shift my focus."
        }
        ```

4.  `plan_execute_at_head(command: str) -> dict`:
    *   **Purpose**: To generate a plan for the client to execute a shell command.
    *   **Output**:
        ```json
        {
          "action_plan": {
            "tool": "execute_shell",
            "command": "command to run"
          },
          "reasoning": "I need to install dependencies by running this command."
        }
        ```

5.  `update_world_model(action_result: dict) -> dict`:
    *   **Purpose**: A critical tool for the client to report the results of an executed action back to the server.
    *   **Logic**: The server parses the `action_result` and updates its internal world model. For example, if a `write` action was successful, it adds the file to its internal representation of the file system.
    *   **Input `action_result` Example**: `{"tool": "write", "path": "app/main.py", "status": "success"}`
    *   **Output**: A dictionary confirming the model has been updated. `{"status": "world_model_updated"}`

**Your Task:**

1.  Create a new project directory named `turingmcp`.
2.  Inside this directory, create a `server.py` file and implement the `turingmcp` server with the five "planning" tools and the one "update" tool described above. The most critical part is managing the server's internal "world model" state across calls.
3.  Create a `requirements.txt` file with the necessary dependencies (`fastmcp`, `uvicorn`).
4.  Create a `README.md` that explains this powerful cognitive planner vs. executor architecture and documents the six tools and the expected JSON structures for their `action_plan` outputs.

This is a challenging but highly rewarding project. I will be here to review your progress. Please begin. 