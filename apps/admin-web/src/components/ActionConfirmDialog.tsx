import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  MessageBar,
  MessageBarBody,
} from "@fluentui/react-components";
import type { ReactNode } from "react";

import type { ApiError } from "../api/client";

type ActionConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  pendingLabel: string;
  pending: boolean;
  error?: ApiError;
  detail?: ReactNode;
  destructive?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  onReload?: () => void;
};

export function ActionConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  pendingLabel,
  pending,
  error,
  detail,
  destructive = false,
  onCancel,
  onConfirm,
  onReload,
}: ActionConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(_, data) => {
        if (!data.open && !pending) onCancel();
      }}
    >
      <DialogSurface>
        <DialogBody>
          <DialogTitle>{title}</DialogTitle>
          <DialogContent className="action-dialog-content">
            <p>{description}</p>
            {detail}
            {error && (
              <MessageBar intent="error">
                <MessageBarBody>
                  <strong>操作失败</strong>
                  <div>{error.message}</div>
                  <div className="error-reference">
                    <span>错误代码：{error.code}</span>
                    {error.requestId && <span>请求编号：{error.requestId}</span>}
                  </div>
                  {error.code === "VERSION_CONFLICT" && onReload && (
                    <Button appearance="subtle" size="small" onClick={onReload}>
                      刷新最新数据
                    </Button>
                  )}
                </MessageBarBody>
              </MessageBar>
            )}
          </DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={onCancel} disabled={pending}>
              取消
            </Button>
            <Button
              appearance="primary"
              className={destructive ? "danger-button" : undefined}
              onClick={onConfirm}
              disabled={pending}
            >
              {pending ? pendingLabel : confirmLabel}
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
