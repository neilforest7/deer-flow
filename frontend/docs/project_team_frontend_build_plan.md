# Frontend Build Plan: Project Team Integration

**Status**: 🚧 In Progress (Week 2 Complete)
**Started**: 2026-03-30
**Last Updated**: 2026-03-30

## Overview

This document tracks the frontend implementation progress for integrating the `project_team_agent` runtime into the DeerFlow web interface.

## Architecture Summary

- **Tech Stack**: Next.js 16, React 19, TypeScript 5.8, Tailwind CSS 4
- **Data Fetching**: TanStack Query with 5-second polling
- **UI Components**: Shadcn UI (consistent with existing design)
- **Routing**: App Router (`/workspace/projects` and `/workspace/projects/[thread_id]`)

## Implementation Phases

### ✅ Phase 1: Data Layer (Week 2) - COMPLETED

**Status**: ✅ Complete (2026-03-30)

**Files Created**:
- `src/core/projects/types.ts` - TypeScript type definitions
- `src/core/projects/api.ts` - API client functions
- `src/core/projects/hooks.ts` - React Query hooks

**Deliverables**:
- [x] Type definitions for all project entities (Phase, PlanStatus, Project, ProjectDetail, etc.)
- [x] API client with error handling for all endpoints
- [x] React Query hooks with automatic polling (5s interval)
- [x] Mutation hooks for create, approve, revise, cancel operations

**Commit**: `4f58105` - feat(frontend): add projects data layer

---

### 🚧 Phase 2: Sidebar & Project List (Week 3) - IN PROGRESS

**Status**: 🚧 Not Started

**Target Files**:
- `src/components/workspace/sidebar.tsx` (modify existing)
- `src/components/workspace/project-list.tsx` (new)
- `src/components/workspace/create-project-dialog.tsx` (new)
- `src/app/workspace/projects/page.tsx` (new route)

**Tasks**:
- [ ] Modify sidebar to add Chats/Projects tab switcher
  - Use Shadcn `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`
  - Preserve existing ThreadList in Chats tab
  - Add ProjectList in Projects tab
- [ ] Create ProjectList component
  - Display project cards with title, phase, status badges
  - Show last updated time
  - Click to navigate to project dashboard
  - "New Project" button at top
- [ ] Create CreateProjectDialog component
  - Modal with textarea for objective input
  - Validation (non-empty objective)
  - Call `useCreateProject` hook
  - Redirect to dashboard on success
- [ ] Add `/workspace/projects` route
  - Server component wrapper
  - Render ProjectList

**Shadcn Components**:
- `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`
- `Card`, `CardHeader`, `CardTitle`, `CardContent`
- `Badge`
- `Button`
- `Dialog`, `DialogContent`, `DialogHeader`, `DialogFooter`
- `Textarea`
- `ScrollArea`

---

### 📅 Phase 3: Dashboard Core (Week 4) - PLANNED

**Status**: 📅 Planned

**Target Files**:
- `src/app/workspace/projects/[thread_id]/page.tsx` (new route)
- `src/components/workspace/approval-section.tsx` (new)
- `src/components/workspace/revise-dialog.tsx` (new)
- `src/components/workspace/overview-tab.tsx` (new)

**Tasks**:
- [ ] Create dashboard page layout
  - Header with project title and phase badges
  - Conditional approval section (only in `awaiting_approval` phase)
  - Tabs for Overview/Work Orders/Specialists
- [ ] Create ApprovalSection component
  - Display work orders preview
  - Approve/Revise/Cancel buttons
  - Call respective mutation hooks
- [ ] Create ReviseDialog component
  - Modal with textarea for feedback
  - Submit calls `useReviseProject`
- [ ] Create OverviewTab component
  - Project brief display (objective, scope, deliverables)
  - Phase progress indicator
  - QA gate results (if available)
  - Delivery summary (if available)

**Shadcn Components**:
- `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`
- `Card`, `CardHeader`, `CardTitle`, `CardContent`
- `Badge`
- `Button`
- `Dialog`, `DialogContent`, `DialogHeader`, `DialogFooter`
- `Textarea`
- `Progress`

---

### 📅 Phase 4: Dashboard Details (Week 5) - PLANNED

**Status**: 📅 Planned

**Target Files**:
- `src/components/workspace/work-orders-tab.tsx` (new)
- `src/components/workspace/specialists-tab.tsx` (new)

**Tasks**:
- [ ] Create WorkOrdersTab component
  - Table with columns: ID, Title, Owner, Status, Dependencies
  - Status badges with color coding
  - Display dependencies as comma-separated list
- [ ] Create SpecialistsTab component
  - Accordion with one item per work order
  - Show specialist name, work order title, status
  - Collapsible sections for:
    - Work order goal
    - Agent report summary
    - Changes (collapsible list)
    - Risks (if any)
    - Verification results

**Shadcn Components**:
- `Table`, `TableHeader`, `TableRow`, `TableHead`, `TableBody`, `TableCell`
- `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent`
- `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent`
- `Badge`
- `Button`
- `ScrollArea`

---

## Component Hierarchy

```
/workspace/projects (route)
└── ProjectList
    ├── CreateProjectDialog
    └── ProjectCard (multiple)

/workspace/projects/[thread_id] (route)
└── ProjectDashboard
    ├── Header (title + badges)
    ├── ApprovalSection (conditional)
    │   └── ReviseDialog
    └── Tabs
        ├── OverviewTab
        │   ├── ProjectBrief
        │   ├── PhaseProgress
        │   ├── QAGateResults (conditional)
        │   └── DeliverySummary (conditional)
        ├── WorkOrdersTab
        │   └── WorkOrdersTable
        └── SpecialistsTab
            └── SpecialistsAccordion
```

## Design Principles

1. **Minimal Code**: Only essential functionality, no over-engineering
2. **Shadcn Only**: Use Shadcn components exclusively, minimal custom styling
3. **Consistent Design**: Match existing DeerFlow UI patterns
4. **No Breaking Changes**: Preserve all existing chat functionality
5. **Progressive Enhancement**: Build incrementally, test each phase

## Testing Strategy

- Manual testing in dev environment (`pnpm dev`)
- Verify API integration with backend
- Test polling behavior (5s refresh)
- Validate approval/revise/cancel flows
- Check responsive design on different screen sizes

## Acceptance Criteria

- [x] Data layer complete with types, API, hooks
- [ ] Users can switch between Chats and Projects tabs
- [ ] Projects list shows all projects with correct status
- [ ] Users can create new projects
- [ ] Dashboard displays current phase and status
- [ ] Approval section appears in `awaiting_approval` phase
- [ ] Users can approve, revise, or cancel plans
- [ ] Work Orders tab shows all work orders
- [ ] Specialists tab shows execution details
- [ ] Dashboard auto-refreshes every 5 seconds
- [ ] All UI uses Shadcn components
- [ ] No changes to existing chat functionality

## Known Limitations (MVP)

- No real-time WebSocket updates (polling only)
- No multi-user permissions
- No project editing (title, brief modification)
- No work order manual creation/editing
- No advanced filtering/search
- No project templates
- No export functionality

## Future Enhancements (Post-MVP)

- Real-time updates via WebSocket
- User-specific project views
- Project templates
- Advanced work order visualization (Gantt, Kanban)
- Specialist execution logs with code highlighting
- Project comparison and analytics
- Export to PDF/Markdown
- Project archiving/deletion

## References

- [Backend Projects API](../../backend/app/gateway/routers/projects.py)
- [Project Team Runtime Architecture](../../backend/docs/project_team_runtime_architecture.md)
- [Frontend Integration Plan](../../backend/docs/project_team_frontend_integration_plan.md)
- [Shadcn UI Documentation](https://ui.shadcn.com/)
