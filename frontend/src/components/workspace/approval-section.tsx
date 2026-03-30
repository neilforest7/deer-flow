"use client";

import { useState } from "react";
import { CheckCircle, XCircle, AlertCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApproveProject, useCancelProject } from "@/core/projects/hooks";

import { ReviseDialog } from "./revise-dialog";

interface ApprovalSectionProps {
  threadId: string;
  planStatus: string;
}

export function ApprovalSection({
  threadId,
  planStatus,
}: ApprovalSectionProps) {
  const [reviseDialogOpen, setReviseDialogOpen] = useState(false);
  const approveProject = useApproveProject();
  const cancelProject = useCancelProject();

  if (planStatus !== "awaiting_approval") {
    return null;
  }

  const handleApprove = async () => {
    try {
      await approveProject.mutateAsync(threadId);
    } catch (error) {
      console.error("Failed to approve project:", error);
    }
  };

  const handleCancel = async () => {
    if (!confirm("Are you sure you want to cancel this project?")) return;

    try {
      await cancelProject.mutateAsync(threadId);
    } catch (error) {
      console.error("Failed to cancel project:", error);
    }
  };

  return (
    <>
      <Card className="border-orange-500/20 bg-orange-500/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-orange-500">
            <AlertCircle className="size-5" />
            Plan Approval Required
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-muted-foreground text-sm">
            Review the project plan and approve to begin execution, or request
            revisions.
          </p>
          <div className="flex gap-2">
            <Button
              onClick={handleApprove}
              disabled={approveProject.isPending}
              className="bg-green-600 hover:bg-green-700"
            >
              <CheckCircle className="mr-2 size-4" />
              {approveProject.isPending ? "Approving..." : "Approve Plan"}
            </Button>
            <Button
              variant="outline"
              onClick={() => setReviseDialogOpen(true)}
            >
              Revise Plan
            </Button>
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={cancelProject.isPending}
              className="text-destructive hover:bg-destructive/10"
            >
              <XCircle className="mr-2 size-4" />
              Cancel
            </Button>
          </div>
        </CardContent>
      </Card>
      <ReviseDialog
        open={reviseDialogOpen}
        onOpenChange={setReviseDialogOpen}
        threadId={threadId}
      />
    </>
  );
}
