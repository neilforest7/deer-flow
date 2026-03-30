"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProjectDetail } from "@/core/projects/types";

interface WorkOrdersTabProps {
  project: ProjectDetail;
}

const statusColors: Record<string, string> = {
  pending: "bg-gray-500/10 text-gray-500",
  active: "bg-blue-500/10 text-blue-500",
  completed: "bg-green-500/10 text-green-500",
  failed: "bg-red-500/10 text-red-500",
};

export function WorkOrdersTab({ project }: WorkOrdersTabProps) {
  const { work_orders } = project;

  if (!work_orders || work_orders.length === 0) {
    return (
      <div className="text-muted-foreground p-4 text-center">
        No work orders yet
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {work_orders.map((wo) => (
        <Card key={wo.id}>
          <CardHeader>
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <CardTitle className="text-base">{wo.title}</CardTitle>
                <p className="text-muted-foreground text-sm">
                  Owner: {wo.owner_agent}
                </p>
              </div>
              <Badge className={statusColors[wo.status] || statusColors.pending}>
                {wo.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h4 className="mb-1 text-sm font-semibold">Goal</h4>
              <p className="text-muted-foreground text-sm">{wo.goal}</p>
            </div>

            {wo.dependencies.length > 0 && (
              <div>
                <h4 className="mb-1 text-sm font-semibold">Dependencies</h4>
                <ul className="text-muted-foreground list-inside list-disc text-sm">
                  {wo.dependencies.map((dep, i) => (
                    <li key={i}>{dep}</li>
                  ))}
                </ul>
              </div>
            )}

            {wo.acceptance_checks.length > 0 && (
              <div>
                <h4 className="mb-1 text-sm font-semibold">Acceptance Checks</h4>
                <ul className="text-muted-foreground list-inside list-disc text-sm">
                  {wo.acceptance_checks.map((check, i) => (
                    <li key={i}>{check}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
