import {
  Button,
  Checkbox,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowDownload24Regular,
  DocumentAdd24Regular,
} from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { exportsApi } from "../api/exportsApi";
import type { DataExport, ExportType } from "../api/exportsApi";
import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "../components/OperationFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const TYPE_LABELS: Record<ExportType, string> = {
  visitors: "访客",
  leads: "线索",
  conversations: "对话",
};
const TYPE_PERMISSIONS: Record<ExportType, string> = {
  visitors: "visits.read",
  leads: "leads.read",
  conversations: "conversations.read",
};
const STATUS_LABELS: Record<DataExport["status"], string> = {
  pending: "等待处理",
  processing: "生成中",
  completed: "可下载",
  failed: "生成失败",
  expired: "已过期",
};

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("导出操作发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function saveExportFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ExportsPage() {
  const { user } = useAuth();
  const [exportType, setExportType] = useState<ExportType>("leads");
  const [includeSensitive, setIncludeSensitive] = useState(false);
  const [pendingAction, setPendingAction] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [error, setError] = useState<ApiError>();
  const isAdmin = user?.role === "company_admin" || user?.role === "platform_admin";
  const allowedTypes = useMemo(
    () =>
      (Object.keys(TYPE_LABELS) as ExportType[]).filter((type) =>
        hasPermission(user, TYPE_PERMISSIONS[type], { allowCardOwner: true }),
    ),
    [user],
  );
  const resource = useResource(
    () => allowedTypes.length > 0
      ? exportsApi.list()
      : Promise.resolve({ items: [], total: 0, limit: 50, offset: 0 }),
    allowedTypes.join(","),
  );

  useEffect(() => {
    if (!allowedTypes.includes(exportType) && allowedTypes[0]) {
      setExportType(allowedTypes[0]);
    }
  }, [allowedTypes, exportType]);

  useEffect(() => {
    const active = resource.data?.items.some(
      (item) => item.status === "pending" || item.status === "processing",
    );
    if (!active) return undefined;
    const timer = window.setInterval(resource.reload, 3000);
    return () => window.clearInterval(timer);
  }, [resource.data, resource.reload]);

  const createExport = async () => {
    if (pendingAction || !allowedTypes.includes(exportType)) return;
    setPendingAction("create");
    setNotice(undefined);
    setError(undefined);
    try {
      await exportsApi.create(exportType, isAdmin && includeSensitive);
      setNotice("导出任务已创建，页面会自动更新处理状态。");
      resource.reload();
    } catch (caught) {
      setError(asApiError(caught));
    } finally {
      setPendingAction(undefined);
    }
  };

  const downloadExport = async (item: DataExport) => {
    if (pendingAction) return;
    setPendingAction(item.id);
    setNotice(undefined);
    setError(undefined);
    try {
      const download = await exportsApi.download(item.id, item.fileName);
      saveExportFile(download.blob, download.fileName);
      setNotice("导出文件已开始下载。");
    } catch (caught) {
      setError(asApiError(caught));
      resource.reload();
    } finally {
      setPendingAction(undefined);
    }
  };

  if (allowedTypes.length === 0) {
    return (
      <main className="page-stack">
        <PageHeader title="数据导出" description="异步生成访客、线索和对话 CSV 文件。" />
        <section className="content-panel data-panel">
          <ResourceState
            status="permission"
            description="当前账号没有访客、线索或对话数据的读取权限。"
          />
        </section>
      </main>
    );
  }

  return (
    <main className="page-stack">
      <PageHeader
        title="数据导出"
        description="异步生成 CSV；敏感字段仅企业管理员可选择，文件将在到期后自动清除。"
        actions={
          <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
            刷新
          </Button>
        }
      />
      <section className="content-panel filter-panel" aria-label="创建导出">
        <Select
          aria-label="导出数据类型"
          value={exportType}
          onChange={(_, data) => setExportType(data.value as ExportType)}
        >
          {allowedTypes.map((type) => (
            <option key={type} value={type}>{TYPE_LABELS[type]}</option>
          ))}
        </Select>
        <Checkbox
          label="包含未脱敏联系方式"
          checked={includeSensitive}
          disabled={!isAdmin}
          onChange={(_, data) => setIncludeSensitive(data.checked === true)}
        />
        <Button
          appearance="primary"
          icon={<DocumentAdd24Regular />}
          disabled={Boolean(pendingAction)}
          onClick={() => void createExport()}
        >
          {pendingAction === "create" ? "正在创建" : "创建导出"}
        </Button>
      </section>
      <OperationFeedback notice={notice} error={error} onRetry={resource.reload} />
      <section className="content-panel data-panel">
        {resource.status === "ready" && resource.data ? (
          resource.data.items.length === 0 ? (
            <ResourceState
              status="empty"
              title="尚无导出任务"
              description="选择数据类型后创建第一个导出任务。"
            />
          ) : (
            <div className="table-scroll">
              <Table aria-label="数据导出列表">
                <TableHeader>
                  <TableRow>
                    <TableHeaderCell>数据</TableHeaderCell>
                    <TableHeaderCell>状态</TableHeaderCell>
                    <TableHeaderCell>范围</TableHeaderCell>
                    <TableHeaderCell>行数</TableHeaderCell>
                    <TableHeaderCell>创建时间</TableHeaderCell>
                    <TableHeaderCell>到期时间</TableHeaderCell>
                    <TableHeaderCell />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {resource.data.items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{TYPE_LABELS[item.exportType]}</TableCell>
                      <TableCell>
                        {STATUS_LABELS[item.status]}
                        {item.failureCode ? `（${item.failureCode}）` : ""}
                      </TableCell>
                      <TableCell>{item.includeSensitive ? "含敏感字段" : "已脱敏"}</TableCell>
                      <TableCell>{item.rowCount ?? "—"}</TableCell>
                      <TableCell>{formatTimestamp(item.createdAt)}</TableCell>
                      <TableCell>{item.expiresAt ? formatTimestamp(item.expiresAt) : "—"}</TableCell>
                      <TableCell className="actions-column">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<ArrowDownload24Regular />}
                          disabled={item.status !== "completed" || Boolean(pendingAction)}
                          onClick={() => void downloadExport(item)}
                        >
                          {pendingAction === item.id ? "下载中" : "下载"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
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
