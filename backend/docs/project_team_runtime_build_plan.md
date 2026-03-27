# Project Team Runtime M1 Build Plan

## 1. Document Goal

This document turns the M1 PRD into an implementation-ready backend build plan for DeerFlow.

Scope:

- backend runtime only
- explicit `StateGraph` control plane
- TDD-first delivery
- no default behavior change to `lead_agent`

This plan is written against the current repository state on `origin/main` semantics, while using the local PRD draft as the primary source of truth.

## 2. Source Of Truth

Primary inputs:

- `backend/docs/project_team_runtime_prd.md`
- `backend/CLAUDE.md`
- `backend/README.md`
- `https://zeljkoavramovic.github.io/agentic-design-patterns/`

Implementation baseline observed in the repository:

- `backend/langgraph.json` currently exposes only `lead_agent`
- `deerflow.client.DeerFlowClient` currently builds only the lead-agent runtime path
- `ThreadState` already carries thread sandbox and artifact substrate
- `SubagentExecutor` already supports isolated thread-aware specialist execution
- tool assembly currently exposes `task` only through `subagent_enabled`

## 3. Hard Constraints

These constraints are non-negotiable. Any implementation that violates them is out of scope for M1.

### 3.1 Runtime Boundary

- Add a new graph named `project_team_agent`
- Keep default `lead_agent` graph, prompt, middleware meaning, and tool behavior unchanged
- Keep gateway and frontend behavior unchanged unless the caller explicitly targets `project_team_agent`

### 3.2 Persistence Boundary

- `ProjectThreadState + checkpointer` is the only durable authority
- No second database, project store, board state, or CRUD layer
- Recovery must rely on persisted graph state, not sidecar runtime memory

### 3.3 Orchestration Boundary

- The outer runtime is an explicit graph, not a prompt-driven manager
- Build work must come only from canonical `WorkOrder` records
- The runtime must not fall back to generic unstructured delegation
- Specialists must not recursively create nested team runtimes

### 3.4 Tool And Middleware Boundary

- `MemoryMiddleware` must never participate in project runtime execution
- `task` must never be exposed to project-runtime planners or specialists
- ACP must be optional and allowlisted per specialist
- Thread sandbox and path conventions must be reused exactly as they work today

### 3.5 UX Boundary

- `build` requires in-conversation approval
- `/approve` starts build
- `/revise ...` returns to planning
- `/cancel` terminates without build
- Ambiguous user replies never start build

### 3.6 Scope Exclusions

- No project CRUD API
- No frontend project list, board, or control plane
- No new global project namespace
- No memory write-back for project runtime concepts

## 4. Current-State Gap Analysis

### 4.1 What Already Exists And Can Be Reused

- `ThreadState` already models `messages`, `sandbox`, `thread_data`, and `artifacts`
- `SubagentExecutor` already accepts `thread_id`, `sandbox_state`, and `thread_data`
- Shared runtime middleware builders already separate lead runtime and subagent runtime substrate
- Existing checkpointer providers already support sync and async graph persistence
- Existing client streaming contract already matches LangGraph event shapes

### 4.2 What Is Missing

- No `project_runtime` package
- No `ProjectThreadState`
- No canonical `ProjectBrief`, `WorkOrder`, `AgentReport`, or `QAGate` types
- No fixed specialist registry owned by project runtime
- No project-runtime-specific tool filtering policy
- No explicit graph for `intake -> discovery -> planning -> awaiting_approval -> build -> qa_gate -> delivery -> done`
- No project-specific client wrappers
- No tests for approval gating, schema validation, QA rework loops, or checkpointer recovery for team runtime

### 4.2a What Is Already Landed In The Repository Now

- `project_runtime` package exists
- `ProjectThreadState`, specialist registry, graph topology, approval gate, build dispatcher, QA gate, and project client wrappers exist
- build specialists already dispatch through `SubagentExecutor`
- executable QA checks already dispatch through `qa-agent`

### 4.2b Remaining Gap After The First Landing

- `discovery`, `planning`, and `delivery` still needed real phase-specialist execution
- phase outputs still needed canonical JSON parsing plus validation before state mutation
- runtime still needed an explicit compatibility rule for deterministic fallback
- docs still overstated specialist readiness by treating registry presence as execution readiness

### 4.3 Immediate Design Implication

M1 should be implemented as a parallel runtime path that reuses execution substrate but owns its own state, graph, registry, prompts, policies, and tests.

## 5. Pattern Mapping

The external design-pattern reference is useful only where it sharpens implementation decisions.

### 5.1 Spec-First Agent

Use the PRD and canonical runtime schema as the hard contract.

Implementation consequence:

- planner output must be structured and validated before state mutation
- invalid work orders are rejected immediately
- QA output must also be canonical and machine-checkable

### 5.2 Planning

Planning is the first-class control mechanism.

Implementation consequence:

- work begins only after a validated plan exists
- `WorkOrder.dependencies` drive dispatch eligibility
- replanning is an explicit graph transition, not an agent improvisation

### 5.3 Routing

Routing maps work orders to specialists.

Implementation consequence:

- the runtime owns a deterministic `owner_agent -> specialist config` mapping
- fallback specialists exist, but only as explicit fallback, not default owners

### 5.4 Multi-Agent Collaboration

Specialists are execution workers, not co-managers.

Implementation consequence:

- orchestration stays in graph code
- specialists receive scoped inputs and return structured reports
- shared durable context lives in `ProjectThreadState`

### 5.5 Human-In-The-Loop

Approval is a deliberate runtime gate.

Implementation consequence:

- no approval means no build
- the approval parser must be conservative
- revision feedback becomes structured state transition input

### 5.6 Stop Hook

`qa_gate` is the runtime-level stop hook before delivery.

Implementation consequence:

- no direct `build -> delivery`
- QA must produce actionable rework payloads
- QA failure routes back to planning instead of producing a soft warning

### 5.7 Exception Handling And Recovery

Failure handling must be graph-native and checkpointer-safe.

Implementation consequence:

- dispatch state must survive process interruption
- partial build progress must be resumable
- QA rework loops must preserve prior reports and statuses

### 5.8 Session Isolation

Specialists must stay isolated at the thread runtime boundary.

Implementation consequence:

- the runtime reuses existing thread sandbox conventions
- no specialist may escape its thread workspace
- cross-thread read or write access must remain impossible

## 6. Target Architecture

## 6.1 New Package Layout

Create a dedicated package:

`backend/packages/harness/deerflow/project_runtime`

Recommended file layout:

| File | Responsibility |
|---|---|
| `__init__.py` | Export `make_project_team_agent` and public runtime types |
| `types.py` | Canonical enums and structured payload models |
| `state.py` | `ProjectThreadState`, reducers, state helpers |
| `registry.py` | Fixed specialist roster, phase ownership, ACP and tool policy |
| `prompts.py` | Runtime-local prompts for discovery, planning, QA, delivery |
| `planning.py` | Discovery and planning helpers, structured planner validation |
| `approval.py` | Intent parsing for `/approve`, `/revise`, `/cancel` |
| `dispatcher.py` | Runnable work-order selection, dispatch, status transition logic |
| `qa.py` | QA aggregation, deterministic checks, canonical QA result generation |
| `delivery.py` | Final delivery summary assembly |
| `graph.py` | Explicit `StateGraph` factory and phase routing |

This layout keeps team semantics local while allowing deterministic unit testing per module.

## 6.2 Canonical Types

Use strongly typed runtime-local models for all project semantics.

Required payloads:

- `ProjectBrief`
- `WorkOrder`
- `AgentReport`
- `QAGate`
- `Phase`
- `PlanStatus`
- `WorkOrderStatus`
- `QAGateResult`

Recommended field additions beyond the PRD minimum:

- `WorkOrderStatus`: `pending`, `ready`, `active`, `completed`, `failed`, `blocked`, `cancelled`
- `AgentReport.verification`: list-shaped payload, not free text only
- `QAGate.required_rework`: list of work-order patch instructions or new work-order intents

## 6.3 ProjectThreadState

`ProjectThreadState` should extend `ThreadState` and add at least:

- `phase`
- `plan_status`
- `project_brief`
- `work_orders`
- `active_work_order_ids`
- `agent_reports`
- `qa_gate`
- `delivery_summary`
- `phase_artifacts`
- `phase_attempts`

Recommended additional fields for implementation clarity:

- `project_runtime_version`
- `approval_state`
- `phase_history`
- `last_user_intent`
- `planner_attempt_count`
- `qa_attempt_count`

These additions remain inside graph state and do not create a second persistence system.

## 6.4 Graph Nodes

### `intake`

Purpose:

- normalize runtime defaults
- seed initial project-runtime state
- preserve the triggering user message in standard thread history

Output:

- initialized `phase`
- initialized `plan_status`
- empty canonical collections

### `discovery`

Purpose:

- synthesize a draft `ProjectBrief`
- identify assumptions, constraints, and missing context
- use discovery-facing specialists only when needed

Output:

- canonical `ProjectBrief`
- discovery-phase `AgentReport` entries if specialists were used
- `phase_artifacts.discovery`
- incremented `phase_attempts.discovery`

### `planning`

Purpose:

- produce canonical `WorkOrder[]`
- validate owner assignment, dependencies, and acceptance checks
- reject malformed planner output before state update

Output:

- validated `work_orders`
- `plan_status="awaiting_approval"`
- `phase="awaiting_approval"`
- `phase_artifacts.planning`
- incremented `phase_attempts.planning`

### `awaiting_approval`

Purpose:

- parse user approval intent conservatively
- gate any transition into build

Output:

- `/approve` -> `phase="build"`, `plan_status="approved"`
- `/revise` -> `phase="planning"`, `plan_status="needs_revision"`
- `/cancel` -> terminate without build
- ambiguous input -> remain in `awaiting_approval`

### `build`

Purpose:

- dispatch runnable work orders only
- record active work orders
- collect structured `AgentReport` results

Output:

- updated work-order statuses
- accumulated reports
- `phase="qa_gate"` once all executable work is completed

### `qa_gate`

Purpose:

- aggregate reports and acceptance checks
- run deterministic verification where possible
- return canonical QA result

Output:

- `pass` -> `phase="delivery"`
- `fail` -> `phase="planning"`
- `blocked` -> remain recoverable with explicit state

### `delivery`

Purpose:

- produce the final concise delivery summary
- list completed work, artifacts, verification, and follow-ups

Output:

- `delivery_summary`
- `phase="done"`
- `phase_artifacts.delivery`
- incremented `phase_attempts.delivery`

## 6.5 Specialist Registry And Policy

The specialist registry must live entirely inside `project_runtime.registry`.

Fixed roster:

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

Default phase owners:

| Phase | Default specialists |
|---|---|
| `discovery` | `discovery-agent`, `architect-agent`, `design-agent` |
| `planning` | `planner-agent` |
| `build` | `frontend-agent`, `backend-agent`, `integration-agent`, `devops-agent`, `data-agent`, `design-agent` |
| `qa_gate` | `qa-agent` |
| `delivery` | `delivery-agent` |

Policy rules:

- `general-purpose` and `bash` are fallback specialists only
- `planner-agent` and `qa-agent` must not depend on ACP by default
- `task` is always denied
- ACP exposure is opt-in per specialist

Recommended initial tool policy:

| Specialist class | Default policy |
|---|---|
| discovery, architect, planner | read-only file tools, selected web/MCP tools, no ACP, no `task` |
| design | read-heavy in discovery, write-enabled in build, no `task` |
| frontend, backend, integration, devops, data | file read/write, bash, selected MCP, ACP only if allowlisted |
| qa | read-only plus deterministic verification tools, no ACP by default |
| delivery | read-only plus `present_files`, no ACP |

## 6.6 Runtime Tool Assembly

Do not reuse `get_available_tools()` unchanged for project runtime because its default behavior is lead-runtime-centric.

Add a runtime-local tool assembly helper that:

- starts from existing substrate tools
- strips `task`
- strips any tool not allowed by the specialist policy
- includes ACP only when both global config and specialist policy allow it
- can include `present_files` only where it is useful

This should be a wrapper over existing tool assembly, not a fork of the core tool system.

Compatibility rule:

- `discovery`, `planning`, and `delivery` execute specialists first
- if specialist execution fails and `allow_deterministic_phase_fallback=true`, runtime falls back to deterministic synthesis
- if specialist execution fails and fallback is disabled, the phase fails fast

## 7. TDD Strategy

The implementation should follow a fixed loop for every milestone.

### 7.1 Mandatory Loop

1. Write focused failing tests for one behavior slice
2. Implement the minimum code needed to make them pass
3. Refactor only after green
4. Re-run targeted tests
5. Run the full backend test suite at milestone boundaries

### 7.2 Test Style

- Prefer pure unit tests for `types`, `state`, `approval`, `registry`, and dispatcher selection logic
- Use controlled integration tests for graph routing and client wrapper behavior
- Mock specialist execution aggressively unless the test specifically targets `SubagentExecutor` integration
- Keep recovery tests checkpointer-backed and deterministic

### 7.3 Definition Of A Good Test Slice

A slice is acceptable when it covers one of:

- one graph transition
- one schema validation rule
- one dispatch eligibility rule
- one recovery rule
- one public wrapper contract

## 8. Milestone Plan

## M0. Regression Fences

Goal:

- prove that selecting nothing new keeps current behavior intact

Tests first:

- `backend/tests/test_project_runtime_regression.py`

Required assertions:

- `lead_agent` registration remains present
- default lead-agent prompt path is unchanged
- default tool behavior is unchanged when `project_team_agent` is not targeted
- harness/app import boundary still holds

Implementation:

- add empty `project_runtime` package scaffold
- export nothing beyond placeholders

Exit criteria:

- no production behavior changes
- new scaffolding compiles

## M1. Contracts And State

Goal:

- establish canonical project-runtime data contracts

Tests first:

- `backend/tests/test_project_runtime_types.py`
- `backend/tests/test_project_runtime_state.py`

Required assertions:

- valid `ProjectBrief` and `WorkOrder` payloads parse successfully
- malformed planner output is rejected
- `ProjectThreadState` defaults are stable
- reducers preserve artifact behavior inherited from `ThreadState`

Implementation:

- add `types.py`
- add `state.py`
- export runtime types in `__init__.py`

Exit criteria:

- the runtime can represent all PRD state without graph code

## M2. Registry And Policy

Goal:

- encode the specialist roster and policy locally

Tests first:

- `backend/tests/test_project_runtime_registry.py`

Required assertions:

- roster matches PRD exactly
- phase ownership matches PRD exactly
- fallback specialists are not default phase owners
- ACP defaults are conservative
- `task` is always filtered out

Implementation:

- add `registry.py`
- add runtime-local tool policy helpers

Exit criteria:

- specialist resolution is deterministic and testable

## M3. Graph Shell

Goal:

- compile an explicit `StateGraph` with the required phase topology

Tests first:

- `backend/tests/test_project_runtime_graph.py`

Required assertions:

- graph compiles with `ProjectThreadState`
- exact phase flow exists
- unsupported transitions do not occur

Implementation:

- add `graph.py`
- register `project_team_agent` in `backend/langgraph.json`

Exit criteria:

- graph can be instantiated and routed even with placeholder node bodies

## M4. Discovery And Planning

Goal:

- produce validated canonical plans

Tests first:

- `backend/tests/test_project_runtime_planning.py`

Required assertions:

- discovery produces canonical `ProjectBrief`
- planning produces canonical `WorkOrder[]`
- malformed planner output is rejected
- invalid dependencies are rejected
- work orders without acceptance checks are either rejected or normalized by explicit rule

Implementation:

- add `prompts.py`
- add `planning.py`
- implement `discovery` and `planning` node logic

Exit criteria:

- runtime reaches `awaiting_approval` only with validated work orders

## M5. Approval Gate

Goal:

- implement conservative build gating

Tests first:

- `backend/tests/test_project_runtime_approval.py`

Required assertions:

- `/approve` starts build
- `/revise ...` returns to planning
- natural-language revision feedback is treated as revise
- `/cancel` terminates without build
- ambiguous replies stay in `awaiting_approval`

Implementation:

- add `approval.py`
- implement awaiting-approval node behavior

Exit criteria:

- no path exists from planning to build without explicit approval state

## M6. Build Dispatcher

Goal:

- dispatch only runnable work orders and capture reports

Tests first:

- `backend/tests/test_project_runtime_dispatcher.py`

Required assertions:

- only dependency-satisfied work orders are dispatched
- active or completed work orders are skipped
- specialist inputs contain `ProjectBrief`, `WorkOrder`, prior reports, and `thread_id`
- every successful execution yields a structured `AgentReport`
- invalid owner agent names are rejected before dispatch

Implementation:

- add `dispatcher.py`
- integrate `SubagentExecutor` with runtime-local specialist configs

Recommended delivery order:

- implement serial dispatch first
- add bounded parallel dispatch only after serial correctness is green

Exit criteria:

- build state transitions are deterministic and recoverable

## M7. QA Gate And Delivery

Goal:

- block bad builds from delivery and close the runtime cleanly

Tests first:

- `backend/tests/test_project_runtime_qa.py`
- `backend/tests/test_project_runtime_delivery.py`

Required assertions:

- QA returns only `pass`, `fail`, or `blocked`
- QA fail returns to planning with actionable rework payload
- QA pass proceeds to delivery
- delivery summary contains completed work, artifacts, verification, and follow-ups

Implementation:

- add `qa.py`
- add `delivery.py`
- complete `qa_gate` and `delivery` nodes

Exit criteria:

- the runtime can finish end-to-end with a canonical summary

## M8. Recovery, Client, And Config

Goal:

- expose the runtime cleanly and make recovery production-safe

Tests first:

- `backend/tests/test_project_runtime_recovery.py`
- `backend/tests/test_project_runtime_client.py`
- `backend/tests/test_project_runtime_config.py`

Required assertions:

- persisted `phase` and `plan_status` resume correctly after restore
- active work-order recovery does not duplicate completed work
- `project_chat` and `project_stream` preserve the existing `chat` and `stream` contract
- ACP-off runtime works
- ACP-on runtime respects specialist allowlists

Implementation:

- add `project_chat()` and `project_stream()` wrappers in `deerflow.client`
- add minimal config surface in `config.example.yaml`
- wire graph targeting into local client helpers

Exit criteria:

- project runtime is externally selectable without disturbing default paths

## M9. Documentation And Final Verification

Goal:

- document the runtime after behavior is real

Required work:

- update `backend/README.md` if user-facing backend entry points changed
- update `backend/CLAUDE.md` for architecture and workflow changes
- add or update docs index once local doc changes are safe to merge
- run `make test`

Exit criteria:

- docs match the actual implementation
- full backend suite is green

## 9. Test Matrix

| Requirement | Primary tests |
|---|---|
| `lead_agent` remains unchanged by default | `test_project_runtime_regression.py`, existing lead-agent tests |
| exact phase flow | `test_project_runtime_graph.py` |
| planner schema validity | `test_project_runtime_planning.py` |
| approval gate is conservative | `test_project_runtime_approval.py` |
| cancel never enters build | `test_project_runtime_approval.py` |
| dispatch consumes only structured work orders | `test_project_runtime_dispatcher.py` |
| dependency handling and retries are recoverable | `test_project_runtime_dispatcher.py`, `test_project_runtime_recovery.py` |
| checkpointer restore resumes correctly | `test_project_runtime_recovery.py` |
| no long-term memory write-back | `test_project_runtime_regression.py` or dedicated memory-isolation test |
| thread isolation | `test_project_runtime_dispatcher.py` with multiple thread IDs |
| ACP optionality and allowlists | `test_project_runtime_registry.py`, `test_project_runtime_config.py` |
| client wrappers preserve contract | `test_project_runtime_client.py`, existing client conformance patterns |
| harness/app boundary remains intact | existing `test_harness_boundary.py` |

## 10. Recommended File-Level Implementation Order

1. `project_runtime/types.py`
2. `project_runtime/state.py`
3. `project_runtime/registry.py`
4. `project_runtime/graph.py`
5. `project_runtime/planning.py`
6. `project_runtime/approval.py`
7. `project_runtime/dispatcher.py`
8. `project_runtime/qa.py`
9. `project_runtime/delivery.py`
10. `project_runtime/__init__.py`
11. `backend/langgraph.json`
12. `deerflow.client`
13. `config.example.yaml`

This order keeps contracts ahead of orchestration and keeps public integration last.

## 11. Engineering Decisions To Lock Early

These choices should be made before implementation spreads across multiple files.

### 11.1 Type System

Recommendation:

- use strongly typed runtime models with validation at the edge
- keep graph state payloads machine-checkable

Reason:

- planner and QA are both contract-producing nodes
- loose dicts will make recovery and tests fragile

### 11.2 Planner Output Shape

Recommendation:

- require structured planner output with explicit `owner_agent`, `dependencies`, and `acceptance_checks`

Reason:

- build dispatch and QA both depend on this payload

### 11.3 Build Concurrency

Recommendation:

- implement serial dispatch first
- add bounded parallel dispatch only after state transitions and recovery are correct

Reason:

- concurrency bugs in graph state are harder to debug than specialist prompt bugs

### 11.4 QA Composition

Recommendation:

- combine deterministic checks with `qa-agent` synthesis

Reason:

- deterministic checks catch objective breakage
- the QA specialist can still summarize risks and missing follow-up

### 11.5 Tool Policy Location

Recommendation:

- keep specialist tool policy in `project_runtime.registry`

Reason:

- policy is team-runtime semantics, not global substrate semantics

## 12. Risks And Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| planner output drifts from schema | invalid build dispatch | validate before state write, fail fast |
| dispatch concurrency corrupts active state | duplicate work or lost updates | start serial, add bounded parallelism later |
| QA becomes purely subjective | unstable rework loops | require canonical QA result plus deterministic checks |
| ACP leaks into unintended specialists | policy violation | central allowlist in runtime-local registry |
| graph recovery replays finished work | wasted execution and inconsistent reports | persist work-order status transitions explicitly |
| memory integration happens accidentally | cross-runtime contamination | ensure project runtime never uses `MemoryMiddleware` |

## 13. Definition Of Done

M1 is complete only when all of the following are true:

- `project_team_agent` exists and is selectable
- default `lead_agent` behavior is unchanged
- `ProjectThreadState` is the only durable authority for team runtime state
- planner output is canonical and validated
- build requires explicit approval
- specialists run through isolated `SubagentExecutor` flows with runtime-local tool policy
- QA failure returns to planning with actionable rework
- delivery produces a canonical final summary
- recovery through the checkpointer works across phase boundaries
- runtime does not write project semantics into long-term memory
- ACP remains optional and allowlisted
- full backend tests pass

## 14. Suggested First Implementation Slice

The safest first slice is:

1. `M0`
2. `M1`
3. `M3`

Reason:

- it freezes current behavior
- it creates the durable contracts before prompt work
- it makes phase routing testable before specialist execution exists

After that, implement `M4 -> M5 -> M6 -> M7 -> M8 -> M9` in order.
