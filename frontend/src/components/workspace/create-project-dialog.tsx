"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

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
import { useCreateProject } from "@/core/projects/hooks";

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateProjectDialog({
  open,
  onOpenChange,
}: CreateProjectDialogProps) {
  const [objective, setObjective] = useState("");
  const router = useRouter();
  const createProject = useCreateProject();

  const handleCreate = async () => {
    if (!objective.trim()) return;

    try {
      const result = await createProject.mutateAsync(objective.trim());
      onOpenChange(false);
      setObjective("");
      router.push(`/workspace/projects/${result.thread_id}`);
    } catch (error) {
      console.error("Failed to create project:", error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Project</DialogTitle>
          <DialogDescription>
            Describe your project objective to get started
          </DialogDescription>
        </DialogHeader>
        <Textarea
          placeholder="e.g., Build a user authentication system with JWT"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          rows={4}
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!objective.trim() || createProject.isPending}
          >
            {createProject.isPending ? "Creating..." : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
