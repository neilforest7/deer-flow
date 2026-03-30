/**
 * API client for projects endpoints
 */

import type { Project, ProjectDetail } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_BASE_URL || "";

export async function fetchProjects(): Promise<Project[]> {
  const response = await fetch(`${API_BASE}/api/projects`);
  if (!response.ok) throw new Error("Failed to fetch projects");
  const data = await response.json();
  return data.projects;
}

export async function fetchProjectDetail(
  threadId: string,
): Promise<ProjectDetail> {
  const response = await fetch(`${API_BASE}/api/projects/${threadId}`);
  if (!response.ok) throw new Error("Failed to fetch project detail");
  return response.json();
}

export async function createProject(
  objective: string,
): Promise<{ thread_id: string }> {
  const response = await fetch(`${API_BASE}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ objective }),
  });
  if (!response.ok) throw new Error("Failed to create project");
  return response.json();
}

export async function approveProject(threadId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/projects/${threadId}/approve`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to approve project");
}

export async function reviseProject(
  threadId: string,
  feedback: string,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/projects/${threadId}/revise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
  });
  if (!response.ok) throw new Error("Failed to revise project");
}

export async function cancelProject(threadId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/projects/${threadId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed to cancel project");
}
