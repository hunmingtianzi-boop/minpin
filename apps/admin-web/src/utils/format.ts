export function formatTimestamp(value?: string): string {
  if (!value) return "未提供";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function knowledgeStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: "草稿",
    drafted: "已起草",
    review_pending: "待审核",
    published: "已发布",
    archived: "已归档",
    active: "进行中",
    closed: "已结束",
    expired: "已过期",
    blocked: "已阻断",
    new: "新线索",
    viewed: "已查看",
    following: "跟进中",
    won: "已成交",
    lost: "已失败",
    invalid: "无效",
    pending: "待处理",
    approved: "已通过",
    indexing: "索引中",
    indexed: "已入库",
    rejected: "已拒绝",
    failed: "处理失败",
    verified: "已核验",
    in_progress: "处理中",
    completed: "已完成",
  };
  return labels[status] ?? status;
}
