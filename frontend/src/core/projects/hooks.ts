"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  controlProject,
  createProject,
  getProject,
  listProjects,
  listProjectTeams,
} from "./api";
import type { CreateProjectRequest, ProjectAction } from "./types";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    refetchOnWindowFocus: false,
  });
}

export function useProject(projectId: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: () => getProject(projectId),
    enabled: Boolean(projectId),
    refetchOnWindowFocus: false,
    refetchInterval,
  });
}

export function useProjectTeams() {
  return useQuery({
    queryKey: ["project-teams"],
    queryFn: listProjectTeams,
    refetchOnWindowFocus: false,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateProjectRequest) => createProject(request),
    onSuccess(project) {
      queryClient.setQueryData(["projects", project.project_id], project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useControlProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: ProjectAction) => controlProject(projectId, action),
    onSuccess(project) {
      queryClient.setQueryData(["projects", project.project_id], project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
