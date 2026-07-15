import {
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular, Eye24Regular } from "@fluentui/react-icons";
import { useState } from "react";

import { workflowApi } from "../api/workflowApi";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { appHref } from "../routing";
import { formatTimestamp } from "../utils/format";

const PAGE_SIZE = 20;

function scoreLabel(score: number): string {
  if (score >= 0.85) return "高";
  if (score >= 0.7) return "中";
  return "低";
}

export function OpportunitiesPage() {
  const [offset, setOffset] = useState(0);
  const resource = useResource(
    () => workflowApi.listOpportunities({ limit: PAGE_SIZE, offset }),
    String(offset),
  );

  return (
    <main className="page-stack">
      <PageHeader
        title="潜在机会"
        description="从高意向 AI 提问中识别匿名机会；只有访客主动提交并同意联系后，才会进入销售线索。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
            刷新
          </Button>
        }
      />

      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="暂未识别到潜在机会"
              description="当访客提出报价、预算、采购、合作、演示或联系等问题时，会显示在这里。"
            />
          ) : (
            <>
              <p className="subtle-note">
                此列表不展示 IP 或联系方式。点击详情可审阅已授权的完整对话，并按需生成纪要。
              </p>
              <div className="table-scroll">
                <Table aria-label="潜在机会列表">
                  <TableHeader>
                    <TableRow>
                      <TableHeaderCell>来源名片</TableHeaderCell>
                      <TableHeaderCell>高意向问题</TableHeaderCell>
                      <TableHeaderCell>识别原因</TableHeaderCell>
                      <TableHeaderCell>意向</TableHeaderCell>
                      <TableHeaderCell>留资状态</TableHeaderCell>
                      <TableHeaderCell>最后活跃</TableHeaderCell>
                      <TableHeaderCell />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {resource.data.items.map((opportunity) => (
                      <TableRow key={opportunity.conversationId}>
                        <TableCell>
                          <div className="entity-title-cell compact-cell">
                            <strong>{opportunity.cardDisplayName}</strong>
                            <code>{opportunity.conversationId}</code>
                          </div>
                        </TableCell>
                        <TableCell className="gap-question">{opportunity.question}</TableCell>
                        <TableCell>{opportunity.reason}</TableCell>
                        <TableCell>
                          <Badge color={opportunity.score >= 0.85 ? "danger" : "warning"}>
                            {scoreLabel(opportunity.score)}意向
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge appearance="outline" color={opportunity.hasConsentedLead ? "success" : "informative"}>
                            {opportunity.hasConsentedLead ? "已留资" : "匿名未留资"}
                          </Badge>
                        </TableCell>
                        <TableCell className="updated-column">
                          {formatTimestamp(opportunity.lastActivityAt)}
                        </TableCell>
                        <TableCell className="actions-column">
                          <a
                            className="inline-action-link"
                            href={appHref(`/conversations?visitorId=${encodeURIComponent(opportunity.visitorId)}`)}
                          >
                            <Eye24Regular />
                            审阅对话
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <PaginationBar
                total={resource.data.total}
                limit={resource.data.limit}
                offset={resource.data.offset}
                onOffsetChange={setOffset}
              />
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
