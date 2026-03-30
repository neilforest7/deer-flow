"use client";

import { Progress } from "@/components/ui/progress";
import type { Phase } from "@/core/projects/types";

interface PhaseProgressProps {
  phase: Phase;
}

const phases: Phase[] = [
  "intake",
  "discovery",
  "planning",
  "awaiting_approval",
  "build",
  "qa_gate",
  "delivery",
  "done",
];

export function PhaseProgress({ phase }: PhaseProgressProps) {
  const currentIndex = phases.indexOf(phase);
  const progress = ((currentIndex + 1) / phases.length) * 100;

  return (
    <div className="space-y-2">
      <Progress value={progress} className="h-2" />
      <p className="text-muted-foreground text-xs">
        Phase {currentIndex + 1} of {phases.length}
      </p>
    </div>
  );
}
