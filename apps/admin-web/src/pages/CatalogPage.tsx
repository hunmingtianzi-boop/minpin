import {
  Button,
  MessageBar,
  MessageBarBody,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  Add24Regular,
  Archive24Regular,
  Delete24Regular,
  Edit24Regular,
  Send24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CaseStudy, Product } from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { CaseStudyEditor, ProductEditor } from "../components/CatalogEditor";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

type CatalogKind = "product" | "case";
type CatalogRecord = Product | CaseStudy;
type CatalogAction = "publish" | "archive" | "delete";

type PendingAction = {
  type: CatalogAction;
  target: CatalogRecord;
};

const contentConfig = {
  product: {
    pageTitle: "产品管理",
    description: "维护公开产品、服务边界和排序。发布与归档均受版本冲突保护。",
    createLabel: "新建产品",
    emptyTitle: "尚未创建产品",
    emptyDescription: "创建第一项产品后，可在这里编辑、发布或归档。",
    tableLabel: "产品列表",
  },
  case: {
    pageTitle: "案例管理",
    description: "维护项目背景、解决方案和成果。只有公开且已发布的案例会对访客展示。",
    createLabel: "新建案例",
    emptyTitle: "尚未创建案例",
    emptyDescription: "创建第一项案例后，可在这里编辑、发布或归档。",
    tableLabel: "案例列表",
  },
} as const;

function recordTitle(record: CatalogRecord): string {
  return "name" in record ? record.name : record.title;
}

function recordContext(record: CatalogRecord): string {
  if ("name" in record) {
    return [record.category, record.summary].filter(Boolean).join(" | ");
  }
  return [record.industry, record.clientDisplayName].filter(Boolean).join(" | ");
}

function actionCopy(action?: PendingAction) {
  if (!action) {
    return {
      title: "确认操作",
      description: "请确认是否继续。",
      confirmLabel: "确认",
      pendingLabel: "正在处理",
      destructive: false,
    };
  }
  const label = "name" in action.target ? "产品" : "案例";
  if (action.type === "publish") {
    return {
      title: `确认发布${label}`,
      description: `发布后，符合公开范围的${label}会立即进入访客可见状态。`,
      confirmLabel: "确认发布",
      pendingLabel: "正在发布",
      destructive: false,
    };
  }
  if (action.type === "archive") {
    return {
      title: `确认归档${label}`,
      description: `归档后，该${label}会立即从公开页面消失，但仍保留历史记录。`,
      confirmLabel: "确认归档",
      pendingLabel: "正在归档",
      destructive: true,
    };
  }
  return {
    title: `确认删除${label}`,
    description: `删除后，该${label}会被软删除并从管理列表及公开页面消失。`,
    confirmLabel: "确认删除",
    pendingLabel: "正在删除",
    destructive: true,
  };
}

export function CatalogPage({ kind }: { kind: CatalogKind }) {
  const config = contentConfig[kind];
  const resource = useResource<CatalogRecord[]>(() =>
    kind === "product" ? adminApi.listProducts() : adminApi.listCaseStudies(),
  );
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CatalogRecord>();
  const [action, setAction] = useState<PendingAction>();
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const openCreate = () => {
    setEditing(undefined);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const openEdit = (record: CatalogRecord) => {
    setEditing(record);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const saved = () => {
    setEditorOpen(false);
    setNotice(`${kind === "product" ? "产品" : "案例"}已由服务端确认保存。`);
    resource.reload();
  };

  const requestAction = (type: CatalogAction, target: CatalogRecord) => {
    setAction({ type, target });
    setActionError(undefined);
    setNotice(undefined);
  };

  const executeAction = async () => {
    if (!action || mutating) return;
    setMutating(true);
    setActionError(undefined);
    try {
      const { target, type } = action;
      if (kind === "product") {
        if (type === "publish") {
          await adminApi.publishProduct(target.id, target.version);
        } else if (type === "archive") {
          await adminApi.archiveProduct(target.id, target.version);
        } else {
          await adminApi.deleteProduct(target.id, target.version);
        }
      } else if (type === "publish") {
        await adminApi.publishCaseStudy(target.id, target.version);
      } else if (type === "archive") {
        await adminApi.archiveCaseStudy(target.id, target.version);
      } else {
        await adminApi.deleteCaseStudy(target.id, target.version);
      }

      const label = kind === "product" ? "产品" : "案例";
      const verb = type === "publish" ? "发布" : type === "archive" ? "归档" : "删除";
      setNotice(`${label}已由服务端确认${verb}。`);
      setAction(undefined);
      resource.reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("执行目录操作时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setMutating(false);
    }
  };

  const copy = actionCopy(action);

  return (
    <main className="page-stack">
      <PageHeader
        title={config.pageTitle}
        description={config.description}
        actions={
          resource.status === "permission" ? undefined : (
            <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
              {config.createLabel}
            </Button>
          )
        }
      />

      {notice && (
        <MessageBar intent="success">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}

      <section className="content-panel catalog-panel">
        {resource.status !== "ready" && (
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? config.emptyTitle : undefined}
            description={
              resource.status === "empty"
                ? config.emptyDescription
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
                {config.createLabel}
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className="table-scroll">
            <Table aria-label={config.tableLabel} size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>名称与范围</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((record) => (
                  <TableRow key={record.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{recordTitle(record) || "未命名内容"}</strong>
                        <span>{recordContext(record) || `链接标识：${record.slug}`}</span>
                      </div>
                    </TableCell>
                    <TableCell className="status-column">
                      <StatusBadge status={record.status} />
                    </TableCell>
                    <TableCell className="updated-column">
                      {formatTimestamp(record.updatedAt)}
                    </TableCell>
                    <TableCell className="catalog-actions-column">
                      <div className="row-actions catalog-row-actions">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Edit24Regular />}
                          onClick={() => openEdit(record)}
                        >
                          编辑
                        </Button>
                        {record.status !== "published" && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Send24Regular />}
                            onClick={() => requestAction("publish", record)}
                          >
                            发布
                          </Button>
                        )}
                        {record.status !== "archived" && (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Archive24Regular />}
                            onClick={() => requestAction("archive", record)}
                          >
                            归档
                          </Button>
                        )}
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Delete24Regular />}
                          onClick={() => requestAction("delete", record)}
                        >
                          删除
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {kind === "product" ? (
        <ProductEditor
          open={editorOpen}
          item={editing && "name" in editing ? editing : undefined}
          onClose={() => setEditorOpen(false)}
          onSaved={saved}
        />
      ) : (
        <CaseStudyEditor
          open={editorOpen}
          item={editing && "title" in editing ? editing : undefined}
          onClose={() => setEditorOpen(false)}
          onSaved={saved}
        />
      )}

      <ActionConfirmDialog
        open={Boolean(action)}
        title={copy.title}
        description={copy.description}
        confirmLabel={copy.confirmLabel}
        pendingLabel={copy.pendingLabel}
        pending={mutating}
        error={actionError}
        destructive={copy.destructive}
        detail={
          action ? (
            <div className="publish-target">
              <strong>{recordTitle(action.target) || "未命名内容"}</strong>
              <span>当前版本：{action.target.version}</span>
            </div>
          ) : undefined
        }
        onCancel={() => {
          setAction(undefined);
          setActionError(undefined);
        }}
        onConfirm={() => void executeAction()}
        onReload={() => {
          setAction(undefined);
          setActionError(undefined);
          resource.reload();
        }}
      />
    </main>
  );
}

export function ProductsPage() {
  return <CatalogPage kind="product" />;
}

export function CaseStudiesPage() {
  return <CatalogPage kind="case" />;
}
