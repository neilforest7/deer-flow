"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProjectDetail } from "@/core/projects/types";

interface OverviewTabProps {
  project: ProjectDetail;
}

export function OverviewTab({ project }: OverviewTabProps) {
  const { project_brief } = project;

  if (!project_brief) {
    return (
      <div className="text-muted-foreground p-4 text-center">
        No project brief available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Objective</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{project_brief.objective}</p>
        </CardContent>
      </Card>

      {project_brief.scope.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Scope</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {project_brief.scope.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {project_brief.constraints.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Constraints</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {project_brief.constraints.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {project_brief.deliverables.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Deliverables</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {project_brief.deliverables.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {project_brief.success_criteria.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Success Criteria</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-inside list-disc space-y-1 text-sm">
              {project_brief.success_criteria.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
