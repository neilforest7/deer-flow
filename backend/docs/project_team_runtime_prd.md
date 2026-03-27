# PRD: DeerFlow Coding/Delivery Team Runtime (M1)

## Status

- Revision basis: `origin/main`
- Scope: backend runtime only
- Goal: add an optional, isolated team runtime without changing default `lead_agent` behavior

## Summary

On top of the clean `origin/main` baseline, add a fully optional team runtime for the multi-agent delivery flow:

`planning -> specialist collaboration -> QA gate -> delivery summary`

The M1 deliverable is a backend runtime that satisfies these requirements:

- Add a separate graph: `project_team_agent`
- Keep `lead_agent`, existing memory, and existing gateway/frontend behavior unchanged by default
- Use an explicit graph plus canonical `WorkOrder` records to represent phases and execution boundaries
- Run specialists as isolated subagents, while keeping orchestration in the explicit graph rather than prompt-driven task delegation
- Use `ProjectThreadState + checkpointer` as the single durable authority
- Require in-conversation user approval before `build`
- Treat ACP as an optional extension point rather than an M1 dependency

## Architecture And Boundaries

### 1. Module Boundary

Add a dedicated namespace:

- `backend/packages/harness/deerflow/project_runtime`

This module may depend on existing harness substrate capabilities:

- model factory
- sandbox tools
- `SubagentExecutor` / `SubagentConfig`
- checkpointer
- MCP / ACP / built-in tool assembly
- thread path and sandbox provider substrate

This module must not leak team semantics back into core:

- do not change the default `lead_agent` prompt
- do not change the default `lead_agent` graph
- do not change the meaning of the core global subagent registry
- do not inject `ProjectBrief`, `WorkOrder`, QA gate semantics, or approval UX into `lead_agent`
- do not require core memory, gateway, or frontend to understand team runtime concepts

M1 allows only these externally visible integration changes:

- `backend/langgraph.json` adds `project_team_agent`
- `backend/packages/harness/deerflow/client.py` adds a thin wrapper for project runtime targeting
- `config.example.yaml` adds a minimal project runtime configuration surface for specialist or tool policy

M1 must not add:

- project CRUD APIs
- project board or control plane APIs
- frontend project UI
- a new global project store namespace

### 2. Independence Boundary

The team runtime is independent at the team-semantics layer, not at the substrate layer.

The following substrate is shared with existing DeerFlow runtime behavior:

- thread directory layout under `.deer-flow/threads/{thread_id}`
- sandbox provider acquisition keyed by `thread_id`
- `/mnt/user-data/*` path conventions
- ACP workspace conventions
- shared tool error and guardrail behavior where appropriate

The following remain team-runtime-local:

- phase model
- `ProjectBrief`
- canonical `WorkOrder`
- specialist roster
- approval gate logic
- QA gate logic
- delivery summary semantics

### 3. Graph Structure

M1 uses an explicit phase graph with these fixed phases:

- `intake`
- `discovery`
- `planning`
- `awaiting_approval`
- `build`
- `qa_gate`
- `delivery`
- `done`

The runtime behavior is phase-driven. The graph control plane owns all phase transitions and never relies on prompt inference for routing.

Required flow:

- `START -> intake -> discovery -> planning -> awaiting_approval`
- after user approval: `awaiting_approval -> build`
- after user revision feedback: `awaiting_approval -> planning`
- after all executable work orders complete: `build -> qa_gate`
- after QA pass: `qa_gate -> delivery`
- after QA fail: `qa_gate -> planning`
- `delivery -> done -> END`

The graph must support multi-turn execution through the existing thread/checkpointer model. Each new user turn re-enters the graph with persisted state, and routing is determined by persisted `phase` and `plan_status`.

### 4. Control Plane vs Execution Plane

M1 uses:

- graph-native control plane
- subagent-native execution plane

The outer `project_team_agent` graph does not expose prompt-driven free-form task delegation to itself.

Instead:

- graph nodes own phase logic
- a structured dispatcher selects specialists from canonical `WorkOrder.owner_agent`
- specialists execute through isolated `SubagentExecutor` runs
- specialists must not recursively orchestrate nested team runtimes

The build loop must only dispatch structured work orders. It must not fallback to the generic `task` tool or allow an outer orchestrator to invent additional unstructured work at runtime.

### 5. Shared Substrate Integration

Current DeerFlow runtime substrate is implemented through thread-aware paths, sandbox providers, and shared middleware behavior. `project_team_agent` must reuse the same substrate contracts, but it does not need to reuse the `lead_agent` middleware stack wholesale.

M1 implementation rule:

- the outer explicit graph owns project semantics
- phase-local executors and specialists reuse DeerFlow substrate initialization and tool environment
- `MemoryMiddleware` is never part of team runtime execution
- `task` tool is never exposed to project runtime planners or specialists

Because `StateGraph` itself does not carry `AgentMiddleware` the same way `create_agent()` does, M1 should treat substrate reuse as an execution-layer concern:

- the outer graph persists `ProjectThreadState`
- phase-local executors and specialists receive the active `thread_id`
- specialist runs use the same thread workspace and sandbox conventions as existing runtime behavior

### 6. Observability Boundary

`project_team_agent` must reuse the existing DeerFlow LangSmith tracing substrate when tracing is enabled through environment configuration.

Observability rules:

- tracing remains optional and environment-controlled
- enabling or disabling tracing must not change runtime semantics
- missing LangSmith configuration must only disable trace export, not runtime execution
- team-runtime-specific trace semantics must stay local to `project_team_agent` and must not alter default `lead_agent` behavior

## State And Persistence

### 1. Durable State Authority

M1 defines a dedicated state schema:

- `ProjectThreadState`

`ProjectThreadState` extends `ThreadState`, then adds team-runtime fields. The checkpointer remains the only durable authority.

`ProjectRepo` may exist only as a state access boundary over graph state patches. It must not become a second storage system.

M1 must not introduce:

- a second durable authority outside graph state
- a project repository database
- a new global project store namespace

### 2. Required State Fields

`ProjectThreadState` must include at least:

- `phase`
- `plan_status`
- `project_brief`
- `work_orders`
- `active_work_order_ids`
- `agent_reports`
- `qa_gate`
- `delivery_summary`

It also inherits existing thread-level state such as:

- `messages`
- `thread_data`
- `sandbox`
- `artifacts`

### 3. Canonical Types

`ProjectBrief`

- `objective`
- `scope`
- `constraints`
- `deliverables`
- `success_criteria`

`WorkOrder`

- `id`
- `owner_agent`
- `title`
- `goal`
- `read_scope`
- `write_scope`
- `dependencies`
- `acceptance_checks`
- `status`

`AgentReport`

- `work_order_id`
- `agent_name`
- `summary`
- `changes`
- `risks`
- `verification`

`PlanStatus`

- `draft`
- `awaiting_approval`
- `approved`
- `needs_revision`

`QAGateResult`

- `pass`
- `fail`
- `blocked`

`QAGate` payload also includes:

- `findings`
- `required_rework`

### 4. Memory Isolation

Global long-term memory and team runtime must remain isolated.

Rules:

- `project_team_agent` does not inject global memory into its runtime prompts
- `project_team_agent` does not enqueue memory updates
- `ProjectBrief`, `WorkOrder`, QA findings, and specialist reports must never be written into long-term memory
- durable team state exists only in `ProjectThreadState`

## Observability And Traceability

M1 must emit LangSmith traces for project-runtime model calls whenever DeerFlow tracing is enabled.

### 1. Top-Level Runtime Trace Metadata

Top-level `project_team_agent` runs must attach metadata that allows filtering and diagnosis across multi-turn execution:

- `runtime=project_team`
- `thread_id`
- `phase`
- `plan_status`
- `project_runtime_version`

### 2. Specialist And QA Trace Metadata

Each specialist and QA execution must attach metadata that allows execution-level diagnosis:

- `runtime=project_team`
- `thread_id`
- `phase`
- `work_order_id`
- `owner_agent`
- `execution_kind`

`execution_kind` must distinguish at least:

- `build_specialist`
- `qa_check`

### 3. Trace Context Propagation

M1 must propagate a single parent `trace_id` from the top-level project runtime into all specialist and QA subagent executions.

This trace context is required so that:

- one project-runtime execution can be correlated across planning, build, QA, and delivery
- specialist runs can be grouped by work order
- QA checks can be correlated to the work order and report they validate

### 4. Persistence And Isolation

Trace metadata is observability data, not durable project state.

Rules:

- trace export must not introduce a second durable authority
- trace payloads do not need to be persisted inside `ProjectThreadState`
- `ProjectBrief`, `WorkOrder`, QA findings, and delivery summaries must not be copied into long-term memory for observability purposes
- observability integration must not require gateway or frontend changes for M1

## Runtime Behavior And Public Interfaces

### 1. Public Entry Points

M1 adds a separate graph:

- `project_team_agent`

Client exposure has two surfaces:

- LangGraph Server surface: select `assistant_id="project_team_agent"`
- embedded Python client surface: use project-runtime-specific thin wrappers in `deerflow.client`

The client wrapper must preserve existing `chat` / `stream` contracts and only change graph targeting.

Minimal wrapper interface:

- `project_chat(message, *, thread_id=None, **kwargs)`
- `project_stream(message, *, thread_id=None, **kwargs)`

For the embedded client implementation, this means local graph targeting rather than literally passing an `assistant_id`.

M1 must not add:

- `create_project`
- project CRUD API
- frontend project list or team list

Thread lifecycle remains the existing DeerFlow thread lifecycle.

### 2. Runtime Trace Integration

Project runtime execution must attach runtime metadata before planner, build, QA, and delivery model invocations.

Implementation rules:

- the project runtime graph attaches top-level runtime metadata
- the structured dispatcher propagates active trace context into specialist execution
- QA acceptance checks propagate the same trace context model as build-phase specialist execution
- trace tagging must distinguish planning, specialist execution, QA gate, and delivery summary generation

### 3. Specialist Roster

M1 includes a fixed delivery team roster:

- `discovery-agent`
- `architect-agent`
- `planner-agent`
- `design-agent`
- `frontend-agent`
- `backend-agent`
- `integration-agent`
- `devops-agent`
- `data-agent`
- `qa-agent`
- `delivery-agent`
- `general-purpose`
- `bash`

Phase mapping:

- `discovery`: `discovery-agent`, `architect-agent`, `design-agent`
- `planning`: `planner-agent`
- `build`: `frontend-agent`, `backend-agent`, `integration-agent`, `devops-agent`, `data-agent`, `design-agent`
- `qa_gate`: `qa-agent`
- `delivery`: `delivery-agent`

`general-purpose` and `bash` are fallback specialists only. They are not default phase owners.

The project runtime owns a local specialist registry. It must not modify the core built-in subagent registry.

### 4. Approval UX

M1 uses in-conversation approval.

After canonical work orders are generated, the runtime enters `awaiting_approval` and only accepts these intents:

- `/approve`
- `/revise ...`
- `/cancel`

Compatibility rules:

- natural-language revision feedback is treated as `revise`
- ambiguous replies never start `build`
- if approval is unclear, remain in `awaiting_approval` and ask for a clearer response

Default policy is conservative:

- no explicit approval
- no build

### 5. ACP Policy

ACP remains a core capability, not a team-runtime subsystem.

M1 policy:

- team runtime must work without ACP
- ACP exposure is controlled by specialist tool allowlists
- `planner-agent` and `qa-agent` do not depend on ACP by default
- ACP may be allowed for `frontend-agent`, `backend-agent`, or `integration-agent` if explicitly configured

## Implementation Requirements

### 1. Graph Implementation

Add a new graph factory under `project_runtime` that compiles an explicit `StateGraph` over `ProjectThreadState`.

Implementation properties:

- phase transitions are represented in graph code
- no phase routing via prompt inference
- checkpointer persistence uses the existing DeerFlow checkpointer infrastructure
- graph re-entry after each turn is based on persisted `phase` and `plan_status`

### 2. Planning Output

The planning phase must emit canonical structured work orders.

Requirements:

- planner output is validated against the canonical schema
- invalid planner output is rejected at planning time
- the runtime does not silently continue with malformed work orders

### 3. Build Dispatch

The build phase must schedule only runnable work orders:

- dependencies satisfied
- not already completed
- not currently active

Each dispatched specialist receives:

- the canonical work order
- current `ProjectBrief`
- relevant prior reports
- the active DeerFlow `thread_id`

Each specialist returns a structured `AgentReport` recorded in runtime state.

### 4. QA Gate

`qa_gate` consumes accumulated reports and returns a canonical QA result:

- `pass`
- `fail`
- `blocked`

If QA fails:

- required rework is translated back into plan/build state
- runtime returns to `planning`

If QA passes:

- runtime proceeds to `delivery`

### 5. Delivery

The delivery phase produces a concise final summary that includes:

- completed work
- notable artifacts or file outputs
- verification status
- outstanding risks or follow-ups

Then the runtime sets `phase="done"` and terminates.

## Test Plan

Required tests:

- `lead_agent` graph, prompt, and default tool behavior remain unchanged when `project_team_agent` is not selected
- `project_team_agent` follows the exact phase flow `intake -> discovery -> planning -> awaiting_approval -> build -> qa_gate -> delivery -> done`
- planner output must conform to canonical `WorkOrder` schema
- `awaiting_approval` never enters `build` without explicit approval
- `revise` returns to `planning`
- `cancel` terminates the runtime flow without entering `build`
- build dispatch only consumes structured `WorkOrder` items
- work order dependency handling, status transitions, retry handling, and QA rework loops are recoverable through the checkpointer
- after restoration from checkpointer, the thread resumes with the correct `phase` and `plan_status`
- team runtime never writes `ProjectBrief`, work orders, or reports into long-term memory
- specialists remain thread-isolated and cannot read or overwrite another thread's runtime outputs
- runtime works when ACP is not configured
- when ACP is configured, only explicitly allowed specialists can use it
- harness/app boundary tests continue to pass and core modules do not import project-runtime semantics accidentally
- project client wrappers preserve the existing `chat` / `stream` contract and only alter graph targeting

## Assumptions And Defaults

- implementation baseline is `origin/main`
- M1 is a backend runtime only
- explicit graph is the control plane
- `ProjectThreadState + checkpointer` is the sole durable authority
- no new global project store is introduced
- full delivery-team roster exists only inside `project_runtime`
- default policy is `plan first, wait for approval, then execute`
- prompt-driven orchestration is not the primary control mechanism
- outer graph does not depend on the `lead_agent` middleware stack
- execution-layer substrate reuse is sufficient for M1 as long as specialists keep the same thread workspace and sandbox conventions
