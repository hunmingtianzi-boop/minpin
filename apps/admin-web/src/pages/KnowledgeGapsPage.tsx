import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
  OverlayDrawer,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  Checkmark24Regular,
  Dismiss24Regular,
  Edit24Regular,
  Eye24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { ApiError } from "../api/client";
import type { KnowledgeGap, KnowledgeGapStatus } from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 20;
type GapAction = "draft" | "approve" | "reject";

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("处理知识缺口时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

function GapDrawer({
  gap,
  onClose,
  onChanged,
}: {
  gap: KnowledgeGap;
  onClose: () => void;
  onChanged: () => void;
}) {
  const auth = useAuth();
  const canDraft = hasPermission(auth.user, "knowledge.review");
  const canApprove = hasPermission(auth.user, "knowledge.publish");
  const canReject = hasPermission(auth.user, "knowledge.review");
  const [current, setCurrent] = useState(gap);
  const [answer, setAnswer] = useState(gap.suggestedAnswer || "");
  const [pending, setPending] = useState<GapAction>();
  const [lastAction, setLastAction] = useState<GapAction>("draft");
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const run = async (action: GapAction) => {
    if (pending) return;
    setPending(action);
    setLastAction(action);
    setError(undefined);
    setNotice(undefined);
    try {
      let updated: KnowledgeGap;
      if (action === "draft") {
        updated = await workflowApi.updateKnowledgeGap(current.id, answer);
      } else if (action === "approve") {
        if (answer.trim() !== (current.suggestedAnswer || "").trim()) {
          await workflowApi.updateKnowledgeGap(current.id, answer);
        }
        updated = await workflowApi.approveKnowledgeGap(current.id);
      } else {
        updated = await workflowApi.rejectKnowledgeGap(current.id);
      }
      setCurrent(updated);
      setAnswer(updated.suggestedAnswer || answer);
      setNotice(
        action === "draft"
          ? "建议答案已保存。"
          : action === "approve"
            ? "知识缺口已通过并进入发布索引流程。"
            : "知识缺口已驳回。",
      );
      onChanged();
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setPending(undefined);
    }
  };

  return (
    <OverlayDrawer position="end" size="large" open onOpenChange={(_, data) => !data.open && onClose()}>
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button appearance="subtle" icon={<Dismiss24Regular />} aria-label="关闭知识缺口" onClick={onClose} />
          }
        >
          知识缺口处理
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <div className="drawer-command-bar">
          <StatusBadge status={current.status} />
          <code>{current.id}</code>
        </div>
        <OperationFeedback
          notice={notice}
          error={error}
          onRetry={() => void run(lastAction)}
        />
        <div className="drawer-section-stack">
          <section className="drawer-section">
            <h3>待补齐问题</h3>
            <p className="gap-question">{current.question}</p>
            <dl className="detail-grid two-columns">
              <div>
                <dt>缺口原因</dt>
                <dd>{current.reason || "未标记"}</dd>
              </div>
              <div>
                <dt>发生次数</dt>
                <dd>{current.occurrenceCount}</dd>
              </div>
              <div>
                <dt>最后发现</dt>
                <dd>{formatTimestamp(current.lastSeenAt)}</dd>
              </div>
              <div>
                <dt>对话 ID</dt>
                <dd><code>{current.conversationId}</code></dd>
              </div>
            </dl>
          </section>
          <section className="drawer-section">
            <h3>建议答案</h3>
            <Field
              label="答案内容"
              hint="通过后会以公开知识的方式发布并建立索引。"
              required={canDraft}
            >
              <Textarea
                resize="vertical"
                value={answer}
                readOnly={!canDraft}
                onChange={(_, data) => setAnswer(data.value)}
                placeholder="输入经企业确认的标准答案。"
              />
            </Field>
            <div className="drawer-form-actions split-actions">
              <div>
                {canReject && current.status !== "rejected" && (
                  <Button
                    className="danger-outline-button"
                    disabled={Boolean(pending)}
                    onClick={() => void run("reject")}
                  >
                    {pending === "reject" ? "正在驳回" : "驳回缺口"}
                  </Button>
                )}
              </div>
              <div>
                {canDraft && (
                  <Button
                    icon={<Edit24Regular />}
                    disabled={Boolean(pending) || !answer.trim()}
                    onClick={() => void run("draft")}
                  >
                    {pending === "draft" ? "正在保存" : "保存草稿"}
                  </Button>
                )}
                {canApprove && !["indexed", "rejected"].includes(current.status) && (
                  <Button
                    appearance="primary"
                    icon={<Checkmark24Regular />}
                    disabled={Boolean(pending) || !answer.trim()}
                    onClick={() => void run("approve")}
                  >
                    {pending === "approve" ? "正在发布" : "通过并发布"}
                  </Button>
                )}
              </div>
            </div>
          </section>
        </div>
      </DrawerBody>
    </OverlayDrawer>
  );
}

export function KnowledgeGapsPage() {
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState<KnowledgeGapStatus | "">("pending");
  const [selected, setSelected] = useState<KnowledgeGap>();
  const resource = useResource(
    () => workflowApi.listKnowledgeGaps({ limit: PAGE_SIZE, offset, status: status || undefined }),
    `${offset}:${status}`,
  );

  return (
    <main className="page-stack">
      <PageHeader
        title="知识缺口"
        description="将 AI 未能稳定回答的真实问题转为经企业审核的公开知识。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新</Button>
        }
      />
      <section className="content-panel filter-panel" aria-label="知识缺口筛选">
        <Select
          aria-label="缺口状态"
          value={status}
          onChange={(_, data) => {
            setOffset(0);
            setStatus(data.value as KnowledgeGapStatus | "");
          }}
        >
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="drafted">已起草</option>
          <option value="approved">已通过</option>
          <option value="indexing">索引中</option>
          <option value="indexed">已入库</option>
          <option value="rejected">已驳回</option>
          <option value="failed">处理失败</option>
        </Select>
      </section>
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState status="empty" title="当前筛选下没有知识缺口" description="AI 识别到新的缺口后会显示在这里。" />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="知识缺口列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>问题</TableHeaderCell>
                      <TableHeaderCell>状态</TableHeaderCell>
                      <TableHeaderCell>原因</TableHeaderCell>
                      <TableHeaderCell>发生次数</TableHeaderCell>
                      <TableHeaderCell>最后发现</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((gap) => (
                      <TableRow key={gap.id}>
                        <TableCell><div className="knowledge-title-cell"><strong>{gap.question}</strong><span>{gap.suggestedAnswer || "尚未起草答案"}</span></div></TableCell>
                        <TableCell><StatusBadge status={gap.status} /></TableCell>
                        <TableCell>{gap.reason || "未标记"}</TableCell>
                        <TableCell>{gap.occurrenceCount}</TableCell>
                        <TableCell className="updated-column">{formatTimestamp(gap.lastSeenAt)}</TableCell>
                        <TableCell className="actions-column"><Button appearance="subtle" size="small" icon={<Eye24Regular />} onClick={() => setSelected(gap)}>处理</Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar total={resource.data.total} limit={resource.data.limit} offset={resource.data.offset} onOffsetChange={setOffset} />
            </>
          )
        ) : (
          <ResourceState status={resource.status === "ready" ? "empty" : resource.status} description={resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} />
        )}
      </section>
      {selected && <GapDrawer key={`${selected.id}:${selected.updatedAt}`} gap={selected} onClose={() => setSelected(undefined)} onChanged={resource.reload} />}
    </main>
  );
}
