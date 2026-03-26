import { getBackendBaseURL } from "@/core/config";

import type {
  CreateProjectRequest,
  ProjectAction,
  ProjectRecord,
  ProjectTeam,
} from "./types";

export async function listProjects(): Promise<ProjectRecord[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/projects`);
  if (!res.ok) throw new Error(`Failed to load projects: ${res.statusText}`);
  const data = (await res.json()) as { projects: ProjectRecord[] };
  return data.projects;
}

export async function getProject(projectId: string): Promise<ProjectRecord> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/projects/${encodeURIComponent(projectId)}`,
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to load project '${projectId}'`);
  }
  return res.json() as Promise<ProjectRecord>;
}

export async function createProject(
  request: CreateProjectRequest,
): Promise<ProjectRecord> {
  const res = await fetch(`${getBackendBaseURL()}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail ?? `Failed to create project: ${res.statusText}`);
  }
  return res.json() as Promise<ProjectRecord>;
}

export async function controlProject(
  projectId: string,
  action: ProjectAction,
): Promise<ProjectRecord> {
  const res = await fetch(
    `${getBackendBaseURL()}/api/projects/${encodeURIComponent(projectId)}/actions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    },
  );
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(
      err.detail ?? `Failed to ${action} project: ${res.statusText}`,
    );
  }
  return res.json() as Promise<ProjectRecord>;
}

export async function listProjectTeams(): Promise<ProjectTeam[]> {
  const res = await fetch(`${getBackendBaseURL()}/api/project-teams`);
  if (!res.ok) {
    throw new Error(`Failed to load project teams: ${res.statusText}`);
  }
  const data = (await res.json()) as { teams: ProjectTeam[] };
  return data.teams;
}
