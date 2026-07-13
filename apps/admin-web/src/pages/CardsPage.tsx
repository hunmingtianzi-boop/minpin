import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Field,
  Input,
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
  Copy24Regular,
  Edit24Regular,
  QrCode24Regular,
  Send24Regular,
  Share24Regular,
  Settings24Regular,
  ToggleRight24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { ManagedCard } from "../api/types";
import { ActionConfirmDialog } from "../components/ActionConfirmDialog";
import { CardEditor } from "../components/CardEditor";
import { CardContentOverridesDialog } from "../components/CardContentOverridesDialog";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

type CardAction = {
  type: "publish" | "deactivate";
  target: ManagedCard;
};

export async function copyManagedCardText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("copy failed");
}

export function CardsPage() {
  const resource = useResource(() => adminApi.listManagedCards());
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ManagedCard>();
  const [shareTarget, setShareTarget] = useState<ManagedCard>();
  const [overrideTarget, setOverrideTarget] = useState<ManagedCard>();
  const [copyNotice, setCopyNotice] = useState<string>();
  const [copyError, setCopyError] = useState<string>();
  const [action, setAction] = useState<CardAction>();
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
    setNotice(editing ? "名片已由服务端确认保存。" : "名片已创建，安全链接已由服务端生成。");
    resource.reload();
  };

  const requestAction = (type: CardAction["type"], target: ManagedCard) => {
    setAction({ type, target });
    setActionError(undefined);
    setNotice(undefined);
  };

  const executeAction = async () => {
    if (!action || mutating) return;
    setMutating(true);
    setActionError(undefined);
    try {
      if (action.type === "publish") {
        await adminApi.publishManagedCard(action.target.id, action.target.version);
        setNotice("名片已由服务端确认发布。公开链接现在可访问。");
      } else {
        await adminApi.deactivateManagedCard(action.target.id, action.target.version);
        setNotice("名片已停用，公开访问会立即失效。");
      }
      setAction(undefined);
      resource.reload();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError
          ? caught
          : new ApiError("执行名片操作时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setMutating(false);
    }
  };

  const copy = async (value: string, label: string) => {
    setCopyNotice(undefined);
    setCopyError(undefined);
    try {
      await copyManagedCardText(value);
      setCopyNotice(`${label}已复制。`);
    } catch {
      setCopyError("浏览器未允许自动复制，请手动选择文本。");
    }
  };

  const deactivating = action?.type === "deactivate";

  return (
    <main className="page-stack">
      <PageHeader
        title="名片管理"
        description="创建和维护多张名片。安全链接、所有者范围和公开状态均由服务端确认。"
        actions={
          resource.status === "permission" ? undefined : (
            <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
              新建名片
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
            title={resource.status === "empty" ? "尚未创建名片" : undefined}
            description={
              resource.status === "empty"
                ? "创建第一张名片后，可在这里发布、停用和复制分享链接。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={openCreate}>
                新建名片
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className="table-scroll">
            <Table aria-label="名片列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>名片与所有者</TableHeaderCell>
                  <TableHeaderCell className="status-column">状态</TableHeaderCell>
                  <TableHeaderCell className="updated-column">更新时间</TableHeaderCell>
                  <TableHeaderCell className="catalog-actions-column">操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((card) => (
                  <TableRow key={card.id}>
                    <TableCell>
                      <div className="entity-title-cell">
                        <strong>{card.displayName || "未命名名片"}</strong>
                        <span>{card.title || "职务未填写"}</span>
                        <code>{card.slug}</code>
                      </div>
                    </TableCell>
                    <TableCell className="status-column">
                      <StatusBadge status={card.status} />
                    </TableCell>
                    <TableCell className="updated-column">
                      {formatTimestamp(card.updatedAt)}
                    </TableCell>
                    <TableCell className="catalog-actions-column">
                      <div className="row-actions catalog-row-actions">
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Edit24Regular />}
                          onClick={() => {
                            setEditing(card);
                            setEditorOpen(true);
                            setNotice(undefined);
                          }}
                        >
                          编辑
                        </Button>
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Share24Regular />}
                          onClick={() => {
                            setShareTarget(card);
                            setCopyNotice(undefined);
                            setCopyError(undefined);
                          }}
                        >
                          分享
                        </Button>
                        <Button
                          appearance="subtle"
                          size="small"
                          icon={<Settings24Regular />}
                          onClick={() => setOverrideTarget(card)}
                        >
                          内容覆盖
                        </Button>
                        {card.status !== "published" ? (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<Send24Regular />}
                            onClick={() => requestAction("publish", card)}
                          >
                            发布
                          </Button>
                        ) : (
                          <Button
                            appearance="subtle"
                            size="small"
                            icon={<ToggleRight24Regular />}
                            onClick={() => requestAction("deactivate", card)}
                          >
                            停用
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      <CardEditor
        open={editorOpen}
        item={editing}
        onClose={() => setEditorOpen(false)}
        onSaved={saved}
      />
      <CardContentOverridesDialog
        card={overrideTarget}
        open={Boolean(overrideTarget)}
        onClose={() => setOverrideTarget(undefined)}
      />

      <ActionConfirmDialog
        open={Boolean(action)}
        title={deactivating ? "确认停用名片" : "确认发布名片"}
        description={
          deactivating
            ? "停用后，公开链接会立即失效。后台配置和历史数据仍会保留。"
            : "发布后，名片公开链接会立即生效，请确认展示内容和政策版本已复核。"
        }
        confirmLabel={deactivating ? "确认停用" : "确认发布"}
        pendingLabel={deactivating ? "正在停用" : "正在发布"}
        pending={mutating}
        error={actionError}
        destructive={deactivating}
        detail={
          action ? (
            <div className="publish-target">
              <strong>{action.target.displayName || "未命名名片"}</strong>
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

      <Dialog
        open={Boolean(shareTarget)}
        onOpenChange={(_, data) => {
          if (!data.open) setShareTarget(undefined);
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>分享名片</DialogTitle>
            <DialogContent className="share-dialog-content">
              <p>分享链接和二维码内容均由服务端返回，不在浏览器中拼接。</p>
              {shareTarget && (
                <div className="share-fields">
                  <Field label="分享链接">
                    <div className="copy-field">
                      <Input value={shareTarget.shareUrl} readOnly />
                      <Button
                        icon={<Copy24Regular />}
                        aria-label="复制分享链接"
                        onClick={() => void copy(shareTarget.shareUrl, "分享链接")}
                      />
                    </div>
                  </Field>
                  <Field
                    label="二维码内容"
                    hint="将以下 URL 交给受信任的二维码工具编码。"
                  >
                    <div className="copy-field">
                      <Input value={shareTarget.qrUrl} readOnly />
                      <Button
                        icon={<QrCode24Regular />}
                        aria-label="复制二维码内容"
                        onClick={() => void copy(shareTarget.qrUrl, "二维码内容")}
                      />
                    </div>
                  </Field>
                  <a
                    className="share-open-link"
                    href={shareTarget.shareUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开公开名片
                  </a>
                </div>
              )}
              {copyNotice && (
                <MessageBar intent="success">
                  <MessageBarBody>{copyNotice}</MessageBarBody>
                </MessageBar>
              )}
              {copyError && (
                <MessageBar intent="error">
                  <MessageBarBody>{copyError}</MessageBarBody>
                </MessageBar>
              )}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setShareTarget(undefined)}>
                关闭
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </main>
  );
}
