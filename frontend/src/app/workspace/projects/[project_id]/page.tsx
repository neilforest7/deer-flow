"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect } from "react";
import { toast } from "sonner";

import { type PromptInputMessage } from "@/components/ai-elements/prompt-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { InputBox } from "@/components/workspace/input-box";
import { MessageList } from "@/components/workspace/messages";
import { ThreadContext } from "@/components/workspace/messages/context";
import { TodoList } from "@/components/workspace/todo-list";
import { TokenUsageIndicator } from "@/components/workspace/token-usage-indicator";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useControlProject, useProject } from "@/core/projects";
import { useLocalSettings } from "@/core/settings";
import { useThreadStream } from "@/core/threads/hooks";
import { formatTimeAgo } from "@/core/utils/datetime";
import { cn } from "@/lib/utils";

function valueAsText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export default function ProjectDetailPage() {
  const params = useParams<{ project_id: string }>();
  const projectId = typeof params?.project_id === "string" ? params.project_id : "";
  const resolvedThreadId = projectId || undefined;
  const [settings, setSettings] = useLocalSettings();
  const {
    data: project,
    error,
    isLoading,
    refetch,
  } = useProject(projectId, 5000);
  const controlProject = useControlProject(projectId);

  useEffect(() => {
    if (project?.title) {
      document.title = `${project.title} - DeerFlow Projects`;
    }
  }, [project?.title]);

  const [thread, sendMessage, isUploading] = useThreadStream({
    threadId: project?.thread_id ?? resolvedThreadId,
    assistantId: "project_lead_agent",
    context: settings.context,
    runtimeContextOverrides: {
      subagent_enabled: true,
    },
    onFinish: () => {
      void refetch();
    },
  });

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      if (!project?.thread_id && !resolvedThreadId) return;
      void sendMessage(project?.thread_id ?? resolvedThreadId!, message, {
        project_id: project?.project_id ?? projectId,
      });
    },
    [project, projectId, resolvedThreadId, sendMessage],
  );

  const handleStop = useCallback(async () => {
    await thread.stop();
  }, [thread]);

  const handleControl = useCallback(
    async (action: "pause" | "resume" | "abort") => {
      try {
        await controlProject.mutateAsync(action);
        await refetch();
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : `Failed to ${action} project.`,
        );
      }
    },
    [controlProject, refetch],
  );

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-hidden px-4 py-4 md:px-6">
        <div className="mx-auto grid size-full max-w-7xl gap-4 xl:grid-cols-[minmax(0,1.6fr)_420px]">
          <ThreadContext.Provider value={{ thread }}>
            <Card className="min-h-0">
              <CardHeader className="border-b">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-2">
                    <CardTitle>{project?.title ?? "Loading project..."}</CardTitle>
                    <CardDescription>
                      {project?.description ?? "Resolving project state..."}
                    </CardDescription>
                  </div>
                  {project && (
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{project.phase}</Badge>
                      <Badge>{project.status}</Badge>
                    </div>
                  )}
                </div>
              </CardHeader>
              <CardContent className="flex min-h-0 flex-1 flex-col px-0">
                <div className="relative flex min-h-0 flex-1 flex-col">
                  <div className="absolute top-4 right-6 z-10">
                    <TokenUsageIndicator messages={thread.messages} />
                  </div>
                  <ScrollArea className="min-h-0 flex-1">
                    {error ? (
                      <div className="text-destructive p-6 text-sm">
                        {error instanceof Error
                          ? error.message
                          : "Failed to load project thread."}
                      </div>
                    ) : (
                      <MessageList
                        className={cn("size-full pt-4")}
                        threadId={project?.thread_id ?? projectId}
                        thread={thread}
                      />
                    )}
                  </ScrollArea>
                  <div className="border-t px-4 pt-3 pb-4">
                    <TodoList
                      className="bg-background/5 mb-4"
                      todos={thread.values.todos ?? []}
                      hidden={!thread.values.todos || thread.values.todos.length === 0}
                    />
                    <InputBox
                      className="bg-background/5 w-full"
                      threadId={project?.thread_id ?? projectId}
                      isNewThread={false}
                      status={thread.error ? "error" : thread.isLoading ? "streaming" : "ready"}
                      context={settings.context}
                      disabled={!project || isUploading}
                      onContextChange={(context) => setSettings("context", context)}
                      onSubmit={handleSubmit}
                      onStop={handleStop}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </ThreadContext.Provider>

          <Card className="min-h-0">
            <CardHeader className="border-b">
              <CardTitle>Project Board</CardTitle>
              <CardDescription>
                Phase, work orders, reports, QA gate, artifacts, and controls.
              </CardDescription>
            </CardHeader>
            <CardContent className="min-h-0 px-0">
              <ScrollArea className="h-[calc(100vh-210px)] px-6">
                {project ? (
                  <div className="space-y-6 py-6">
                    <section className="space-y-3">
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <div className="text-muted-foreground text-xs uppercase">Phase</div>
                          <div className="font-medium">{project.phase}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground text-xs uppercase">Status</div>
                          <div className="font-medium">{project.status}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground text-xs uppercase">Team</div>
                          <div className="font-medium">{project.team_name}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground text-xs uppercase">Updated</div>
                          <div className="font-medium">
                            {formatTimeAgo(project.updated_at ?? project.created_at ?? "")}
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={controlProject.isPending || project.control_flags.pause_requested}
                          onClick={() => void handleControl("pause")}
                        >
                          Pause
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={controlProject.isPending || !project.control_flags.pause_requested}
                          onClick={() => void handleControl("resume")}
                        >
                          Resume
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={controlProject.isPending || project.control_flags.abort_requested}
                          onClick={() => void handleControl("abort")}
                        >
                          Abort
                        </Button>
                      </div>
                    </section>

                    <section className="space-y-2">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        Project Brief
                      </h3>
                      <div className="rounded-xl border p-4 text-sm">
                        {valueAsText(project.project_brief?.objective) ||
                          project.description ||
                          ""}
                      </div>
                    </section>

                    <section className="space-y-2">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        Work Orders
                      </h3>
                      <div className="space-y-2">
                        {project.work_orders.map((order) => (
                          <div key={String(order.id)} className="rounded-xl border p-4 text-sm">
                            <div className="flex items-start justify-between gap-3">
                              <div className="font-medium">
                                {valueAsText(order.description) || valueAsText(order.id)}
                              </div>
                              <Badge variant="outline">
                                {valueAsText(order.status) || "unknown"}
                              </Badge>
                            </div>
                            <div className="text-muted-foreground mt-2 text-xs">
                              {valueAsText(order.owner_agent)}
                            </div>
                          </div>
                        ))}
                        {project.work_orders.length === 0 && (
                          <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm">
                            No work orders yet.
                          </div>
                        )}
                      </div>
                    </section>

                    <section className="space-y-2">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        Reports
                      </h3>
                      <div className="space-y-2">
                        {project.agent_reports.map((report) => (
                          <div key={String(report.id)} className="rounded-xl border p-4 text-sm">
                            <div className="font-medium">
                              {valueAsText(report.summary) || valueAsText(report.id)}
                            </div>
                            <div className="text-muted-foreground mt-2 text-xs">
                              {valueAsText(report.owner_agent)}
                            </div>
                          </div>
                        ))}
                        {project.agent_reports.length === 0 && (
                          <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm">
                            No reports yet.
                          </div>
                        )}
                      </div>
                    </section>

                    <section className="space-y-2">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        QA Gate
                      </h3>
                      <div className="rounded-xl border p-4 text-sm">
                        {project.gate_decision ? (
                          <div className="space-y-2">
                            <div className="font-medium">
                              {valueAsText(project.gate_decision.status) || "unknown"}
                            </div>
                            <div className="text-muted-foreground text-xs">
                              Latest QA gate decision stored in LangGraph Store.
                            </div>
                          </div>
                        ) : (
                          <div className="text-muted-foreground">Pending QA gate.</div>
                        )}
                      </div>
                    </section>

                    <section className="space-y-2">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        Artifacts
                      </h3>
                      <div className="space-y-2">
                        {project.artifacts.map((artifact) => (
                          <div key={artifact} className="rounded-xl border p-3 text-sm">
                            {artifact}
                          </div>
                        ))}
                        {project.artifacts.length === 0 && (
                          <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm">
                            No artifacts yet.
                          </div>
                        )}
                      </div>
                    </section>
                  </div>
                ) : (
                  <div className="text-muted-foreground p-6 text-sm">
                    {isLoading ? "Loading project board..." : "Project not found."}
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
