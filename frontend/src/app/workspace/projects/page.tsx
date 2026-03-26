"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { useCreateProject, useProjectTeams, useProjects } from "@/core/projects";
import { formatTimeAgo } from "@/core/utils/datetime";

export default function ProjectsPage() {
  const router = useRouter();
  const { data: projects = [] } = useProjects();
  const { data: teams = [] } = useProjectTeams();
  const createProject = useCreateProject();

  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [teamName, setTeamName] = useState("software-delivery-default");

  useEffect(() => {
    document.title = "Projects - DeerFlow";
  }, []);

  const sortedProjects = useMemo(
    () =>
      [...projects].sort((a, b) =>
        (b.updated_at ?? b.created_at ?? "").localeCompare(
          a.updated_at ?? a.created_at ?? "",
        ),
      ),
    [projects],
  );

  async function handleCreateProject() {
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      toast.error("Project title is required.");
      return;
    }

    try {
      const project = await createProject.mutateAsync({
        title: trimmedTitle,
        objective: objective.trim() || undefined,
        team_name: teamName,
      });
      router.push(`/workspace/projects/${project.project_id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create project.");
    }
  }

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-hidden px-4 py-6 md:px-6">
        <div className="mx-auto grid size-full max-w-7xl gap-6 lg:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="h-fit">
            <CardHeader>
              <CardTitle>New Project</CardTitle>
              <CardDescription>
                Create a Project Delivery OS thread driven by
                `project_lead_agent`.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Title</label>
                <Input
                  placeholder="Postgres migration for DeerFlow"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Objective</label>
                <Textarea
                  placeholder="Migrate the platform to Postgres-only persistence and ship a project workspace."
                  rows={5}
                  value={objective}
                  onChange={(event) => setObjective(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Team</label>
                <select
                  className="border-input bg-background flex h-10 w-full rounded-md border px-3 text-sm"
                  value={teamName}
                  onChange={(event) => setTeamName(event.target.value)}
                >
                  {(teams.length > 0 ? teams : [{ name: "software-delivery-default" }]).map(
                    (team) => (
                      <option key={team.name} value={team.name}>
                        {team.name}
                      </option>
                    ),
                  )}
                </select>
              </div>
              <Button
                className="w-full"
                disabled={createProject.isPending}
                onClick={handleCreateProject}
              >
                {createProject.isPending ? "Creating..." : "Create project"}
              </Button>
            </CardContent>
          </Card>

          <Card className="min-h-0">
            <CardHeader>
              <CardTitle>Projects</CardTitle>
              <CardDescription>
                Each project maps 1:1 to its own orchestration thread and board.
              </CardDescription>
            </CardHeader>
            <CardContent className="min-h-0">
              <ScrollArea className="h-[calc(100vh-220px)] pr-4">
                <div className="space-y-3">
                  {sortedProjects.map((project) => (
                    <Link
                      key={project.project_id}
                      href={`/workspace/projects/${project.project_id}`}
                    >
                      <div className="hover:border-foreground/20 rounded-xl border p-4 transition">
                        <div className="flex items-start justify-between gap-3">
                          <div className="space-y-1">
                            <div className="font-medium">{project.title}</div>
                            <div className="text-muted-foreground text-sm">
                              {project.description}
                            </div>
                          </div>
                          <div className="text-right text-xs uppercase tracking-[0.14em] text-muted-foreground">
                            {project.phase}
                          </div>
                        </div>
                        <div className="text-muted-foreground mt-3 flex items-center justify-between text-xs">
                          <span>{project.status}</span>
                          <span>
                            {formatTimeAgo(project.updated_at ?? project.created_at ?? "")}
                          </span>
                        </div>
                      </div>
                    </Link>
                  ))}
                  {sortedProjects.length === 0 && (
                    <div className="text-muted-foreground rounded-xl border border-dashed p-6 text-sm">
                      No projects yet. Create one from the left panel.
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
