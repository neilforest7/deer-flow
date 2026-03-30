"use client";

import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApprovalSection } from "@/components/workspace/approval-section";
import { OverviewTab } from "@/components/workspace/overview-tab";
import { PhaseProgress } from "@/components/workspace/phase-progress";
import { SpecialistsTab } from "@/components/workspace/specialists-tab";
import { WorkOrdersTab } from "@/components/workspace/work-orders-tab";
import { useProjectDetail } from "@/core/projects/hooks";

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

export default function ProjectDetailPage() {
  const params = useParams();
  const threadId = params.thread_id as string;
  const { data: project, isLoading } = useProjectDetail(threadId);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading project...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Project not found</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-3xl font-bold">{project.title}</h1>
          <div className="mt-2 flex items-center gap-2">
            <Badge variant="secondary">
              {phaseLabels[project.phase] || project.phase}
            </Badge>
            <span className="text-muted-foreground text-sm">
              Updated {new Date(project.updated_at).toLocaleString()}
            </span>
          </div>
          <div className="mt-4">
            <PhaseProgress phase={project.phase} />
          </div>
        </div>

        <ApprovalSection
          threadId={threadId}
          planStatus={project.plan_status}
        />

        <Tabs defaultValue="overview" className="w-full">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="work-orders">Work Orders</TabsTrigger>
            <TabsTrigger value="specialists">Specialists</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="mt-4">
            <OverviewTab project={project} />
          </TabsContent>
          <TabsContent value="work-orders" className="mt-4">
            <WorkOrdersTab project={project} />
          </TabsContent>
          <TabsContent value="specialists" className="mt-4">
            <SpecialistsTab project={project} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
