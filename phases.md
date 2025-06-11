# Tanuki MCP: Taskmaster - Production Implementation Manual

This document is the definitive, explicit, and sequential four-phase plan to build and deploy the **Taskmaster MCP Server**. The architecture is centered around a **single gateway tool (`taskmaster`)** to provide a clean, powerful interface for the LLM.

Each phase is a self-contained, production-focused sprint. The logic built is designed to be dynamic, configurable, and extensible—**no hardcoding, no static logic**. Following this manual will result in a robust server deployed flawlessly to Smithery.ai.

---

## **Phase 1: The Core Engine & `taskmaster` Gateway** ✅ **COMPLETED**

### **Primary Goal**
Construct the server's skeleton. We will establish the project structure, state management, and the all-important `taskmaster` tool, which will act as a command router. This foundation will be built for extension, not replacement.

### **✅ PHASE 1 COMPLETION STATUS**
**All Phase 1 requirements have been implemented:**
- ✅ Directory structure created exactly as specified
- ✅ `config.yaml` created with state directory configuration
- ✅ `taskmaster/models.py` implemented with Pydantic Task and Session models
- ✅ `taskmaster/commands/base_command.py` abstract base class created
- ✅ `taskmaster/commands/create_session.py` command implemented
- ✅ `taskmaster/commands/add_task.py` command implemented  
- ✅ `taskmaster/commands/get_tasklist.py` command implemented
- ✅ `server.py` MCP server with single `taskmaster` gateway tool implemented
- ✅ `requirements.txt` created with necessary dependencies
- ✅ All state persistence functionality working with filesystem JSON storage

**Ready for Phase 2 implementation in a new chat session.**

### **Core Components & Structure**
First, create this exact directory structure. This is non-negotiable for ensuring modules are found correctly.

```
/tanukimcp-taskmaster/
├── taskmaster/
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── base_command.py
│   │   ├── create_session.py
│   │   └── add_task.py
│   ├── state/
│   ├── __init__.py
│   └── models.py
├── tests/
├── server.py
└── config.yaml
```

### **Implementation Details (Vividly Detailed)**

1.  **`config.yaml`**: Create this file. It will manage all configurable paths and settings.
    ```yaml
    # config.yaml
    state_directory: 'taskmaster/state'
    ```

2.  **Data Models (`taskmaster/models.py`)**: Use Pydantic for automatic data validation and serialization. This is critical for production quality.
    ```python
    # taskmaster/models.py
    from pydantic import BaseModel, Field
    from typing import List, Optional
    import uuid

    class Task(BaseModel):
        id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
        description: str
        status: str = "[ ]" # Enforce "[ ]" or "[X]"
        # Fields for Phase 2
        validation_required: bool = False
        validation_criteria: List[str] = []
        evidence: List[dict] = []

    class Session(BaseModel):
        id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
        tasks: List[Task] = []
        # Field for Phase 3
        environment_map: Optional[dict] = None
    ```

3.  **Command Router (`taskmaster/commands/base_command.py` and specific commands)**: We will use a command pattern. The `taskmaster` tool will dynamically load and execute command classes from the `commands` directory.
    ```python
    # taskmaster/commands/base_command.py
    from abc import ABC, abstractmethod
    from ..models import Session

    class BaseCommand(ABC):
        @abstractmethod
        def execute(self, payload: dict) -> dict:
            pass
    ```
    ```python
    # taskmaster/commands/create_session.py
    # (Implementation will create a new Session object and save it)
    ```

4.  **`server.py` (The Single Gateway)**: This is the heart of the MCP server. It will define a **single tool**: `taskmaster`. This tool acts as a router, delegating work to the appropriate command module. This is a cleaner and more powerful approach than exposing many small tools.

### **MCP Implementation**
The LLM will interact with **only one tool**.

-   **`@tool taskmaster(command: str, payload: dict) -> dict`**: The single, unified entry point for all operations.
    -   **`command="create_session"`**, `payload={}`
        -   *Action*: Creates a new `Session`, saves it as `session_xyz.json` in the `taskmaster/state` directory, and returns `{"session_id": "session_xyz"}`.
    -   **`command="add_task"`**, `payload={"session_id": "...", "description": "..."}`
        -   *Action*: Loads the session, adds a new `Task` to its `tasks` list, saves the session, and returns `{"task_id": "task_abc"}`.
    -   **`command="get_tasklist"`**, `payload={"session_id": "..."}`
        -   *Action*: Loads the session and returns a dictionary representation of the `tasks` list.

### **Deliverable**
A runnable local MCP server with a single, powerful `taskmaster` tool that can create sessions and add tasks via a command-based API, with all state persisted to the filesystem.

---

## **Phase 2: The Advanced Validation & Anti-Hallucination Engine** ✅ **COMPLETED**

### **Primary Goal**
To build the server's conscience. We will create a dynamic, pluggable `ValidationEngine` and integrate it deeply into the `taskmaster` command flow. This makes hallucinated progress impossible.

### **✅ PHASE 2 COMPLETION STATUS**
**All Phase 2 requirements have been implemented:**
- ✅ `taskmaster/validation_rules/` directory structure created
- ✅ `base_rule.py` abstract base class implemented 
- ✅ `syntax_rule.py` validation rule implemented with Python/JavaScript support
- ✅ `content_contains_rule.py` validation rule implemented
- ✅ `file_exists_rule.py` validation rule implemented
- ✅ `ValidationEngine` class implemented with dynamic rule loading
- ✅ `define_validation_criteria` command implemented
- ✅ `mark_task_complete` command implemented with validation orchestration
- ✅ `get_validation_rules` command implemented
- ✅ Evidence storage functionality working
- ✅ All validation passing/failing scenarios tested and working

**Ready for Phase 3 implementation in a new chat session.**

### **Core Components & Structure**
Add to the existing structure:
```
/taskmaster/
├── validation_rules/
│   ├── __init__.py
│   ├── base_rule.py
│   └── syntax_rule.py
├── commands/
│   ├── ...
│   └── mark_task_complete.py
└── validation_engine.py
```

### **Implementation Details (Vividly Detailed)**

1.  **Pluggable Rules Engine**: We will **not** hardcode validation logic.
    -   **`taskmaster/validation_rules/base_rule.py`**: Define a base class for all rules.
        ```python
        # taskmaster/validation_rules/base_rule.py
        from abc import ABC, abstractmethod
        from ..models import Task

        class BaseValidationRule(ABC):
            @property
            @abstractmethod
            def rule_name(self) -> str:
                pass

            @abstractmethod
            def check(self, task: Task, evidence: dict) -> (bool, str):
                # Returns (is_valid, message)
                pass
        ```
    -   **`ValidationEngine` (`taskmaster/validation_engine.py`)**: This class will dynamically load all rule classes from the `validation_rules` directory. It will have one method: `validate(task, evidence)`, which runs all checks listed in `task.validation_criteria`.

2.  **Deep Integration with Commands**: Validation is not an afterthought; it's a core part of a command's execution.
    -   The `mark_task_complete` command will be responsible for orchestrating the validation. It will instantiate the `ValidationEngine`, call its `validate` method, and only if validation succeeds will it change the task's status to `[X]`.

### **MCP Implementation**
The `taskmaster` tool is extended with new commands:

-   **`command="define_validation_criteria"`**, `payload={"session_id": "...", "task_id": "...", "criteria": ["syntax_rule"], "validation_required": true}`
    -   *Action*: Loads the specified task and sets its `validation_criteria` list and `validation_required` flag.
-   **`command="mark_task_complete"`**, `payload={"session_id": "...", "task_id": "...", "evidence": {...}}`
    -   *Action*:
        1.  Loads the task.
        2.  If `validation_required` is `True`, it calls the `ValidationEngine`.
        3.  The engine runs the checks from `validation_criteria` against the `evidence` payload.
        4.  If all checks pass, it stores the evidence with timestamp, updates the task status to `[X]`, saves the session, and returns `{"status": "complete", "validation_messages": [...]}`.
        5.  If any check fails, it returns `{"status": "validation_failed", "validation_messages": [...], "message": "Task validation failed. Task remains incomplete."}`.
-   **`command="get_validation_rules"`**, `payload={}`
    -   *Action*: Returns all available validation rules loaded by the `ValidationEngine`.

**Implemented Validation Rules:**
- `syntax_rule`: Validates Python/JavaScript code syntax
- `content_contains_rule`: Checks if content contains required strings (case-sensitive/insensitive)
- `file_exists_rule`: Verifies that specified files exist on the filesystem

### **Deliverable**
An MCP server where task completion is strictly gated. The `taskmaster` tool now refuses to mark tasks complete without passing a dynamic, extensible set of validation rules. Evidence is stored with timestamps for audit purposes, and comprehensive validation messages provide clear feedback.

---

## **Phase 3: The Smart Environment & Capability Scanner** ✅ **COMPLETED**

### **Primary Goal**
To give the server eyes and ears. We will build a fast, asynchronous, and cached `EnvironmentScanner` whose results are integrated directly into the session.

### **✅ PHASE 3 COMPLETION STATUS**
**All Phase 3 requirements have been implemented:**
- ✅ `taskmaster/scanners/` directory structure created
- ✅ `base_scanner.py` abstract base class implemented
- ✅ `system_tool_scanner.py` implemented with async tool detection and system info gathering
- ✅ `environment_scanner.py` implemented with dynamic scanner loading and async orchestration
- ✅ `create_session` command updated to perform environment scanning on session creation
- ✅ `scan_environment` command implemented for manual rescanning
- ✅ `get_environment` command implemented with filtering and summary options
- ✅ Config.yaml updated with scanner configuration options
- ✅ All environment scanning functionality working with persistent caching in session state
- ✅ Async/parallel scanning with timeout protection and error handling
- ✅ Comprehensive system tool detection covering 40+ common development tools

**Ready for Phase 4 implementation in a new chat session.**

### **Core Components & Structure**
Add to the existing structure:
```
/taskmaster/
├── scanners/
│   ├── __init__.py
│   ├── base_scanner.py
│   └── system_tool_scanner.py
└── environment_scanner.py
```

### **Implementation Details (Vividly Detailed)**

1.  **Asynchronous & Parallel Scanning**: To meet the "near-instantaneous" requirement, we will use `asyncio`.
    -   **`EnvironmentScanner` (`taskmaster/environment_scanner.py`)**: This class will dynamically load all scanner modules from the `scanners` directory and run their `scan` methods concurrently using `asyncio.gather`.
2.  **Caching**: The scan results are stored directly in the `session.json` file in the `environment_map` field. This provides a persistent cache per session. The `create_session` command will perform the initial scan.
3.  **Configurable Scanners**: The scanners will not have hardcoded tool names. For example, `system_tool_scanner` will read a list of executables to check for from `config.yaml`.

### **MCP Implementation**
The `taskmaster` tool is enhanced:

-   **`command="create_session"` (Updated)**:
    -   *Action*: After creating the session object, it now also runs the `EnvironmentScanner` and populates the `environment_map` field before the first save.
-   **`command="scan_environment"`**, `payload={"session_id": "..."}`
    -   *Action*: Manually triggers a full rescan of the environment and updates the `environment_map` for that session.
-   **`command="get_environment"`**, `payload={"session_id": "..."}`
    -   *Action*: Returns the `environment_map` from the session state.

### **Deliverable**
A `taskmaster` tool that creates environment-aware sessions, providing context for what tools and resources are available for the tasks at hand.

---

## **Phase 4: Production Hardening & Flawless Smithery Deployment**

### **Primary Goal**
This is the final sprint. We will polish the server to absolute production-grade quality and deploy it to Smithery.ai with a simple `git push`. **Every step must be followed exactly.**

### **Implementation Steps (EXTREMELY EXPLICIT)**

1.  **Finalize Code & Lazy Loading**:
    -   **Lazy Loading is CRITICAL for Smithery**: In `server.py`, DO NOT import your command, validation, or scanner modules at the top of the file. Import them *inside* the `taskmaster` tool function. This ensures the server starts instantly, passing Smithery's cold-start health checks.
        ```python
        # server.py
        @tool
        def taskmaster(command: str, payload: dict) -> dict:
            # Lazy import command module
            import importlib
            try:
                # e.g., command_module = importlib.import_module(".create_session", "taskmaster.commands")
                command_module = importlib.import_module(f".{command}", "taskmaster.commands")
                command_class = getattr(command_module, "Command")
                instance = command_class()
                return instance.execute(payload)
            except (ImportError, AttributeError) as e:
                return {"error": f"Invalid command '{command}'", "details": str(e)}
        ```
    -   **Finalize all Commands**: Implement `progress_to_next`, `end_session`, etc., with full error handling.

2.  **Comprehensive Testing**:
    -   Use `pytest` to create tests for every single `taskmaster` command.
    -   Test success paths, failure paths (e.g., bad session ID), and edge cases. Aim for >95% coverage.

3.  **Create `requirements.txt`**:
    -   Lock your dependencies. This is vital for reproducible builds.
    -   Run `pip freeze > requirements.txt` in your terminal.
    -   Ensure it contains `fastmcp`, `pydantic`, `pyyaml`, and `pytest`.

4.  **Create `smithery.yaml`**:
    -   This file is the **key to a successful deployment**. Create it in the root directory.
    -   ```yaml
        # smithery.yaml
        version: 1
        deployment:
          type: python
          command: "uvicorn server:app --host 0.0.0.0 --port $PORT"
          health_check:
            path: "/health"
        ```
    -   *Explanation*:
        -   `type: python`: Tells Smithery what kind of application it is.
        -   `command`: The exact command to run. `uvicorn` is a production-grade ASGI server that FastMCP is built on. Using `server:app` points to the `app` object inside your `server.py` file.
        -   `--host 0.0.0.0`: **CRITICAL**. This tells the server to listen for traffic from outside its container.
        -   `--port $PORT`: **CRITICAL**. Smithery assigns a port via the `$PORT` environment variable. You MUST use it.
        -   `health_check`: FastMCP provides a `/health` endpoint out of the box. Smithery uses this to see if your app started correctly.

5.  **Final `README.md`**:
    -   Create a high-quality `README.md` that documents the `taskmaster` tool's API (all commands and their payloads).

6.  **The Final Deployment Workflow**:
    -   Open your terminal in the project root.
    -   **Step 6.1**: Check your work: `git status`. Ensure `server.py`, `requirements.txt`, `smithery.yaml`, the `taskmaster` directory, and your `README.md` are all present.
    -   **Step 6.2**: Stage all files: `git add .`
    -   **Step 6.3**: Commit with a clear message: `git commit -m "build: Finalize server for Smithery v1.0 deployment"`
    -   **Step 6.4**: Push to the main branch: `git push origin main`

### **What Happens Next (The Magic)**
When you push to the `main` branch of `TanukiMCP/taskmaster`, a Smithery webhook fires. Smithery clones your repo, reads `smithery.yaml`, sees it's a Python app, and runs `pip install -r requirements.txt`. Then, it executes the `uvicorn` command. Because you implemented lazy loading, the server starts in milliseconds. Smithery's health check hits the `/health` endpoint, gets a `200 OK`, and marks your deployment as successful.

### **Deliverable**
A fully operational, production-grade, and robust MCP Taskmaster server, live on Smithery.ai, deployed automatically and flawlessly from a single `git push`. 