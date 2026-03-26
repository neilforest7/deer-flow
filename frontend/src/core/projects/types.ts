export type ProjectControlFlags = {
  pause_requested: boolean;
  abort_requested: boolean;
  updated_at?: string;
};

export type ProjectRecord = {
  project_id: string;
  thread_id: string;
  assistant_id: string;
  visible_agent_name: string;
  title: string;
  description: string;
  status: string;
  phase: string;
  team_name: string;
  created_at?: string;
  updated_at?: string;
  project_title?: string;
  project_brief?: Record<string, unknown> | null;
  work_orders: Array<Record<string, unknown>>;
  agent_reports: Array<Record<string, unknown>>;
  gate_decision?: Record<string, unknown> | null;
  delivery_pack?: Record<string, unknown> | null;
  active_batch?: Record<string, unknown> | null;
  artifacts: string[];
  control_flags: ProjectControlFlags;
  latest_gate?: Record<string, unknown> | null;
};

export type CreateProjectRequest = {
  title: string;
  objective?: string;
  team_name?: string;
};

export type ProjectAction = "pause" | "resume" | "abort";

export type ProjectTeam = {
  name: string;
  description: string;
  visible_agent_name: string;
  phases: string[];
  specialists: Array<Record<string, unknown>>;
  routing_policy: Record<string, unknown>;
  qa_policy: Record<string, unknown>;
  delivery_policy: Record<string, unknown>;
  updated_at?: string;
};
