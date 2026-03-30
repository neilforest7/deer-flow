"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useReviseProject } from "@/core/projects/hooks";

interface ReviseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  threadId: string;
}

export function ReviseDialog({
  open,
  onOpenChange,
  threadId,
}: ReviseDialogProps) {
  const [feedback, setFeedback] = useState("");
  const reviseProject = useReviseProject();

  const handleRevise = async () => {
    if (!feedback.trim()) return;

    try {
      await reviseProject.mutateAsync({ threadId, feedback: feedback.trim() });
      onOpenChange(false);
      setFeedback("");
    } catch (error) {
      console.error("Failed to revise project:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revise Plan</DialogTitle>
          <DialogDescription>
            Provide feedback for plan revision
          </DialogDescription>
        </DialogHeader>
        <Textarea
          placeholder="e.g., Add error handling for API failures, include unit tests"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={6}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleRevise}
            disabled={!feedback.trim() || reviseProject.isPending}
          >
            {reviseProject.isPending ? "Submitting..." : "Submit Feedback"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
