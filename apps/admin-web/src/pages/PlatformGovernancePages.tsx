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
import { ArrowClockwise24Regular, Search24Regular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import { platformApi } from "../api/platformApi";
import type { PlatformAuditProjection, PlatformCompanyAggregate, PlatformServiceHealth, PlatformTaskProjection } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";
import styles from "./PlatformGovernancePages.module.css";

function PageState<T>({ resource, emptyTitle, children }: { resource: ReturnType<typeof useResource<T[]>>; emptyTitle: string; children: (data: T[]) => ReactNode }) {
  if (resource.status !== "ready" || !resource.data) return <section className="content-panel"><ResourceState status={resource.status === "ready" ? "empty" : resource.status} title={resource.status === "empty" ? emptyTitle : undefined} description={resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} /></section>;
  return <>{children(resource.data)}</>;
}

function Refresh({ onClick }: { onClick: () => void }) { return <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={onClick}>刷新</Button>; }
function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (value: string) => void; placeholder: string }) { return <Input className={styles.search} contentBefore={<Search24Regular />} value={value} placeholder={placeholder} onChange={(_, data) => onChange(data.value)} />; }
function Summary({ items }: { items: Array<[string, number, string?]> }) { return <div className={styles.summary} aria-label="运营摘要">{items.map(([label, value, tone]) => <div key={label} className={tone ? styles[tone] : undefined}><span>{label}</span><strong>{value}</strong></div>)}</div>; }

function AggregatePage({ mode }: { mode: "employees" | "visitors" }) {
  const resource = useResource<PlatformCompanyAggregate[]>(() => platformApi.listCompanyAggregates());
  const [query, setQuery] = useState("");
  const employees = mode === "employees";
  return <main className="page-stack"><PageHeader title={employees ? "企业员工概览" : "企业访客概览"} description={employees ? "按企业判断员工覆盖与名片运营准备度，不读取员工联系方式或企业私域内容。" : "按企业观察近 30 天访问活跃度，不读取访客身份和会话正文。"} actions={<Refresh onClick={resource.reload} />} />
    <PageState resource={resource} emptyTitle="当前没有企业聚合数据">{(data) => {
      const filtered = data.filter((item) => item.companyName.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
      const total = data.reduce((sum, item) => sum + (employees ? item.employeeCount : item.visits30d), 0);
      return <><Summary items={employees ? [["接入企业", data.length], ["在用员工", total], ["未配置员工", data.filter((item) => item.employeeCount === 0).length, "warning"]] : [["接入企业", data.length], ["近 30 天访问", total], ["尚无访问", data.filter((item) => item.visits30d === 0).length, "warning"]]} />
        <section className="content-panel data-panel"><div className={styles.toolbar}><SearchBox value={query} onChange={setQuery} placeholder="按企业名称筛选" /><span>显示 {filtered.length} / {data.length} 家企业</span></div><Table className={styles.table} aria-label={employees ? "企业员工聚合" : "企业访客聚合"}><TableHeader><TableRow><TableHeaderCell>企业</TableHeaderCell>{employees ? <><TableHeaderCell>在用员工</TableHeaderCell><TableHeaderCell>运营提醒</TableHeaderCell></> : <><TableHeaderCell>访问</TableHeaderCell><TableHeaderCell>独立访客</TableHeaderCell><TableHeaderCell>最近访问</TableHeaderCell></>}</TableRow></TableHeader><TableBody>{filtered.map((item) => <TableRow key={item.companyId}><TableCell data-label="企业"><strong>{item.companyName}</strong></TableCell>{employees ? <><TableCell data-label="在用员工">{item.employeeCount}</TableCell><TableCell data-label="运营提醒">{item.employeeCount === 0 ? <span className={styles.attention}>建议核对企业管理员与名片配置</span> : "已具备员工运营基础"}</TableCell></> : <><TableCell data-label="访问">{item.visits30d}</TableCell><TableCell data-label="独立访客">{item.uniqueVisitors30d}</TableCell><TableCell data-label="最近访问">{item.lastVisitAt ? formatTimestamp(item.lastVisitAt) : <span className={styles.attention}>暂无访问</span>}</TableCell></>}</TableRow>)}</TableBody></Table></section></>;
    }}</PageState></main>;
}

export function PlatformEmployeesPage() { return <AggregatePage mode="employees" />; }
export function PlatformVisitorsPage() { return <AggregatePage mode="visitors" />; }

export function PlatformTasksPage() {
  const resource = useResource<PlatformTaskProjection[]>(() => platformApi.listTasks());
  const [query, setQuery] = useState(""); const [filter, setFilter] = useState("all");
  return <main className="page-stack"><PageHeader title="任务中心" description="集中观察资料解析、业务事件与失败信号；为了避免重复写入，任务不在此处直接重试。" actions={<Refresh onClick={resource.reload} />} />
    <PageState resource={resource} emptyTitle="当前没有后台任务">{(data) => {
      const failed = data.filter((item) => ["failed", "error"].includes(item.status)).length;
      const active = data.filter((item) => ["queued", "processing", "running"].includes(item.status)).length;
      const filtered = data.filter((item) => {
        const statusMatches = filter === "all" || (filter === "attention" ? ["failed", "error"].includes(item.status) : ["queued", "processing", "running"].includes(item.status));
        const queryMatches = `${item.businessLabel} ${item.companyName ?? ""} ${item.taskType}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
        return statusMatches && queryMatches;
      });
      return <><Summary items={[["全部任务", data.length], ["处理中", active], ["需关注", failed, "danger"]]} /><section className="content-panel data-panel"><div className={styles.toolbar}><SearchBox value={query} onChange={setQuery} placeholder="搜索企业、任务或类型" /><div className={styles.filterGroup}><Button appearance={filter === "all" ? "primary" : "secondary"} size="small" onClick={() => setFilter("all")}>全部</Button><Button appearance={filter === "active" ? "primary" : "secondary"} size="small" onClick={() => setFilter("active")}>处理中</Button><Button appearance={filter === "attention" ? "primary" : "secondary"} size="small" onClick={() => setFilter("attention")}>需关注</Button></div></div><Table className={styles.table} aria-label="平台任务"><TableHeader><TableRow><TableHeaderCell>业务任务</TableHeaderCell><TableHeaderCell>企业</TableHeaderCell><TableHeaderCell>状态</TableHeaderCell><TableHeaderCell>最近更新</TableHeaderCell></TableRow></TableHeader><TableBody>{filtered.map((item) => <TableRow key={item.id}><TableCell data-label="业务任务"><strong>{item.businessLabel}</strong><small>{item.taskType}{item.errorCode ? ` · ${item.errorCode}` : ""}</small></TableCell><TableCell data-label="企业">{item.companyName ?? "平台"}</TableCell><TableCell data-label="状态"><StatusBadge status={item.status} /></TableCell><TableCell data-label="最近更新">{formatTimestamp(item.updatedAt)}</TableCell></TableRow>)}</TableBody></Table>{filtered.length === 0 && <p className={styles.noResults}>没有符合当前筛选条件的任务。</p>}</section></>;
    }}</PageState></main>;
}

export function PlatformAuditPage() {
  const resource = useResource<PlatformAuditProjection[]>(() => platformApi.listAudit()); const [query, setQuery] = useState("");
  return <main className="page-stack"><PageHeader title="审计记录" description="按业务语义查看平台操作轨迹；内部动作代码仅作为次级排障信息。" actions={<Refresh onClick={resource.reload} />} />
    <PageState resource={resource} emptyTitle="当前没有审计记录">{(data) => { const filtered = data.filter((item) => `${item.businessLabel} ${item.actorDisplayName} ${item.action} ${item.resourceType}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())); return <><Summary items={[["可追溯记录", data.length], ["操作者", new Set(data.map((item) => item.actorDisplayName)).size], ["失败记录", data.filter((item) => ["failed", "error"].includes(item.result)).length, "danger"]]} /><section className="content-panel data-panel"><div className={styles.toolbar}><SearchBox value={query} onChange={setQuery} placeholder="搜索操作、操作者或资源" /><span>最近优先</span></div><Table className={styles.table} aria-label="平台审计记录"><TableHeader><TableRow><TableHeaderCell>操作</TableHeaderCell><TableHeaderCell>操作者</TableHeaderCell><TableHeaderCell>结果</TableHeaderCell><TableHeaderCell>时间</TableHeaderCell></TableRow></TableHeader><TableBody>{filtered.map((item) => <TableRow key={item.id}><TableCell data-label="操作"><strong>{item.businessLabel}</strong><small>{item.action} · {item.resourceType}</small></TableCell><TableCell data-label="操作者">{item.actorDisplayName}</TableCell><TableCell data-label="结果"><StatusBadge status={item.result} /></TableCell><TableCell data-label="时间">{formatTimestamp(item.createdAt)}</TableCell></TableRow>)}</TableBody></Table></section></>; }}</PageState></main>;
}

export function PlatformHealthPage() {
  const resource = useResource<PlatformServiceHealth[]>(() => platformApi.getServiceHealth());
  return <main className="page-stack"><PageHeader title="服务健康" description="每项探针独立限时。优先看异常项与检查时间，不将单项异常掩盖为整体正常。" actions={<Refresh onClick={resource.reload} />} />
    <PageState resource={resource} emptyTitle="暂时没有健康检查结果">{(data) => { const attention = data.filter((item) => item.status !== "healthy").length; return <><Summary items={[["检查服务", data.length], ["健康", data.length - attention], ["需处理", attention, "danger"]]} /><section className={styles.healthGrid} aria-label="平台服务健康">{data.map((item) => <article key={item.service} className="content-panel"><header><strong>{item.service}</strong><StatusBadge status={item.status} /></header><p>{item.latencyMs === undefined ? "未配置直接探针" : `响应 ${item.latencyMs} ms`}</p><dl className={styles.healthMeta}><div><dt>检查时间</dt><dd>{formatTimestamp(item.checkedAt)}</dd></div><div><dt>建议</dt><dd>{item.status === "healthy" ? "继续观察" : "核对服务日志与运行配置"}</dd></div></dl>{item.errorCode && <code>{item.errorCode}</code>}</article>)}</section></>; }}</PageState></main>;
}
