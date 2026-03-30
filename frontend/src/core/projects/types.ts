/**
 * Project runtime types for project_team_agent
 */

export type Phase =
  | "intake"
  | "discovery"
  | "planning"
  | "awaiting_approval"
  | "build"
  | "qa_gate"
  | "delivery"
  | "done";

export type PlanStatus =
  | "draft"
  | "awaiting_approval"
  | "approved"
  | "needs_revision";

export interface Project {
  id: string;
  title: string;
  phase: Phase;
  plan_status: PlanStatus;
  created_at: string;
  updated_at: string;
}

export interface ProjectBrief {
  objective: string;
  scope: string[];
  constraints: string[];
  deliverables: string[];
  success_criteria: string[];
}

export interface WorkOrder {
  id: string;
  owner_agent: string;
  title: string;
  goal: string;
  read_scope: string[];
  write_scope: string[];
  dependencies: string[];
  acceptance_checks: string[];
  status: "pending" | "active" | "completed" | "failed";
}

export interface AgentReport {
  work_order_id: string;
  agent_name: string;
  summary: string;
  changes: string[];
  risks: string[];
  verification: string[];
}

export interface QAGate {
  result: "pass" | "fail" | "blocked";
  findings: string[];
  required_rework: string[];
}

export interface DeliverySummary {
  completed_work: Array<{
    work_order_id: string;
    title: string;
    summary: string;
  }>;
  artifacts: string[];
  verification: string[];
  follow_ups: string[];
}

export interface ProjectDetail extends Project {
  project_brief: ProjectBrief | null;
  work_orders: WorkOrder[];
  agent_reports: AgentReport[];
  qa_gate: QAGate | null;
  delivery_summary: DeliverySummary | null;
  phase_artifacts: Record<string, unknown>;
}
