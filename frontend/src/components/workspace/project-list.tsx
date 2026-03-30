"use client";

import Link from "next/link";
import { MessageSquare, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useProjects } from "@/core/projects/hooks";
import { cn } from "@/lib/utils";

const phaseLabels: Record<string, string> = {
  intake: "Intake",
  discovery: "Discovery",
  planning: "Planning",
  awaiting_approval: "Awaiting Approval",
  build: "Build",
  qa_gate: "QA Gate",
  delivery: "Delivery",
  done: "Done",
};

const phaseColors: Record<string, string> = {
  intake: "bg-blue-500/10 text-blue-500",
  discovery: "bg-purple-500/10 text-purple-500",
  planning: "bg-yellow-500/10 text-yellow-500",
  awaiting_approval: "bg-orange-500/10 text-orange-500",
  build: "bg-green-500/10 text-green-500",
  qa_gate: "bg-cyan-500/10 text-cyan-500",
  delivery: "bg-indigo-500/10 text-indigo-500",
  done: "bg-gray-500/10 text-gray-500",
};

export function ProjectList() {
  const { data: projects, isLoading } = useProjects();

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground text-sm">Loading projects...</p>
      </div>
    );
  }

  if (!projects || projects.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
        <MessageSquare className="text-muted-foreground size-12" />
        <div className="text-center">
          <h3 className="font-semibold">No projects yet</h3>
          <p className="text-muted-foreground text-sm">
            Create your first project to get started
          </p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="grid gap-4 p-4">
        {projects.map((project) => (
          <Link key={project.id} href={`/workspace/projects/${project.id}`}>
            <Card className="hover:bg-accent transition-colors">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{project.title}</CardTitle>
              </CardHeader>
              <CardContent className="flex items-center gap-2">
                <Badge
                  variant="secondary"
                  className={cn(
                    "text-xs",
                    phaseColors[project.phase] || "bg-gray-500/10 text-gray-500",
                  )}
                >
                  {phaseLabels[project.phase] || project.phase}
                </Badge>
                <span className="text-muted-foreground text-xs">
                  {new Date(project.updated_at).toLocaleDateString()}
                </span>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </ScrollArea>
  );
}
