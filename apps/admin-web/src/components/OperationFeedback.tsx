import {
  Button,
  MessageBar,
  MessageBarBody,
} from "@fluentui/react-components";
import { ArrowClockwise24Regular } from "@fluentui/react-icons";

import type { ApiError } from "../api/client";

export function OperationFeedback({
  notice,
  error,
  onRetry,
}: {
  notice?: string;
  error?: ApiError;
  onRetry?: () => void;
}) {
  if (!notice && !error) return null;
  if (error) {
    const conflict = error.status === 409;
    return (
      <MessageBar intent="error">
        <MessageBarBody>
          <strong>{conflict ? "数据状态已变更" : "操作失败"}</strong>
          <div>
            {conflict
              ? `${error.message} 请刷新最新数据后重试。`
              : error.message}
          </div>
          {(error.code || error.requestId) && (
            <div className="error-reference">
              <span>错误代码：{error.code}</span>
              {error.requestId && <span>请求编号：{error.requestId}</span>}
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
    );
  }
  return (
    <MessageBar intent="success">
      <MessageBarBody>{notice}</MessageBarBody>
    </MessageBar>
  );
}
