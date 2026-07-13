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
  Spinner,
} from "@fluentui/react-components";
import { Globe24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";

import {
  enterpriseContentApi,
  type EnterpriseDistribution,
  type EnterpriseResourceType,
} from "../api/enterpriseContentApi";
import { ApiError } from "../api/client";

function errorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : "内容分发策略暂时无法读取。";
}

export function ContentDistributionControl({
  resourceType,
  resourceId,
  resourceLabel,
  sourceStatus,
}: {
  resourceType: EnterpriseResourceType;
  resourceId: string;
  resourceLabel: string;
  sourceStatus: string;
}) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<
    | { status: "idle" | "loading" }
    | { status: "ready"; data: EnterpriseDistribution }
    | { status: "error" | "permission"; error: unknown }
  >({ status: "idle" });
  const [saving, setSaving] = useState(false);

  const reload = () => {
    setState({ status: "loading" });
    void enterpriseContentApi.getDistribution(resourceType, resourceId).then(
      (data) => setState({ status: "ready", data }),
      (error: unknown) =>
        setState({
          status: error instanceof ApiError && error.status === 403 ? "permission" : "error",
          error,
        }),
    );
  };

  useEffect(() => {
    if (open && state.status === "idle") reload();
    // Deliberately load only when this row is opened; catalog lists can contain many records.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const setVisibility = (isDefaultVisible: boolean) => {
    if (state.status !== "ready" || saving) return;
    setSaving(true);
    void enterpriseContentApi
      .setDistribution(resourceType, resourceId, state.data.version, isDefaultVisible)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        setState({
          status: error instanceof ApiError && error.status === 403 ? "permission" : "error",
          error,
        });
      })
      .finally(() => setSaving(false));
  };

  const sourcePublished = sourceStatus === "published";
  const distribution = state.status === "ready" ? state.data : undefined;
  const visible = distribution?.isDefaultVisible ?? false;

  return (
    <>
      <Button
        appearance="subtle"
        size="small"
        icon={<Globe24Regular />}
        onClick={() => setOpen(true)}
      >
        分发策略
      </Button>
      <Dialog open={open} onOpenChange={(_, data) => setOpen(data.open)}>
        <DialogSurface aria-describedby="distribution-description">
          <DialogBody>
            <DialogTitle>企业统一内容分发</DialogTitle>
            <DialogContent>
              <p id="distribution-description">
                设置“{resourceLabel || "未命名内容"}”是否默认分发到员工名片。员工仍可在名片级隐藏或调整展示文案。
              </p>
              {state.status === "loading" || state.status === "idle" ? (
                <div className="inline-loading"><Spinner size="tiny" />正在读取服务端策略…</div>
              ) : state.status === "permission" ? (
                <MessageBar intent="warning"><MessageBarBody>当前账号无权管理企业统一内容。</MessageBarBody></MessageBar>
              ) : state.status === "error" ? (
                <MessageBar intent="error">
                  <MessageBarBody>
                    {errorMessage(state.error)} <Button appearance="subtle" size="small" onClick={reload}>重试</Button>
                  </MessageBarBody>
                </MessageBar>
              ) : distribution ? (
                <div className="distribution-summary">
                  <p>
                    有效公开状态：<strong>{sourcePublished && visible ? "默认向员工名片公开" : sourcePublished ? "默认不公开" : "源内容尚未发布"}</strong>
                  </p>
                  {!sourcePublished && <p className="form-note">请先发布源内容；未发布、归档或删除的内容不会出现在公开名片。</p>}
                  <p className="form-note">策略版本：{distribution.version}。保存采用服务端版本保护，其他管理员更新后请刷新重试。</p>
                  <div className="distribution-options" role="group" aria-label="默认分发状态">
                    <Button
                      appearance={distribution.isDefaultVisible ? "primary" : "secondary"}
                      disabled={saving || distribution.isDefaultVisible}
                      onClick={() => setVisibility(true)}
                    >
                      默认公开
                    </Button>
                    <Button
                      appearance={!distribution.isDefaultVisible ? "primary" : "secondary"}
                      disabled={saving || !distribution.isDefaultVisible}
                      onClick={() => setVisibility(false)}
                    >
                      默认隐藏
                    </Button>
                  </div>
                </div>
              ) : null}
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" onClick={() => setOpen(false)}>关闭</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </>
  );
}
