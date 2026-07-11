import {
  Badge,
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
  Delete24Regular,
  Edit24Regular,
  ToggleLeft24Regular,
  ToggleRight24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { ForbiddenTopic } from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { ForbiddenTopicEditor } from "../components/ForbiddenTopicEditor";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

type TopicAction = {
  type: "activate" | "deactivate" | "delete";
  target: ForbiddenTopic;
};

const actionLabels = {
  refuse: "拒绝回答",
  handoff: "建议转人工",
  safe_template: "安全模板",
} as const;

export function ForbiddenTopicsPage() {
  const resource = useResource(() => adminApi.listForbiddenTopics());
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ForbiddenTopic>();
  const [action, setAction] = useState<TopicAction>();
  const [mutating, setMutating] = useState(false);
  const [actionError, setActionError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();

  const openCreate = () => {
    setEditing(undefined);
    setEditorOpen(true);
    setNotice(undefined);
  };

  const saved = () => {
    setEditorOpen(false);
    setNotice("禁答主题已由服务端确认保存。状态切换需使用列表中的启停操作。");
    resource.reload();
  };

  const requestAction = (type: TopicAction["type"], target: ForbiddenTopic) => {
    setAction({ type, target });
    setActionError(undefined);
    setNotice(undefined);
  };

  const executeAction = async () => {
    if (!action || mutating) return;
    setMutating(true);
    setActionError(undefined);
    try {
      if (action.type === "delete") {
        await adminApi.deleteForbiddenTopic(action.target.id, action.target.version);
        setNotice("禁答主题已由服务端确认删除。");
      } else {
        const active = action.type === "activate";
        await adminApi.setForbiddenTopicActive(
          action.target.id,
          action.target.version,
          active,
        );
        setNotice(active ? "禁答主题已启用。" : "禁答主题已停用。");
      }
      setAction(undefined);
      resource.reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("执行禁答主题操作时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setMutating(false);
    }
  };

  const deleting = action?.type === "delete";
  const deactivating = action?.type === "deactivate";
  const actionTitle = deleting
    ? "确认删除禁答主题"
    : deactivating
      ? "确认停用禁答主题"
      : "确认启用禁答主题";
  const actionDescription = deleting
    ? "删除后，该规则不会再参与安全策略匹配，且无法从列表恢复。"
    : deactivating
      ? "停用后，该规则会立即退出安全策略匹配。"
      : "启用后，该规则会立即进入安全策略匹配。";

  return (
    <main className="page-stack">
      <PageHeader
        title="禁答主题"
        description="维护 AI 不应直接回答的主题和安全回复。每次修改与启停都使用服务端版本校验。"
        actions={
          resource.status === "permission" ? undefined : (
            <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
              新建禁答主题
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
            title={resource.status === "empty" ? "尚未配置禁答主题" : undefined}
            description={
              resource.status === "empty"
                ? "添加第一条规则后，可在这里编辑、启停或删除。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
                新建禁答主题
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className="table-scroll">
            <Table aria-label="禁答主题列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>主题与匹配词</TableHeaderCell>
                  <TableHeaderCell className="topic-action-column">处理动作</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((topic) => (
                  <TableRow key={topic.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{topic.topic || "未命名主题"}</strong>
                        <span>
                          {topic.matchTerms.length
                            ? topic.matchTerms.slice(0, 4).join("、")
                            : "未配置匹配词"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="topic-action-column">
                      {actionLabels[topic.action]}
                    </TableCell>
                    <TableCell className="status-column">
                      <Badge appearance="tint" color={topic.isActive ? "success" : "subtle"}>
                        {topic.isActive ? "已启用" : "已停用"}
                      </Badge>
                    </TableCell>
                    <TableCell className="updated-column">
                      {formatTimestamp(topic.updatedAt)}
                    </TableCell>
                    <TableCell className="catalog-actions-column">
                      <div className="row-actions catalog-row-actions">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Edit24Regular />}
                          onClick={() => {
                            setEditing(topic);
                            setEditorOpen(true);
                            setNotice(undefined);
                          }}
                        >
                          编辑
                        </Button>
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={
                            topic.isActive ? (
                              <ToggleLeft24Regular />
                            ) : (
                              <ToggleRight24Regular />
                            )
                          }
                          onClick={() =>
                            requestAction(topic.isActive ? "deactivate" : "activate", topic)
                          }
                        >
                          {topic.isActive ? "停用" : "启用"}
                        </Button>
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Delete24Regular />}
                          onClick={() => requestAction("delete", topic)}
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

      <ForbiddenTopicEditor
        open={editorOpen}
        item={editing}
        onClose={() => setEditorOpen(false)}
        onSaved={saved}
      />

      <ActionConfirmDialog
        open={Boolean(action)}
        title={actionTitle}
        description={actionDescription}
        confirmLabel={deleting ? "确认删除" : deactivating ? "确认停用" : "确认启用"}
        pendingLabel="正在处理"
        pending={mutating}
        error={actionError}
        destructive={deleting || deactivating}
        detail={
          action ? (
            <div className="publish-target">
              <strong>{action.target.topic || "未命名主题"}</strong>
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
