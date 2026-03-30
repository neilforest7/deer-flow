"use client";

import { MessageSquare, FolderKanban } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function WorkspaceTabs() {
  const pathname = usePathname();
  const activeTab = pathname.startsWith("/workspace/projects")
    ? "projects"
    : "chats";

  return (
    <Tabs value={activeTab} className="w-full">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="chats" asChild>
          <Link href="/workspace/chats">
            <MessageSquare className="mr-2 size-4" />
            Chats
          </Link>
        </TabsTrigger>
        <TabsTrigger value="projects" asChild>
          <Link href="/workspace/projects">
            <FolderKanban className="mr-2 size-4" />
            Projects
          </Link>
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
