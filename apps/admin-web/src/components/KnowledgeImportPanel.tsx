import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular, ArrowUpload24Regular } from "@fluentui/react-icons";
import { useContext, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  knowledgeImportsApi,
  type KnowledgeImportBatch,
  type KnowledgeImportBatchStatus,
  type KnowledgeImportItemStatus,
} from "../api/knowledgeImportsApi";
import { AuthContext } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import { OperationFeedback } from "./OperationFeedback";
import { ResourceState } from "./ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

export const KNOWLEDGE_IMPORT_MAX_FILES = 5;
export const KNOWLEDGE_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024;
export const KNOWLEDGE_IMPORT_MAX_BATCH_BYTES = 25 * 1024 * 1024;
const allowedExtensions = new Set(["pdf", "docx", "csv"]);

const batchLabels: Record<KnowledgeImportBatchStatus, string> = {
  pending: "等待处理",
  processing: "处理中",
  completed: "已完成",
  completed_with_errors: "部分完成",
  failed: "批次失败",
  dead_letter: "处理终止",
};
const itemLabels: Record<KnowledgeImportItemStatus, string> = {
  pending: "等待处理",
  processing: "处理中",
  completed: "草稿已创建",
  failed: "失败",
  dead_letter: "处理终止",
};

export function validateKnowledgeImportFiles(files: File[]): string | undefined {
  if (files.length === 0) return "请选择要导入的文件。";
  if (files.length > KNOWLEDGE_IMPORT_MAX_FILES) return "每批最多选择 5 个文件。";
  for (const file of files) {
    const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
    if (!allowedExtensions.has(extension)) {
      return `不支持文件“${file.name}”，仅可上传 PDF、DOCX 或 CSV。`;
    }
    if (file.size > KNOWLEDGE_IMPORT_MAX_FILE_BYTES) {
      return `文件“${file.name}”超过 10 MiB。`;
    }
  }
  if (files.reduce((sum, file) => sum + file.size, 0) > KNOWLEDGE_IMPORT_MAX_BATCH_BYTES) {
    return "本批文件总大小超过 25 MiB。";
  }
  return undefined;
}

function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("创建知识导入批次时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

function isActive(batch: KnowledgeImportBatch): boolean {
  return batch.status === "pending" || batch.status === "processing";
}

function ImportDetail({ batch }: { batch: KnowledgeImportBatch }) {
  const completed = batch.succeededItems + batch.failedItems;
  const progress = batch.totalItems > 0 ? completed / batch.totalItems : 0;
  return (
    <div className="knowledge-import-detail">
      <div className="knowledge-import-progress-copy">
        <strong>{batchLabels[batch.status]}</strong>
        <span>{completed}/{batch.totalItems} 项已处理</span>
      </div>
      <ProgressBar value={progress} aria-label="导入批次进度" />
      <div className="table-scroll">
        <Table aria-label="知识导入逐文件结果" size="small">
          <TableHeader><TableRow>
            <TableHeaderCell>文件</TableHeaderCell><TableHeaderCell>类型</TableHeaderCell>
            <TableHeaderCell>状态</TableHeaderCell><TableHeaderCell>结果</TableHeaderCell>
          </TableRow></TableHeader>
          <TableBody>
            {batch.items.map((item) => (
              <TableRow key={item.id}>
                <TableCell>{item.fileName}{item.rowNumber ? ` · 第 ${item.rowNumber} 行` : ""}</TableCell>
                <TableCell>{item.sourceType.toUpperCase()}</TableCell>
                <TableCell><Badge appearance="tint" color={item.status === "completed" ? "success" : item.status === "failed" || item.status === "dead_letter" ? "danger" : "informative"}>{itemLabels[item.status]}</Badge></TableCell>
                <TableCell>{item.errorCode ? `错误码：${item.errorCode}` : item.documentId ? "已生成待审核草稿" : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

export function KnowledgeImportPanel() {
  const auth = useContext(AuthContext);
  const canImport = auth?.user
    ? hasPermission(auth.user, "knowledge.write")
    : true;
  const inputRef = useRef<HTMLInputElement>(null);
  const resource = useResource(() => knowledgeImportsApi.list());
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<KnowledgeImportBatch>();
  const [uploading, setUploading] = useState(false);
  const [validationError, setValidationError] = useState<string>();
  const [operationError, setOperationError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    const active = resource.data?.items.some(isActive) || (selectedBatch && isActive(selectedBatch));
    if (!active) return undefined;
    const timer = window.setInterval(() => {
      resource.reload();
      if (selectedBatch && isActive(selectedBatch)) {
        void knowledgeImportsApi.get(selectedBatch.id).then(setSelectedBatch, () => undefined);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [resource.data, resource.reload, selectedBatch]);

  const chooseFiles = (files: File[]) => {
    const error = validateKnowledgeImportFiles(files);
    setSelectedFiles(error ? [] : files);
    setValidationError(error);
    setOperationError(undefined);
    setNotice(undefined);
  };

  const upload = async () => {
    const error = validateKnowledgeImportFiles(selectedFiles);
    if (error || uploading) {
      setValidationError(error);
      return;
    }
    setUploading(true);
    setOperationError(undefined);
    setNotice(undefined);
    try {
      const batch = await knowledgeImportsApi.create(selectedFiles);
      setSelectedBatch(batch);
      setSelectedFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      setNotice("导入批次已创建。内容只会生成草稿，仍需人工审核并发布。");
      resource.reload();
    } catch (caught) {
      setOperationError(asApiError(caught));
    } finally {
      setUploading(false);
    }
  };

  const openBatch = async (batch: KnowledgeImportBatch) => {
    setOperationError(undefined);
    try {
      setSelectedBatch(await knowledgeImportsApi.get(batch.id));
    } catch (caught) {
      setOperationError(asApiError(caught));
    }
  };

  return (
    <section className="content-panel knowledge-import-panel" aria-labelledby="knowledge-import-title">
      <div className="knowledge-import-heading">
        <div><h2 id="knowledge-import-title">文件与批量导入</h2><p>支持 PDF、DOCX 和 CSV；CSV 每行一条知识，必须包含 raw_text 列。导入结果均为草稿，不会自动发布；请审核后再发布。</p></div>
        <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>刷新批次</Button>
      </div>

      {!canImport ? (
        <ResourceState status="permission" description="当前账号没有知识写入权限，无法创建导入批次。" compact />
      ) : (
        <div className="knowledge-import-picker">
          <input ref={inputRef} aria-label="选择知识文件" type="file" accept=".pdf,.docx,.csv" multiple disabled={uploading} onChange={(event) => chooseFiles(Array.from(event.target.files ?? []))} />
          <span>{selectedFiles.length > 0 ? `已选择 ${selectedFiles.length} 个文件` : "每批 1–5 个；单文件不超过 10 MiB，批次不超过 25 MiB。"}</span>
          <Button appearance="primary" icon={<ArrowUpload24Regular />} disabled={uploading || selectedFiles.length === 0} onClick={() => void upload()}>{uploading ? "正在上传" : "创建导入批次"}</Button>
        </div>
      )}
      {validationError && <MessageBar intent="error"><MessageBarBody>{validationError}</MessageBarBody></MessageBar>}
      <OperationFeedback
        notice={notice}
        error={operationError}
        onRetry={selectedFiles.length > 0 ? () => void upload() : resource.reload}
      />
      {selectedBatch && <ImportDetail batch={selectedBatch} />}

      {resource.status !== "ready" ? (
        <ResourceState status={resource.status} title={resource.status === "empty" ? "尚无导入批次" : undefined} description={resource.status === "empty" ? "选择文件后创建第一个异步导入批次。" : resource.error?.message} errorCode={resource.error?.code} requestId={resource.error?.requestId} onRetry={resource.status === "error" ? resource.reload : undefined} compact />
      ) : resource.data && resource.data.items.length === 0 ? (
        <ResourceState status="empty" title="尚无导入批次" description="选择文件后创建第一个异步导入批次。" compact />
      ) : resource.data ? (
        <div className="table-scroll"><Table aria-label="知识导入批次列表" size="small">
          <TableHeader><TableRow><TableHeaderCell>批次</TableHeaderCell><TableHeaderCell>状态</TableHeaderCell><TableHeaderCell>进度</TableHeaderCell><TableHeaderCell>创建时间</TableHeaderCell><TableHeaderCell /></TableRow></TableHeader>
          <TableBody>{resource.data.items.map((batch) => <TableRow key={batch.id}>
            <TableCell><code>{batch.id}</code></TableCell><TableCell>{batchLabels[batch.status]}</TableCell>
            <TableCell>{batch.succeededItems} 成功 / {batch.failedItems} 失败 / {batch.pendingItems} 待处理</TableCell>
            <TableCell>{formatTimestamp(batch.createdAt)}</TableCell><TableCell><Button appearance="subtle" size="small" onClick={() => void openBatch(batch)}>查看结果</Button></TableCell>
          </TableRow>)}</TableBody>
        </Table></div>
      ) : null}
    </section>
  );
}
