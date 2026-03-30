"use client";

import { useState } from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CreateProjectDialog } from "@/components/workspace/create-project-dialog";
import { ProjectList } from "@/components/workspace/project-list";

export default function ProjectsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Projects</h1>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="mr-2 size-4" />
            New Project
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ProjectList />
      </div>
      <CreateProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
