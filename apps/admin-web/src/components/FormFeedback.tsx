import { MessageBar, MessageBarBody } from "@fluentui/react-components";

import type { ApiError } from "../api/client";

type FormFeedbackProps = {
  success?: string;
  error?: ApiError;
};

export function FormFeedback({ success, error }: FormFeedbackProps) {
  if (error) {
    return (
      <MessageBar intent="error">
        <MessageBarBody>
          <strong>保存失败</strong>
          <div>{error.message}</div>
          <div className="error-reference">
            <span>错误代码：{error.code}</span>
            {error.requestId && <span>请求编号：{error.requestId}</span>}
          </div>
        </MessageBarBody>
      </MessageBar>
    );
  }
  if (success) {
    return (
      <MessageBar intent="success">
        <MessageBarBody>{success}</MessageBarBody>
      </MessageBar>
    );
  }
  return null;
}
