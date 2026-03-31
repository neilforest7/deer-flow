# Project Team Frontend Integration Plan

**Status**: ✅ Complete
**Created**: 2026-03-30
**Last Updated**: 2026-03-31
**Target**: Expose project_team runtime to frontend with dedicated UI

## Progress Summary

### ✅ Completed
- **Week 1: Backend API** - All endpoints implemented and tested
  - Created `app/gateway/routers/projects.py` with 6 endpoints
  - Wrote comprehensive test suite (9 tests, all passing)
  - Registered router in Gateway application
  - Commit: `1cdecd5`
  - **Bug fixes (2026-03-31)** - Critical deployment issues resolved:
    - Fixed database path: Changed from hardcoded `/app/backend/.deer-flow/langgraph.db` to config-based `{config.deer_flow_home}/checkpoints.db`
    - Fixed LangGraph URL: Changed from `http://localhost:2024` to `http://langgraph:2024` for Docker service resolution
    - Fixed metadata field: Changed filter from `metadata.assistant_id` to `metadata.graph_id` (correct LangGraph schema)
    - Removed unused `get_checkpointer()` function
    - Removed duplicate return statement
    - Commits: `6762693`, `6011450`

- **Week 2: Frontend Data Layer** - Types, API client, and hooks ready
  - Created `src/core/projects/types.ts` with all type definitions
  - Created `src/core/projects/api.ts` with API client functions
  - Created `src/core/projects/hooks.ts` with React Query hooks (5s polling)
  - Commit: `4f58105`

- **Week 3: UI Foundation** - Sidebar tabs and project list complete
  - Created `workspace-tabs.tsx` for Chats/Projects tab switcher
  - Created `project-list.tsx` with phase badges and navigation
  - Created `create-project-dialog.tsx` with objective input
  - Added `/workspace/projects` list page
  - Added `/workspace/projects/[thread_id]` dashboard page
  - Modified `workspace-sidebar.tsx` to integrate tabs and conditional rendering

- **Week 4: Dashboard Core** - Approval interface and overview tab complete
  - Created `approval-section.tsx` with approve/revise/cancel actions
  - Created `revise-dialog.tsx` for plan revision feedback
  - Created `overview-tab.tsx` displaying project brief details
  - Updated dashboard page with tabs navigation (Overview/Work Orders/Specialists)
  - Integrated approval section for awaiting_approval phase

- **Week 5: Dashboard Details** - Work orders and specialists tabs complete
  - Created `work-orders-tab.tsx` displaying work orders with status badges
  - Created `specialists-tab.tsx` with accordion layout for agent reports
  - Created `phase-progress.tsx` visual progress indicator
  - Integrated all tabs into dashboard page
  - Added Accordion component from shadcn

### 🚧 In Progress
- None - All planned features complete

### 📅 Planned
- **Week 4: Dashboard Core** - Approval interface and overview tab
- **Week 5: Dashboard Details** - Work orders and specialists tabs

## Overview

This plan outlines the implementation of a frontend interface for the `project_team_agent` runtime, providing users with a dedicated project management dashboard alongside the existing chat interface.

## Technical Decisions

### Architecture Choices

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Entry Point** | Left sidebar top tabs (Chats/Projects) | Maintains UI consistency, easy navigation |
| **Data Source** | Query LangGraph checkpointer directly | Simple architecture, no new storage layer |
| **Real-time Updates** | Polling every 5-10 seconds | Balance between freshness and server load |
| **Permissions** | No access control (all users see all projects) | MVP simplicity |
| **Project Creation** | "New Project" button in Projects tab | Clear, dedicated entry point |
| **Dashboard Features** | Phase/status + approval + work orders + specialists | Complete project visibility |
| **Approval Interaction** | Modal dialog for revision feedback | Focused user experience |

### Technology Stack

**Backend**:
- FastAPI (existing gateway)
- LangGraph checkpointer (data source)
- Project runtime types from `deerflow.project_runtime`

**Frontend**:
- Next.js 16 + React 19 + TypeScript 5.8
- TanStack Query (data fetching + caching)
- Shadcn UI components (consistent design)
- Tailwind CSS 4 (styling)

## Implementation Phases

### Phase 1: Backend API (Week 1)

#### 1.1 New API Endpoints

**File**: `backend/packages/gateway/deerflow_gateway/routes/projects.py` (new)

```python
# Endpoints to implement:
GET    /api/projects                      # List all projects
GET    /api/projects/{thread_id}          # Get project detail
POST   /api/projects                      # Create new project
POST   /api/projects/{thread_id}/approve  # Approve plan
POST   /api/projects/{thread_id}/revise   # Revise plan with feedback
POST   /api/projects/{thread_id}/cancel   # Cancel project
```

**Implementation Notes**:
- Query checkpointer for all threads with `assistant_id="project_team_agent"`
- Extract project title from `project_brief.objective` (fallback: "Untitled Project")
- Approval operations send messages (`/approve`, `/revise <feedback>`, `/cancel`) to thread
- Return full `ProjectThreadState` for detail endpoint

#### 1.2 Response Schemas

**Project List Item**:
```json
{
  "id": "thread-123",
  "title": "User Authentication System",
  "phase": "awaiting_approval",
  "plan_status": "awaiting_approval",
  "created_at": "2026-03-30T10:00:00Z",
  "updated_at": "2026-03-30T14:30:00Z"
}
```

**Project Detail**:
```json
{
  "id": "thread-123",
  "title": "User Authentication System",
  "phase": "awaiting_approval",
  "plan_status": "awaiting_approval",
  "created_at": "2026-03-30T10:00:00Z",
  "updated_at": "2026-03-30T14:30:00Z",
  "project_brief": {
    "objective": "Build user authentication system",
    "scope": ["Login", "Registration", "Password reset"],
    "constraints": ["Must use JWT", "GDPR compliant"],
    "deliverables": ["Auth API", "Frontend components"],
    "success_criteria": ["All tests pass", "Security audit clean"]
  },
  "work_orders": [
    {
      "id": "wo-1",
      "owner_agent": "backend-agent",
      "title": "Implement JWT authentication",
      "goal": "Create secure JWT-based auth",
      "read_scope": ["src/auth/"],
      "write_scope": ["src/auth/jwt.py"],
      "dependencies": [],
      "acceptance_checks": ["Unit tests pass"],
      "status": "pending"
    }
  ],
  "agent_reports": [],
  "qa_gate": null,
  "delivery_summary": null,
  "phase_artifacts": {}
}
```

### Phase 2: Frontend Data Layer (Week 2)

#### 2.1 Type Definitions

**File**: `src/core/projects/types.ts` (new)

```typescript
export type Phase =
  | 'intake'
  | 'discovery'
  | 'planning'
  | 'awaiting_approval'
  | 'build'
  | 'qa_gate'
  | 'delivery'
  | 'done'

export type PlanStatus =
  | 'draft'
  | 'awaiting_approval'
  | 'approved'
  | 'needs_revision'

export interface Project {
  id: string
  title: string
  phase: Phase
  plan_status: PlanStatus
  created_at: string
  updated_at: string
}

export interface ProjectBrief {
  objective: string
  scope: string[]
  constraints: string[]
  deliverables: string[]
  success_criteria: string[]
}

export interface WorkOrder {
  id: string
  owner_agent: string
  title: string
  goal: string
  read_scope: string[]
  write_scope: string[]
  dependencies: string[]
  acceptance_checks: string[]
  status: 'pending' | 'active' | 'completed' | 'failed'
}

export interface AgentReport {
  work_order_id: string
  agent_name: string
  summary: string
  changes: string[]
  risks: string[]
  verification: string[]
}

export interface QAGate {
  result: 'pass' | 'fail' | 'blocked'
  findings: string[]
  required_rework: string[]
}

export interface DeliverySummary {
  completed_work: Array<{
    work_order_id: string
    title: string
    summary: string
  }>
  artifacts: string[]
  verification: string[]
  follow_ups: string[]
}

export interface ProjectDetail extends Project {
  project_brief: ProjectBrief | null
  work_orders: WorkOrder[]
  agent_reports: AgentReport[]
  qa_gate: QAGate | null
  delivery_summary: DeliverySummary | null
  phase_artifacts: Record<string, any>
}
```

#### 2.2 API Client

**File**: `src/core/projects/api.ts` (new)

```typescript
import type { Project, ProjectDetail } from './types'

export async function fetchProjects(): Promise<Project[]> {
  const response = await fetch('/api/projects')
  if (!response.ok) throw new Error('Failed to fetch projects')
  return response.json()
}

export async function fetchProjectDetail(threadId: string): Promise<ProjectDetail> {
  const response = await fetch(`/api/projects/${threadId}`)
  if (!response.ok) throw new Error('Failed to fetch project detail')
  return response.json()
}

export async function createProject(objective: string): Promise<{ thread_id: string }> {
  const response = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objective })
  })
  if (!response.ok) throw new Error('Failed to create project')
  return response.json()
}

export async function approveProject(threadId: string): Promise<void> {
  const response = await fetch(`/api/projects/${threadId}/approve`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to approve project')
}

export async function reviseProject(threadId: string, feedback: string): Promise<void> {
  const response = await fetch(`/api/projects/${threadId}/revise`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback })
  })
  if (!response.ok) throw new Error('Failed to revise project')
}

export async function cancelProject(threadId: string): Promise<void> {
  const response = await fetch(`/api/projects/${threadId}/cancel`, { method: 'POST' })
  if (!response.ok) throw new Error('Failed to cancel project')
}
```

#### 2.3 React Query Hooks

**File**: `src/core/projects/hooks.ts` (new)

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from './api'

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: api.fetchProjects,
    refetchInterval: 5000, // Poll every 5 seconds
  })
}

export function useProjectDetail(threadId: string) {
  return useQuery({
    queryKey: ['projects', threadId],
    queryFn: () => api.fetchProjectDetail(threadId),
    refetchInterval: 5000,
    enabled: !!threadId,
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useApproveProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.approveProject,
    onSuccess: (_, threadId) => {
      queryClient.invalidateQueries({ queryKey: ['projects', threadId] })
    },
  })
}

export function useReviseProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ threadId, feedback }: { threadId: string; feedback: string }) =>
      api.reviseProject(threadId, feedback),
    onSuccess: (_, { threadId }) => {
      queryClient.invalidateQueries({ queryKey: ['projects', threadId] })
    },
  })
}

export function useCancelProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.cancelProject,
    onSuccess: (_, threadId) => {
      queryClient.invalidateQueries({ queryKey: ['projects', threadId] })
    },
  })
}
```

### Phase 3: UI Components (Week 3-5)

#### 3.1 Component Structure

```
src/components/workspace/
├── sidebar.tsx (modify - add tabs)
├── project-list.tsx (new)
├── create-project-dialog.tsx (new)
├── approval-section.tsx (new)
├── revise-dialog.tsx (new)
├── overview-tab.tsx (new)
├── work-orders-tab.tsx (new)
└── specialists-tab.tsx (new)

src/app/workspace/projects/
├── page.tsx (new - projects list route)
└── [thread_id]/
    └── page.tsx (new - project dashboard)
```

#### 3.2 Shadcn Components Used

- `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent` - Navigation
- `Card`, `CardHeader`, `CardTitle`, `CardContent` - Content containers
- `Badge` - Status indicators
- `Button` - Actions
- `Dialog`, `DialogContent`, `DialogHeader`, `DialogFooter` - Modals
- `Table`, `TableHeader`, `TableRow`, `TableCell` - Work orders
- `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent` - Specialists
- `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent` - Expandable content
- `ScrollArea` - Scrollable lists
- `Textarea` - Text input
- `Progress` - Phase progress indicator

#### 3.3 Key UI Flows

**Creating a Project**:
1. User clicks "New Project" button in Projects tab
2. Dialog opens with textarea for objective input
3. User enters objective and clicks "Create"
4. API creates thread with `project_team_agent`
5. User redirected to project dashboard

**Approving a Plan**:
1. User views project in `awaiting_approval` phase
2. Dashboard shows approval section with plan preview
3. User clicks "Approve" button
4. API sends `/approve` message to thread
5. Dashboard polls and updates to `build` phase

**Revising a Plan**:
1. User clicks "Revise Plan" button
2. Modal opens with textarea for feedback
3. User enters feedback and submits
4. API sends `/revise <feedback>` message
5. Dashboard updates to show `planning` phase

### Phase 4: Testing Strategy

#### 4.1 Backend Tests

**File**: `backend/packages/gateway/tests/test_projects_api.py` (new)

```python
# Test cases:
- test_list_projects_empty()
- test_list_projects_with_data()
- test_get_project_detail()
- test_create_project()
- test_approve_project()
- test_revise_project()
- test_cancel_project()
- test_project_not_found()
```

#### 4.2 Frontend Tests

**Component Tests**:
- ProjectList renders correctly
- CreateProjectDialog validates input
- ApprovalSection shows correct buttons
- ReviseDialog submits feedback
- Dashboard tabs switch correctly

**Integration Tests**:
- Projects list fetches and displays data
- Project creation flow end-to-end
- Approval flow updates project state
- Polling updates dashboard automatically

## Implementation Checklist

### Week 1: Backend API
- [x] Create `projects.py` routes file
- [x] Implement `GET /api/projects` (list)
- [x] Implement `GET /api/projects/{thread_id}` (detail)
- [x] Implement `POST /api/projects` (create)
- [x] Implement `POST /api/projects/{thread_id}/approve`
- [x] Implement `POST /api/projects/{thread_id}/revise`
- [x] Implement `POST /api/projects/{thread_id}/cancel`
- [x] Write backend tests (9 tests, all passing)
- [x] Register router in Gateway app

### Week 2: Frontend Data Layer
- [x] Create `src/core/projects/types.ts`
- [x] Create `src/core/projects/api.ts`
- [x] Create `src/core/projects/hooks.ts`
- [x] Test API integration
- [x] Verify polling behavior

### Week 3: UI Foundation
- [x] Modify sidebar to add Chats/Projects tabs
- [x] Create `project-list.tsx` component
- [x] Create `create-project-dialog.tsx`
- [x] Add routes: `/workspace/projects` and `/workspace/projects/[thread_id]`
- [x] Test navigation flow

### Week 4: Dashboard Core
- [x] Create dashboard page layout
- [x] Implement `approval-section.tsx`
- [x] Implement `revise-dialog.tsx`
- [x] Implement `overview-tab.tsx`
- [x] Test approval/revise/cancel flows

### Week 5: Dashboard Details
- [x] Implement `work-orders-tab.tsx`
- [x] Implement `specialists-tab.tsx`
- [x] Add phase progress indicator
- [x] Style polish and responsive design
- [x] End-to-end testing

## Acceptance Criteria

1. ✅ Users can switch between Chats and Projects in sidebar
2. ✅ Projects list shows all projects with phase and status
3. ✅ Users can create new projects via "New Project" button
4. ✅ Dashboard displays current phase and plan status
5. ✅ Approval section appears in `awaiting_approval` phase
6. ✅ Users can approve, revise, or cancel plans
7. ✅ Work Orders tab shows all work orders with dependencies
8. ✅ Specialists tab shows execution details and reports
9. ✅ Dashboard auto-refreshes every 5 seconds
10. ✅ All UI uses Shadcn components with consistent styling
11. ✅ No changes to existing chat functionality

## Non-Goals (Out of Scope)

- Multi-user permissions and access control
- Project editing (title, brief modification)
- Work order manual creation/editing
- Real-time WebSocket updates
- Project templates
- Project archiving/deletion
- Export functionality
- Advanced filtering/search

## Future Enhancements

- Real-time updates via WebSocket
- User-specific project views
- Project templates
- Advanced work order visualization (Gantt chart, Kanban)
- Specialist execution logs with code highlighting
- Project comparison and analytics
- Export to PDF/Markdown

## References

- [Project Team Runtime Architecture](./project_team_runtime_architecture.md)
- [Project Team Runtime PRD](./project_team_runtime_prd.md)
- [Frontend CLAUDE.md](../../frontend/CLAUDE.md)
- [Shadcn UI Documentation](https://ui.shadcn.com/)
