"use client";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProjectDetail } from "@/core/projects/types";

interface SpecialistsTabProps {
  project: ProjectDetail;
}

export function SpecialistsTab({ project }: SpecialistsTabProps) {
  const { agent_reports } = project;

  if (!agent_reports || agent_reports.length === 0) {
    return (
      <div className="text-muted-foreground p-4 text-center">
        No agent reports yet
      </div>
    );
  }

  return (
    <Accordion type="single" collapsible className="space-y-4">
      {agent_reports.map((report, idx) => (
        <AccordionItem key={idx} value={`report-${idx}`} className="border-none">
          <Card>
            <CardHeader>
              <AccordionTrigger className="hover:no-underline">
                <div className="flex items-center justify-between w-full pr-4">
                  <CardTitle className="text-base">{report.agent_name}</CardTitle>
                  <span className="text-muted-foreground text-sm">
                    Work Order: {report.work_order_id}
                  </span>
                </div>
              </AccordionTrigger>
            </CardHeader>
            <AccordionContent>
              <CardContent className="space-y-4 pt-0">
                <div>
                  <h4 className="mb-1 text-sm font-semibold">Summary</h4>
                  <p className="text-muted-foreground text-sm">{report.summary}</p>
                </div>

                {report.changes.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-semibold">Changes</h4>
                    <ul className="text-muted-foreground list-inside list-disc text-sm">
                      {report.changes.map((change, i) => (
                        <li key={i}>{change}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {report.risks.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-semibold">Risks</h4>
                    <ul className="text-muted-foreground list-inside list-disc text-sm">
                      {report.risks.map((risk, i) => (
                        <li key={i}>{risk}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {report.verification.length > 0 && (
                  <div>
                    <h4 className="mb-1 text-sm font-semibold">Verification</h4>
                    <ul className="text-muted-foreground list-inside list-disc text-sm">
                      {report.verification.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </AccordionContent>
          </Card>
        </AccordionItem>
      ))}
    </Accordion>
  );
}
