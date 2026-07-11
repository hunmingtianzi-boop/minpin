import {
  Button,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
} from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  ErrorCircle24Regular,
  LockClosed24Regular,
} from "@fluentui/react-icons";
import type { ReactNode } from "react";

import type { ResourceStatus } from "../hooks/useResource";

type ResourceStateProps = {
  status: Exclude<ResourceStatus, "ready">;
  title?: string;
  description?: string;
  errorCode?: string;
  requestId?: string;
  onRetry?: () => void;
  emptyAction?: ReactNode;
  compact?: boolean;
};

export function ResourceState({
  status,
  title,
  description,
  errorCode,
  requestId,
  onRetry,
  emptyAction,
  compact = false,
}: ResourceStateProps) {
  if (status === "loading") {
    return (
      <div
        className={compact ? "resource-loading compact" : "resource-loading"}
        role="status"
        aria-label="正在加载"
      >
        <Skeleton>
          <SkeletonItem size={16} />
          <SkeletonItem size={32} />
          {!compact && <SkeletonItem size={16} />}
        </Skeleton>
      </div>
    );
  }

  if (status === "permission") {
    return (
      <div className={compact ? "resource-state compact" : "resource-state"}>
        <LockClosed24Regular aria-hidden />
        <div>
          <h3>{title ?? "没有访问权限"}</h3>
          <p>{description ?? "请联系企业管理员为当前账号分配所需权限。"}</p>
        </div>
      </div>
    );
  }

  if (status === "empty") {
    return (
      <div className={compact ? "resource-state compact" : "resource-state"}>
        <Add24Regular aria-hidden />
        <div>
          <h3>{title ?? "暂无数据"}</h3>
          <p>{description ?? "完成首次配置后，相关内容会显示在这里。"}</p>
          {emptyAction && <div className="resource-state-action">{emptyAction}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className={compact ? "resource-error compact" : "resource-error"}>
      <MessageBar intent="error" icon={<ErrorCircle24Regular />}>
        <MessageBarBody>
          <strong>{title ?? "加载失败"}</strong>
          <div>{description ?? "管理服务暂未返回可用数据。"}</div>
          {(errorCode || requestId) && (
            <div className="error-reference">
              {errorCode && <span>错误代码：{errorCode}</span>}
              {requestId && <span>请求编号：{requestId}</span>}
            </div>
          )}
          {onRetry && (
            <Button
              appearance="subtle"
              size="small"
              icon={<ArrowClockwise24Regular />}
              onClick={onRetry}
            >
              重试
            </Button>
          )}
        </MessageBarBody>
      </MessageBar>
    </div>
  );
}
