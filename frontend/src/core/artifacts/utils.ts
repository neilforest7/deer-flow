import { getBackendBaseURL } from "../config";
import type { AgentThread } from "../threads";

export function urlOfArtifact({
  filepath,
  threadId,
  download = false,
  preview = false,
  isMock = false,
}: {
  filepath: string;
  threadId: string;
  download?: boolean;
  preview?: boolean;
  isMock?: boolean;
}) {
  const query = new URLSearchParams();
  if (download) {
    query.set("download", "true");
  }
  if (preview) {
    query.set("preview", "true");
  }
  const suffix = query.size > 0 ? `?${query.toString()}` : "";

  if (isMock) {
    return `${getBackendBaseURL()}/mock/api/threads/${threadId}/artifacts${filepath}${suffix}`;
  }
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${filepath}${suffix}`;
}

export function extractArtifactsFromThread(thread: AgentThread) {
  return thread.values.artifacts ?? [];
}

export function resolveArtifactURL(absolutePath: string, threadId: string) {
  return `${getBackendBaseURL()}/api/threads/${threadId}/artifacts${absolutePath}`;
}
