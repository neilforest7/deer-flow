# Project Team Runtime Architecture

**Status**: ✅ Implemented and Production-Ready
**Version**: M1
**Last Updated**: 2026-03-30

## Overview

The Project Team Runtime (`project_team_agent`) is a separate LangGraph-based agent runtime that orchestrates multi-agent software delivery through explicit phases. It runs alongside the default `lead_agent` without modifying core DeerFlow behavior.

**Key Characteristics**:
- Phase-driven explicit graph (not prompt-driven orchestration)
- Specialist agents execute via `SubagentExecutor` substrate
- Checkpointer-based persistence for multi-turn execution
- In-conversation approval gate before build execution
- Dual-mode: specialist execution with deterministic fallback

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     project_team_agent Graph                     │
│                                                                   │
│  START → route_from_phase (conditional entry based on state)     │
│                                                                   │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐                 │
│  │ intake   │───▶│ discovery │───▶│ planning │                  │
│  └──────────┘    └───────────┘    └──────────┘                  │
│                        │                 │                        │
│                        ▼                 ▼                        │
│                  discovery-agent   planner-agent                 │
│                  architect-agent                                 │
│                  design-agent                                    │
│                                                                   │
│  ┌──────────────────┐                                            │
│  │ awaiting_approval│◀───────────────┘                          │
│  └──────────────────┘                                            │
│         │                                                         │
│         ├─ /approve ──▶ build                                   │
│         ├─ /revise ───▶ planning                                │
│         └─ /cancel ───▶ done                                    │
│                                                                   │
│  ┌───────┐                                                       │
│  │ build │  (parallel work order dispatch)                      │
│  └───────┘                                                       │
│      │                                                            │
│      ├──▶ frontend-agent                                        │
│      ├──▶ backend-agent                                         │
│      ├──▶ integration-agent                                     │
│      ├──▶ devops-agent                                          │
│      ├──▶ data-agent                                            │
│      └──▶ design-agent                                          │
│                                                                   │
│  ┌─────────┐                                                     │
│  │ qa_gate │───▶ qa-agent                                       │
│  └─────────┘                                                     │
│      │                                                            │
│      ├─ pass ──▶ delivery                                       │
│      └─ fail ──▶ planning (with rework)                        │
│                                                                   │
│  ┌──────────┐    ┌──────┐                                       │
│  │ delivery │───▶│ done │───▶ END                               │
│  └──────────┘    └──────┘                                       │
│       │                                                           │
│       ▼                                                           │
│  delivery-agent                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
backend/packages/harness/deerflow/project_runtime/
├── graph.py              # Main graph factory and phase nodes
├── state.py              # ProjectThreadState schema
├── types.py              # Canonical types (WorkOrder, ProjectBrief, etc.)
├── planning.py           # Discovery and planning phase execution
├── delivery.py           # Delivery phase execution
├── dispatcher.py         # Build phase work order dispatch
├── qa.py                 # QA gate execution
├── approval.py           # Approval routing logic
├── registry.py           # Specialist registry and configuration
├── prompts.py            # Phase-specific prompts
└── observability.py      # LangSmith tracing metadata
```

## Phase Flow

### 1. Intake Phase
**Node**: `intake_node`
**Purpose**: Initialize project runtime state
**Output**: Default `ProjectThreadState` with phase set to `INTAKE`

### 2. Discovery Phase
**Node**: `discovery_node` → `run_discovery()`
**Specialists**: `discovery-agent`, `architect-agent`, `design-agent` (conditional)
**Execution**: `execute_discovery_phase()` via `SubagentExecutor`
**Output**: Validated `ProjectBrief` with objective, scope, constraints, deliverables, success criteria
**Fallback**: `synthesize_project_brief()` if specialist execution fails and fallback is allowed

### 3. Planning Phase
**Node**: `planning_node` → `run_planning()`
**Specialist**: `planner-agent`
**Execution**: `execute_planning_phase()` via `SubagentExecutor`
**Output**: Validated `PlanningOutput` with structured `WorkOrder[]`
**Fallback**: `synthesize_work_orders()` if specialist execution fails and fallback is allowed
**QA Replan**: If returning from failed QA gate, `_replan_from_qa_failure()` appends rework notes to work orders

### 4. Awaiting Approval Phase
**Node**: `awaiting_approval_node` → `resolve_approval_update()`
**Purpose**: Wait for explicit user approval before build execution
**Commands**:
- `/approve` → transition to `build` phase
- `/revise <feedback>` → return to `planning` phase with revision notes
- `/cancel` → transition to `done` phase
- Natural language revision feedback → treated as `/revise`

**Policy**: Conservative - no explicit approval = no build execution

### 5. Build Phase
**Node**: `build_node` → `dispatch_build_phase()`
**Specialists**: `frontend-agent`, `backend-agent`, `integration-agent`, `devops-agent`, `data-agent`, `design-agent`
**Execution**: Parallel work order dispatch via `SubagentExecutor`
**Scheduling**: Only runnable work orders (dependencies satisfied, not completed, not active)
**Output**: `AgentReport` per work order with summary, changes, risks, verification

### 6. QA Gate Phase
**Node**: `qa_gate_node` → `run_qa_gate()`
**Specialist**: `qa-agent`
**Execution**: Hybrid - executable checks run via `SubagentExecutor`, non-executable checks preserved as findings
**Output**: `QAGate` with result (`pass`/`fail`/`blocked`), findings, required_rework
**Routing**:
- `pass` → `delivery` phase
- `fail` → `planning` phase (with rework appended to work orders)
- `blocked` → END (interrupt)

### 7. Delivery Phase
**Node**: `delivery_node` → `run_delivery()`
**Specialist**: `delivery-agent`
**Execution**: `execute_delivery_phase()` via `SubagentExecutor`
**Output**: `DeliverySummary` with completed_work, artifacts, verification, follow_ups
**Fallback**: `build_delivery_summary()` aggregates from state if specialist execution fails

### 8. Done Phase
**Node**: `done_node`
**Purpose**: Terminal state, marks project completion
**Output**: Phase set to `DONE`, graph terminates

## State Management

### ProjectThreadState Schema

Extends `ThreadState` with project-specific fields:

```python
{
    # Inherited from ThreadState
    "messages": [...],
    "thread_data": {...},
    "sandbox": {...},
    "artifacts": [...],

    # Project runtime fields
    "phase": "intake|discovery|planning|awaiting_approval|build|qa_gate|delivery|done",
    "plan_status": "draft|awaiting_approval|approved|needs_revision",
    "project_brief": {
        "objective": str,
        "scope": [str],
        "constraints": [str],
        "deliverables": [str],
        "success_criteria": [str]
    },
    "work_orders": [{
        "id": str,
        "owner_agent": str,
        "title": str,
        "goal": str,
        "read_scope": [str],
        "write_scope": [str],
        "dependencies": [str],
        "acceptance_checks": [str],
        "status": "pending|active|completed|failed"
    }],
    "active_work_order_ids": [str],
    "agent_reports": [{
        "work_order_id": str,
        "agent_name": str,
        "summary": str,
        "changes": [str],
        "risks": [str],
        "verification": [str]
    }],
    "qa_gate": {
        "result": "pass|fail|blocked",
        "findings": [str],
        "required_rework": [str]
    },
    "delivery_summary": {
        "completed_work": [{...}],
        "artifacts": [str],
        "verification": [str],
        "follow_ups": [str]
    },
    "phase_artifacts": {
        "discovery": {"mode": "specialist|deterministic", ...},
        "planning": {"mode": "specialist|deterministic|qa-replan", ...},
        "delivery": {"mode": "specialist|deterministic", ...}
    },
    "phase_attempts": {
        "discovery": int,
        "planning": int,
        "delivery": int
    },
    "trace_id": str,
    "project_runtime_version": str
}
```

### Persistence

**Authority**: LangGraph checkpointer (single source of truth)
**Multi-turn**: Graph re-enters via `route_from_phase()` based on persisted `phase` field
**No secondary storage**: No project database, no global project store

## Specialist Execution

### Execution Pattern

All specialists execute through the same substrate:

```python
def _execute_specialist_json(
    specialist_name: str,
    task: str,
    *,
    phase: Phase,
    state: Mapping[str, Any],
    thread_id: str | None,
    parent_model: str | None = None,
    trace_id: str | None = None,
    run_metadata: Mapping[str, Any] | None = None,
    available_tools: list[Any] | None = None,
    executor_cls=None,
) -> dict[str, Any]:
    # 1. Get specialist config from registry
    specialist_config = get_specialist_config(specialist_name)

    # 2. Filter tools based on phase and ACP policy
    filtered_tool_names = tool_names_for_specialist(
        specialist_name, available_tools, phase=phase, acp_enabled=...
    )

    # 3. Create scoped executor
    executor = SubagentExecutor(
        config=scoped_config,
        tools=available_tools,
        parent_model=parent_model,
        sandbox_state=state.get("sandbox"),
        thread_data=state.get("thread_data"),
        thread_id=thread_id,
        trace_id=trace_id,
        run_metadata=run_metadata,
    )

    # 4. Execute and extract JSON result
    result = executor.execute(task)
    return _extract_json_payload(result.result)
```

### Specialist Roster

| Specialist | Phase | Purpose |
|------------|-------|---------|
| `discovery-agent` | discovery | Requirements analysis |
| `architect-agent` | discovery | System architecture |
| `design-agent` | discovery | UX/UI design (conditional) |
| `planner-agent` | planning | Work order generation |
| `frontend-agent` | build | Frontend implementation |
| `backend-agent` | build | Backend implementation |
| `integration-agent` | build | Cross-system integration |
| `devops-agent` | build | CI/CD and infrastructure |
| `data-agent` | build | Data and schema work |
| `qa-agent` | qa_gate | Quality assurance |
| `delivery-agent` | delivery | Delivery summary generation |

### Tool Filtering

Each specialist has a curated tool allowlist based on phase:

- **Discovery/Planning/Delivery**: Read-only tools (ls, read_file, grep)
- **Build**: Full sandbox tools (bash, write_file, str_replace)
- **QA**: Verification tools (bash for test execution)
- **ACP**: Controlled by `acp_allowed_specialists` config

## Dual-Mode Execution

### Specialist Mode (Default)

Phases execute through real specialist agents via `SubagentExecutor`:

```python
try:
    project_brief, executed, _ = execute_discovery_phase(state, thread_id=thread_id)
    phase_artifacts["discovery"] = {
        "mode": "specialist",
        "specialists": executed,
        "project_brief": project_brief.model_dump(mode="json"),
    }
except Exception:
    # Fallback if allowed
    ...
```

### Deterministic Fallback Mode

If specialist execution fails and `allow_deterministic_phase_fallback=true`:

```python
if not _deterministic_phase_fallback_allowed():
    raise  # Force specialist-only execution

# Fallback to deterministic synthesis
project_brief = synthesize_project_brief(state)
phase_artifacts["discovery"] = {
    "mode": "deterministic",
    "project_brief": project_brief.model_dump(mode="json"),
}
```

**Configuration**:
```yaml
# config.yaml
project_runtime:
  allow_deterministic_phase_fallback: true  # Default: compatibility mode
  # Set to false for specialist-only execution
```

### Mode Tracking

`phase_artifacts` records execution mode for observability:
- `"mode": "specialist"` - Specialist executed successfully
- `"mode": "deterministic"` - Fallback synthesis used
- `"mode": "qa-replan"` - QA-driven replanning (planning phase only)

## Client Integration

### Embedded Client

`DeerFlowClient` provides direct in-process access:

```python
from deerflow.client import DeerFlowClient

client = DeerFlowClient()

# Project runtime methods
response = client.project_chat("Build a user authentication system", thread_id="thread-123")

for event in client.project_stream("Add login page", thread_id="thread-123"):
    if event["event"] == "messages-tuple":
        print(event["data"])
```

### LangGraph Server

Via LangGraph SDK HTTP client:

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2024")

# Select project_team_agent
thread = client.threads.create()
for chunk in client.runs.stream(
    thread["thread_id"],
    "project_team_agent",  # assistant_id
    input={"messages": [{"role": "user", "content": "Build auth system"}]}
):
    print(chunk)
```

## Observability

### LangSmith Tracing

**Top-level metadata** (attached to graph runs):
```python
{
    "runtime": "project_team",
    "thread_id": str,
    "phase": str,
    "plan_status": str,
    "project_runtime_version": str
}
```

**Specialist metadata** (attached to SubagentExecutor runs):
```python
{
    "runtime": "project_team",
    "thread_id": str,
    "phase": str,
    "work_order_id": str,  # For build phase
    "owner_agent": str,
    "execution_kind": "discovery_specialist|planning_specialist|build_specialist|qa_check|delivery_specialist",
    "attempt": int
}
```

**Trace propagation**: Single `trace_id` flows from graph → all specialist executions

### Phase Artifacts

Stored in `ProjectThreadState.phase_artifacts` for runtime introspection:

```python
{
    "discovery": {
        "mode": "specialist",
        "specialists": ["discovery-agent", "architect-agent"],
        "project_brief": {...}
    },
    "planning": {
        "mode": "specialist",
        "work_orders": [...]
    },
    "delivery": {
        "mode": "specialist",
        "delivery_summary": {...}
    }
}
```

## Configuration

### Project Runtime Config

```yaml
# config.yaml
project_runtime:
  default_model_name: "gpt-4"  # Model for specialists
  acp_allowed_specialists: ["frontend-agent", "backend-agent"]  # ACP access
  allow_deterministic_phase_fallback: true  # Dual-mode control
```

### Specialist Registry

Defined in `project_runtime/registry.py`:

```python
_SPECIALIST_CONFIGS = {
    "discovery-agent": SubagentConfig(
        name="discovery-agent",
        description="Requirements and discovery specialist",
        system_prompt="...",
        tools=["ls", "read_file", "grep"],
        max_turns=10
    ),
    # ... other specialists
}
```

## Boundaries and Isolation

### Module Boundary

**Namespace**: `deerflow.project_runtime.*`

**Dependencies** (allowed):
- ✅ `deerflow.subagents.executor.SubagentExecutor`
- ✅ `deerflow.tools.get_available_tools`
- ✅ `deerflow.config.get_app_config`
- ✅ `deerflow.models.create_chat_model`
- ✅ Sandbox, checkpointer, thread substrate

**Isolation** (forbidden):
- ❌ No changes to `lead_agent` graph or prompt
- ❌ No changes to core subagent registry
- ❌ No injection into `MemoryMiddleware`
- ❌ No `task` tool exposure to project runtime

### Memory Isolation

Project runtime **never** writes to long-term memory:
- `ProjectBrief`, `WorkOrder`, `AgentReport` stay in `ProjectThreadState`
- QA findings and delivery summaries stay in graph state
- No memory queue enqueuing from project runtime

### Substrate Reuse

**Shared** (same contracts as `lead_agent`):
- Thread directory layout: `.deer-flow/threads/{thread_id}/`
- Sandbox provider acquisition
- Virtual path conventions: `/mnt/user-data/*`
- Tool error handling and guardrails

**Independent** (project-runtime-local):
- Phase model and transitions
- Specialist roster and registry
- Approval gate logic
- QA gate logic
- Delivery summary semantics

## Testing

### Test Coverage

**Unit tests**:
- `tests/test_project_runtime_graph.py` - Graph structure and phase transitions
- `tests/test_project_runtime_planning.py` - Planning phase logic
- `tests/test_project_runtime_delivery.py` - Delivery phase logic
- `tests/test_project_runtime_dispatcher.py` - Build dispatch
- `tests/test_project_runtime_qa.py` - QA gate

**Integration tests**:
- Multi-turn execution with checkpointer
- Approval routing (`/approve`, `/revise`, `/cancel`)
- QA failure → planning replan loop
- Specialist execution end-to-end

**Boundary tests**:
- `lead_agent` unchanged when `project_team_agent` not selected
- Memory isolation (no writes to long-term memory)
- Thread isolation (no cross-thread state leakage)

## Future Enhancements (Post-M1)

- Frontend UI for phase visualization and approval
- Project CRUD APIs for multi-project management
- Project board/control plane
- Persistent project store (separate from thread state)
- Advanced specialist orchestration (sub-teams, parallel phases)
- Custom specialist definitions via config
- Phase-level rollback and replay

## References

- [PRD: Project Team Runtime M1](./project_team_runtime_prd.md)
- [DeerFlow Architecture](./ARCHITECTURE.md)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
