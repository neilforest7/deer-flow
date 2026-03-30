/**
 * React Query hooks for projects
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as api from "./api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: api.fetchProjects,
    refetchInterval: 5000, // Poll every 5 seconds
  });
}

export function useProjectDetail(threadId: string) {
  return useQuery({
    queryKey: ["projects", threadId],
    queryFn: () => api.fetchProjectDetail(threadId),
    refetchInterval: 5000,
    enabled: !!threadId,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useApproveProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.approveProject,
    onSuccess: (_, threadId) => {
      void queryClient.invalidateQueries({ queryKey: ["projects", threadId] });
    },
  });
}

export function useReviseProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, feedback }: { threadId: string; feedback: string }) =>
      api.reviseProject(threadId, feedback),
    onSuccess: (_, { threadId }) => {
      void queryClient.invalidateQueries({ queryKey: ["projects", threadId] });
    },
  });
}

export function useCancelProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.cancelProject,
    onSuccess: (_, threadId) => {
      void queryClient.invalidateQueries({ queryKey: ["projects", threadId] });
    },
  });
}
