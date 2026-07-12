import {
  Button,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular } from "@fluentui/react-icons";
import { useState } from "react";

import type { DashboardOverview, EmployeeAnalyticsPage } from "../api/types";
import { workflowApi } from "../api/workflowApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { PageHeader } from "../components/PageHeader";
import { PaginationBar } from "../components/PaginationBar";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { APP_PATHS, onInternalLinkClick } from "../routing";
import { formatTimestamp } from "../utils/format";

function formatRate(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="dashboard-metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function DashboardContent({ data }: { data: DashboardOverview }) {
  const auth = useAuth();
  const steps = [
    { label: "访问", value: data.visits, path: APP_PATHS.visits, permission: "visits.read", allowCardOwner: true },
    { label: "对话", value: data.conversations, path: APP_PATHS.conversations, permission: "conversations.read", allowCardOwner: true },
    { label: "新线索", value: data.newLeads, path: APP_PATHS.leads, permission: "leads.read", allowCardOwner: true },
    { label: "待处理缺口", value: data.pendingGaps, path: APP_PATHS.knowledgeGaps, permission: "knowledge.read", allowCardOwner: true },
    { label: "未读通知", value: data.unreadNotifications, path: APP_PATHS.notifications },
  ].filter((step) =>
    hasPermission(auth.user, step.permission, {
      allowCardOwner: step.allowCardOwner,
    }),
  );

  return (
    <>
      <section className="content-panel dashboard-overview" aria-label="核心指标">
        <div className="dashboard-metrics">
          <Metric label="访问量" value={data.visits} />
          <Metric label="独立访客" value={data.uniqueVisitors} />
          <Metric label="对话数" value={data.conversations} />
          <Metric label="AI 回答" value={data.aiAnswers} />
          <Metric label="对话转化率" value={formatRate(data.conversationRate)} />
          <Metric label="线索转化率" value={formatRate(data.leadRate)} />
        </div>
        <div className="dashboard-generated">
          服务端统计生成于 {formatTimestamp(data.generatedAt)}
        </div>
      </section>

      <section className="content-panel workflow-strip" aria-labelledby="workflow-title">
        <div className="section-heading-inline">
          <div>
            <h2 id="workflow-title">客户转化链路</h2>
            <p>从访问记录进入对话、纪要和线索跟进，异常问题进入知识补齐。</p>
          </div>
        </div>
        <div className="workflow-steps">
          {steps.map((step, index) => (
            <a
              key={step.path}
              href={step.path}
              onClick={(event) => onInternalLinkClick(event, step.path)}
            >
              <span>{step.label}</span>
              <strong>{step.value}</strong>
              {index < steps.length - 1 && <i aria-hidden>/</i>}
            </a>
          ))}
        </div>
      </section>

      <section className="content-panel data-panel" aria-labelledby="daily-title">
        <div className="section-heading-inline">
          <div>
            <h2 id="daily-title">每日趋势</h2>
            <p>访问、对话和线索均来自真实业务记录。</p>
          </div>
        </div>
        {data.daily.length === 0 ? (
          <ResourceState
            compact
            status="empty"
            title="当前周期暂无趋势数据"
            description="访客开始访问后，日维度统计会显示在这里。"
          />
        ) : (
          <div className="table-scroll">
            <Table aria-label="每日趋势">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>日期</TableHeaderCell>
                  <TableHeaderCell>访问</TableHeaderCell>
                  <TableHeaderCell>对话</TableHeaderCell>
                  <TableHeaderCell>线索</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.daily.map((item) => (
                  <TableRow key={item.day}>
                    <TableCell>{item.day}</TableCell>
                    <TableCell>{item.visits}</TableCell>
                    <TableCell>{item.conversations}</TableCell>
                    <TableCell>{item.leads}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>
    </>
  );
}

function EmployeePerformance({
  resource,
  dashboard,
  onOffsetChange,
}: {
  resource: ReturnType<typeof useResource<EmployeeAnalyticsPage>>;
  dashboard?: DashboardOverview;
  onOffsetChange: (offset: number) => void;
}) {
  const data = resource.data;
  const reconciliation = data?.reconciliation;
  const reconciled = Boolean(
    dashboard &&
      reconciliation &&
      dashboard.visits === reconciliation.visits &&
      dashboard.conversations === reconciliation.conversations &&
      dashboard.totalLeads === reconciliation.totalLeads &&
      dashboard.uniqueVisitors === reconciliation.uniqueVisitors,
  );

  return (
    <section className="content-panel data-panel" aria-labelledby="employee-performance-title">
      <div className="section-heading-inline">
        <div>
          <h2 id="employee-performance-title">员工表现</h2>
          <p>企业管理员查看全员；名片员工仅能看到本人，数据范围由服务端权限控制。</p>
        </div>
        <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
          刷新员工数据
        </Button>
      </div>

      {resource.status !== "ready" || !data ? (
        <ResourceState
          compact
          status={resource.status === "ready" ? "empty" : resource.status}
          title={resource.status === "empty" ? "当前周期暂无员工表现" : undefined}
          description={resource.error?.message}
          errorCode={resource.error?.code}
          requestId={resource.error?.requestId}
          onRetry={resource.status === "error" ? resource.reload : undefined}
        />
      ) : data.items.length === 0 ? (
        <ResourceState
          compact
          status="empty"
          title="当前周期暂无员工表现"
          description="员工名片产生访问、对话或线索后会显示在这里。"
        />
      ) : (
        <>
          <div className="analytics-reconciliation" role="status">
            <strong>{reconciled ? "与业务总览已对账" : dashboard ? "与业务总览存在差异" : "员工汇总"}</strong>
            <span>
              访问 {data.reconciliation.visits} · 独立访客 {data.reconciliation.uniqueVisitors} · 对话 {data.reconciliation.conversations} · 线索 {data.reconciliation.totalLeads}
            </span>
            {data.reconciliation.employeeUniqueVisitorsSum !== data.reconciliation.uniqueVisitors && (
              <span>员工独立访客合计 {data.reconciliation.employeeUniqueVisitorsSum}；同一访客访问多位员工时，公司口径仅去重一次。</span>
            )}
          </div>
          <div className="table-scroll">
            <Table aria-label="员工表现">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>员工</TableHeaderCell>
                  <TableHeaderCell>名片</TableHeaderCell>
                  <TableHeaderCell>访问</TableHeaderCell>
                  <TableHeaderCell>独立访客</TableHeaderCell>
                  <TableHeaderCell>对话</TableHeaderCell>
                  <TableHeaderCell>线索</TableHeaderCell>
                  <TableHeaderCell>对话率</TableHeaderCell>
                  <TableHeaderCell>线索率</TableHeaderCell>
                  <TableHeaderCell>最近活跃</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((employee) => (
                  <TableRow key={employee.membershipId}>
                    <TableCell>{employee.displayName}</TableCell>
                    <TableCell>{employee.cardCount}</TableCell>
                    <TableCell>{employee.visits}</TableCell>
                    <TableCell>{employee.uniqueVisitors}</TableCell>
                    <TableCell>{employee.conversations}</TableCell>
                    <TableCell>{employee.leads}</TableCell>
                    <TableCell>{formatRate(employee.conversationRate)}</TableCell>
                    <TableCell>{formatRate(employee.leadRate)}</TableCell>
                    <TableCell>{employee.lastActivityAt ? formatTimestamp(employee.lastActivityAt) : "暂无活跃"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <PaginationBar total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={onOffsetChange} />
          <div className="dashboard-generated">员工统计生成于 {formatTimestamp(data.generatedAt)}</div>
        </>
      )}
    </section>
  );
}

export function OverviewPage() {
  const [periodDays, setPeriodDays] = useState(30);
  const [employeeOffset, setEmployeeOffset] = useState(0);
  const resource = useResource(
    () => workflowApi.getDashboard(periodDays),
    periodDays,
  );
  const employeeResource = useResource(
    () => workflowApi.listEmployeeAnalytics({ periodDays, limit: 20, offset: employeeOffset }),
    `${periodDays}:${employeeOffset}`,
  );

  const changePeriod = (days: number) => {
    setPeriodDays(days);
    setEmployeeOffset(0);
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="业务工作台"
        description={`聚合最近 ${periodDays} 天的访客、AI 对话、销售线索和知识运营信号。`}
        actions={
          <div className="header-filter-actions">
            <Select
              aria-label="统计周期"
              value={String(periodDays)}
              onChange={(_, data) => changePeriod(Number(data.value))}
            >
              <option value="7">最近 7 天</option>
              <option value="30">最近 30 天</option>
              <option value="90">最近 90 天</option>
            </Select>
            <Button
              appearance="subtle"
              icon={<ArrowClockwise24Regular />}
              onClick={resource.reload}
            >
              刷新
            </Button>
          </div>
        }
      />

      {resource.status === "ready" && resource.data ? (
        <>
          <DashboardContent data={resource.data} />
          <EmployeePerformance
            resource={employeeResource}
            dashboard={resource.data}
            onOffsetChange={setEmployeeOffset}
          />
        </>
      ) : (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            description={resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        </section>
      )}
      {resource.status !== "ready" && (
        <EmployeePerformance resource={employeeResource} onOffsetChange={setEmployeeOffset} />
      )}
    </main>
  );
}
