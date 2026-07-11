import { Badge } from "@fluentui/react-components";

import { knowledgeStatusLabel } from "../utils/format";

export function StatusBadge({ status }: { status?: string }) {
  if (!status) return <Badge appearance="outline">状态未提供</Badge>;
  const color =
    ["published", "indexed", "completed", "won", "verified"].includes(status)
      ? "success"
      : ["review_pending", "pending", "new", "active", "following", "indexing", "in_progress"].includes(status)
        ? "warning"
        : ["blocked", "failed", "rejected", "lost", "invalid"].includes(status)
          ? "danger"
          : ["archived", "closed", "expired"].includes(status)
          ? "subtle"
          : "informative";
  return (
    <Badge appearance="tint" color={color}>
      {knowledgeStatusLabel(status)}
    </Badge>
  );
}
