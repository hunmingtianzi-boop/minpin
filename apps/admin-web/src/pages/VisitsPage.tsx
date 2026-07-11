import {
  Button,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  Chat24Regular,
  Dismiss24Regular,
  Filter24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { workflowApi } from "../api/workflowApi";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { APP_PATHS, navigate } from "../routing";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 20;

function formatDuration(seconds?: number): string {
  if (seconds === undefined) return "访问中";
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`;
}

export function VisitsPage() {
  const [offset, setOffset] = useState(0);
  const [cardDraft, setCardDraft] = useState("");
  const [cardId, setCardId] = useState("");
  const resource = useResource(
    () =>
      workflowApi.listVisits({
        limit: PAGE_SIZE,
        offset,
        cardId: cardId || undefined,
      }),
    `${offset}:${cardId}`,
  );

  const applyFilter = () => {
    const next = cardDraft.trim();
    if (next === cardId && offset === 0) resource.reload();
    setOffset(0);
    setCardId(next);
  };

  const clearFilter = () => {
    setCardDraft("");
    setOffset(0);
    setCardId("");
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="访问记录"
        description="按名片查看访客来源、停留时长和对话转化，数据不含主观推断。"
        actions={
          <Button
            appearance="subtle"
            icon={<ArrowClockwise24Regular />}
            onClick={resource.reload}
          >
            刷新
          </Button>
        }
      />

      <section className="content-panel filter-panel" aria-label="访问筛选">
        <Input
          aria-label="名片 ID"
          placeholder="输入名片 ID"
          value={cardDraft}
          onChange={(_, data) => setCardDraft(data.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") applyFilter();
          }}
        />
        <Button icon={<Filter24Regular />} onClick={applyFilter}>
          筛选
        </Button>
        {cardId && (
          <Button appearance="subtle" icon={<Dismiss24Regular />} onClick={clearFilter}>
            清除
          </Button>
        )}
      </section>

      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="没有匹配的访问记录"
              description="可以清除名片筛选，或等待新访客进入公开名片。"
            />
          ) : (
            <>
              <div className="table-scroll">
                <Table aria-label="访问记录列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>名片</TableHeaderCell>
                      <TableHeaderCell>来源</TableHeaderCell>
                      <TableHeaderCell>开始时间</TableHeaderCell>
                      <TableHeaderCell>停留时长</TableHeaderCell>
                      <TableHeaderCell>对话数</TableHeaderCell>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((visit) => (
                      <TableRow key={visit.id}>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{visit.cardDisplayName}</strong>
                            <code>{visit.visitorId}</code>
                          </div>
                        </TableCell>
                        <TableCell>{visit.source || "直接访问"}</TableCell>
                        <TableCell className="updated-column">
                          {formatTimestamp(visit.startedAt)}
                        </TableCell>
                        <TableCell>{formatDuration(visit.durationSeconds)}</TableCell>
                        <TableCell>{visit.conversationCount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="panel-footer-row">
                <Button
                  appearance="subtle"
                  icon={<Chat24Regular />}
                  onClick={() => navigate(APP_PATHS.conversations)}
                >
                  查看对话
                </Button>
                <PaginationBar
                  total={resource.data.total}
                  limit={resource.data.limit}
                  offset={resource.data.offset}
                  onOffsetChange={setOffset}
                />
              </div>
            </>
          )
        ) : (
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        )}
      </section>
    </main>
  );
}
