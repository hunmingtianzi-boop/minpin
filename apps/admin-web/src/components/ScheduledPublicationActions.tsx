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
} from "@fluentui/react-components";
import { CalendarClock24Regular, Dismiss24Regular } from "@fluentui/react-icons";
import { useState } from "react";

import {
  scheduledPublicationsApi,
  type ScheduledPublication,
  type ScheduledPublicationTargetType,
} from "../api/scheduledPublicationsApi";
import { ApiError } from "../api/client";
import { ActionConfirmDialog } from "./ActionConfirmDialog";
import { OperationFeedback } from "./OperationFeedback";
import { StatusBadge } from "./StatusBadge";
import { formatTimestamp } from "../utils/format";

function initialScheduleTime(): string {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function asApiError(caught: unknown, fallback: string): ApiError {
  return caught instanceof ApiError
    ? caught
    : new ApiError(fallback, { code: "UNKNOWN_ERROR" });
}

export function ScheduledPublicationStatus({
  publication,
}: {
  publication?: ScheduledPublication;
}) {
  if (!publication) return null;
  return (
    <div className="scheduled-publication-status">
      <StatusBadge status={publication.status} />
      <span>计划发布：{formatTimestamp(publication.scheduledAt)}</span>
    </div>
  );
}

export function ScheduledPublicationActions({
  targetType,
  targetId,
  targetVersion,
  targetLabel,
  knowledgeVersionId,
  current,
  disabled,
  onChanged,
}: {
  targetType: ScheduledPublicationTargetType;
  targetId: string;
  targetVersion: number;
  targetLabel: string;
  knowledgeVersionId?: string;
  current?: ScheduledPublication;
  disabled?: boolean;
  onChanged: (notice: string) => void;
}) {
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [scheduledFor, setScheduledFor] = useState(initialScheduleTime);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError>();
  const isActive =
    current?.status === "pending" ||
    current?.status === "processing" ||
    current?.status === "failed";

  const schedule = async () => {
    if (pending) return;
    const instant = new Date(scheduledFor);
    if (!scheduledFor || Number.isNaN(instant.getTime()) || instant.getTime() <= Date.now()) {
      setError(new ApiError("请选择当前时间之后的发布时间。", { code: "INVALID_SCHEDULE_TIME" }));
      return;
    }
    setPending(true);
    setError(undefined);
    try {
      await scheduledPublicationsApi.create({
        targetType,
        targetId,
        scheduledFor: instant.toISOString(),
        version: targetVersion,
        knowledgeVersionId,
      });
      setScheduleOpen(false);
      onChanged(`已为“${targetLabel}”设置定时发布。`);
    } catch (caught) {
      setError(asApiError(caught, "设置定时发布时发生未知错误。"));
    } finally {
      setPending(false);
    }
  };

  const cancel = async () => {
    if (!current || pending) return;
    setPending(true);
    setError(undefined);
    try {
      await scheduledPublicationsApi.cancel(current.id, current.version);
      setCancelOpen(false);
      onChanged(`已取消“${targetLabel}”的定时发布。`);
    } catch (caught) {
      setError(asApiError(caught, "取消定时发布时发生未知错误。"));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      {isActive ? (
        <Button
          appearance="subtle"
          size="small"
          icon={<Dismiss24Regular />}
          disabled={disabled || current.status === "processing"}
          onClick={() => {
            setError(undefined);
            setCancelOpen(true);
          }}
        >
          取消定时
        </Button>
      ) : (
        <Button
          appearance="subtle"
          size="small"
          icon={<CalendarClock24Regular />}
          disabled={disabled}
          onClick={() => {
            setScheduledFor(initialScheduleTime());
            setError(undefined);
            setScheduleOpen(true);
          }}
        >
          定时发布
        </Button>
      )}

      <Dialog
        open={scheduleOpen}
        onOpenChange={(_, data) => {
          if (!data.open && !pending) setScheduleOpen(false);
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>设置定时发布</DialogTitle>
            <DialogContent className="scheduled-publication-dialog">
              <p>服务器将在指定时间发布“{targetLabel}”，执行前可以取消。</p>
              <Field label="发布时间" required>
                <Input
                  type="datetime-local"
                  value={scheduledFor}
                  disabled={pending}
                  onChange={(_, data) => setScheduledFor(data.value)}
                />
              </Field>
              <OperationFeedback error={error} />
            </DialogContent>
            <DialogActions>
              <Button disabled={pending} onClick={() => setScheduleOpen(false)}>取消</Button>
              <Button appearance="primary" disabled={pending} onClick={() => void schedule()}>
                {pending ? "正在设置" : "确认定时发布"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <ActionConfirmDialog
        open={cancelOpen}
        title="取消定时发布"
        description={`确认取消“${targetLabel}”的定时发布吗？取消后内容仍保留当前状态。`}
        confirmLabel="确认取消定时"
        pendingLabel="正在取消"
        pending={pending}
        error={error}
        destructive
        onCancel={() => {
          setCancelOpen(false);
          setError(undefined);
        }}
        onConfirm={() => void cancel()}
      />
    </>
  );
}
