"use client";

import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";

import { ProjectList } from "./project-list";
import { RecentChatList } from "./recent-chat-list";
import { WorkspaceHeader } from "./workspace-header";
import { WorkspaceNavChatList } from "./workspace-nav-chat-list";
import { WorkspaceNavMenu } from "./workspace-nav-menu";
import { WorkspaceTabs } from "./workspace-tabs";

export function WorkspaceSidebar({
  ...props
}: React.ComponentProps<typeof Sidebar>) {
  const { open: isSidebarOpen } = useSidebar();
  const pathname = usePathname();
  const isProjectsView = pathname.startsWith("/workspace/projects");

  return (
    <>
      <Sidebar variant="sidebar" collapsible="icon" {...props}>
        <SidebarHeader className="space-y-2 py-2">
          <WorkspaceHeader />
          {isSidebarOpen && <WorkspaceTabs />}
        </SidebarHeader>
        <SidebarContent>
          {isProjectsView ? (
            isSidebarOpen && <ProjectList />
          ) : (
            <>
              <WorkspaceNavChatList />
              {isSidebarOpen && <RecentChatList />}
            </>
          )}
        </SidebarContent>
        <SidebarFooter>
          <WorkspaceNavMenu />
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
    </>
  );
}
