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
  Spinner,
  Textarea,
} from "@fluentui/react-components";
import { ArrowCounterclockwise24Regular, Delete24Regular, Edit24Regular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import {
  enterpriseContentApi,
  type CardContentOverride,
  type CardContentOverrideRevision,
  type ContentOverrideMode,
  type CustomContentDisplay,
  type EnterpriseResourceType,
} from "../api/enterpriseContentApi";
import type { CaseStudy, ManagedCard, Product } from "../api/types";

type ResourceItem = {
  id: string;
  resourceType: Extract<EnterpriseResourceType, "product" | "case_study">;
  title: string;
  summary: string;
  sourceStatus: string;
};

type LoadState =
  | { status: "idle" | "loading" }
  | { status: "ready"; resources: ResourceItem[]; overrides: CardContentOverride[] }
  | { status: "permission" | "error"; error: unknown };

function asResource(product: Product): ResourceItem {
  return {
    id: product.id,
    resourceType: "product",
    title: product.name || "未命名产品",
    summary: product.summary,
    sourceStatus: product.status,
  };
}

function asCaseResource(caseStudy: CaseStudy): ResourceItem {
  return {
    id: caseStudy.id,
    resourceType: "case_study",
    title: caseStudy.title || "未命名案例",
    summary: caseStudy.background,
    sourceStatus: caseStudy.status,
  };
}

function friendlyError(error: unknown) {
  return error instanceof ApiError ? error.message : "名片内容覆盖暂时无法读取。";
}

function displayFor(resource: ResourceItem, override?: CardContentOverride): CustomContentDisplay {
  return {
    title: override?.customDisplay.title ?? resource.title,
    summary: override?.customDisplay.summary ?? resource.summary,
    imageUrl: override?.customDisplay.imageUrl,
    sortOrder: override?.customDisplay.sortOrder,
  };
}

function resourceKey(resourceType: EnterpriseResourceType, resourceId: string) {
  return `${resourceType}:${resourceId}`;
}

export function CardContentOverridesDialog({ card, open, onClose }: {
  card: ManagedCard | undefined;
  open: boolean;
  onClose: () => void;
}) {
  const [state, setState] = useState<LoadState>({ status: "idle" });
  const [editing, setEditing] = useState<ResourceItem>();
  const [custom, setCustom] = useState<CustomContentDisplay>({});
  const [saving, setSaving] = useState(false);
  const [historyTarget, setHistoryTarget] = useState<ResourceItem>();
  const [revisions, setRevisions] = useState<CardContentOverrideRevision[]>();
  const [historyError, setHistoryError] = useState<unknown>();

  const reload = () => {
    if (!card) return;
    setState({ status: "loading" });
    void Promise.all([
      adminApi.listProducts(),
      adminApi.listCaseStudies(),
      enterpriseContentApi.listOverrides(card.id),
    ]).then(
      ([products, cases, overrides]) => {
        setState({
          status: "ready",
          resources: [...products.map(asResource), ...cases.map(asCaseResource)],
          overrides,
        });
      },
      (error: unknown) => setState({
        status: error instanceof ApiError && error.status === 403 ? "permission" : "error",
        error,
      }),
    );
  };

  useEffect(() => {
    if (open && state.status === "idle") reload();
    if (!open) {
      setEditing(undefined);
      setHistoryTarget(undefined);
      setRevisions(undefined);
      setHistoryError(undefined);
    }
    // Each dialog session reads once; successful mutations replace local state through reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, card?.id]);

  const overrideMap = useMemo(() => {
    if (state.status !== "ready") return new Map<string, CardContentOverride>();
    return new Map(state.overrides.map((item) => [resourceKey(item.resourceType, item.resourceId), item]));
  }, [state]);
  const readyState = state.status === "ready" ? state : undefined;

  const mutate = (
    resource: ResourceItem,
    mode: ContentOverrideMode,
    content?: CustomContentDisplay,
  ) => {
    if (!card || saving) return;
    const current = overrideMap.get(resourceKey(resource.resourceType, resource.id));
    setSaving(true);
    void enterpriseContentApi
      .setOverride(card.id, resource.resourceType, resource.id, current?.version ?? 0, mode, content)
      .then(() => {
        setEditing(undefined);
        reload();
      })
      .catch((error: unknown) => setState({ status: "error", error }))
      .finally(() => setSaving(false));
  };

  const removeOverride = (resource: ResourceItem) => {
    if (!card || saving) return;
    const current = overrideMap.get(resourceKey(resource.resourceType, resource.id));
    if (!current) return;
    setSaving(true);
    void enterpriseContentApi
      .deleteOverride(card.id, resource.resourceType, resource.id, current.version)
      .then(reload)
      .catch((error: unknown) => setState({ status: "error", error }))
      .finally(() => setSaving(false));
  };

  const openHistory = (resource: ResourceItem) => {
    if (!card || !overrideMap.has(resourceKey(resource.resourceType, resource.id))) return;
    setHistoryTarget(resource);
    setRevisions(undefined);
    setHistoryError(undefined);
    void enterpriseContentApi
      .listOverrideRevisions(card.id, resource.resourceType, resource.id)
      .then(setRevisions, setHistoryError);
  };

  const rollback = (revisionVersion: number) => {
    if (!card || !historyTarget || saving) return;
    const current = overrideMap.get(resourceKey(historyTarget.resourceType, historyTarget.id));
    if (!current) return;
    setSaving(true);
    void enterpriseContentApi
      .rollbackOverride(card.id, historyTarget.resourceType, historyTarget.id, current.version, revisionVersion)
      .then(() => {
        setHistoryTarget(undefined);
        setRevisions(undefined);
        reload();
      })
      .catch((error: unknown) => setHistoryError(error))
      .finally(() => setSaving(false));
  };

  const close = () => {
    if (!saving) onClose();
  };

  return (
    <>
    <Dialog open={open} onOpenChange={(_, data) => !data.open && close()}>
      <DialogSurface className="content-overrides-dialog">
        <DialogBody>
          <DialogTitle>员工名片内容覆盖</DialogTitle>
          <DialogContent>
            <p>
              {card?.displayName || "该员工"}可继承企业默认内容、对单项内容隐藏，或只调整该员工名片上的展示文案。
              不会改动企业源内容，也不会绕过内容发布与可见性规则。
            </p>
            <p className="form-note">“继承”会保留一条可审计的恢复默认记录；“移除覆盖”会清除该员工的个性化历史。两者当前展示结果相同。</p>
            {state.status === "loading" || state.status === "idle" ? (
              <div className="inline-loading"><Spinner size="tiny" />正在读取有效内容与覆盖策略…</div>
            ) : state.status === "permission" ? (
              <MessageBar intent="warning"><MessageBarBody>当前账号无权管理员工名片内容覆盖。</MessageBarBody></MessageBar>
            ) : state.status === "error" ? (
              <MessageBar intent="error">
                <MessageBarBody>{friendlyError(state.error)} <Button appearance="subtle" size="small" onClick={reload}>重试</Button></MessageBarBody>
              </MessageBar>
            ) : readyState ? (
              <div className="content-override-list">
                {readyState.resources.map((resource) => {
                  const current = overrideMap.get(resourceKey(resource.resourceType, resource.id));
                  const effective = current?.mode ?? "inherit";
                  return (
                    <article className="content-override-row" key={resourceKey(resource.resourceType, resource.id)}>
                      <div>
                        <small>{resource.resourceType === "product" ? "产品与服务" : "公开案例"} · 源内容{resource.sourceStatus === "published" ? "已发布" : "未发布"}</small>
                        <strong>{resource.title}</strong>
                        <p>{resource.summary || "暂无摘要"}</p>
                        <span className={`content-override-mode mode-${effective}`}>当前：{effective === "inherit" ? "继承企业默认" : effective === "hidden" ? "此名片隐藏" : "自定义展示"}</span>
                      </div>
                      <div className="content-override-actions">
                        <Button size="small" appearance={effective === "inherit" ? "primary" : "secondary"} disabled={saving || effective === "inherit"} onClick={() => mutate(resource, "inherit")}>继承</Button>
                        <Button size="small" appearance={effective === "hidden" ? "primary" : "secondary"} disabled={saving || effective === "hidden"} onClick={() => mutate(resource, "hidden")}>隐藏</Button>
                        <Button size="small" appearance={effective === "custom" ? "primary" : "secondary"} disabled={saving} icon={<Edit24Regular />} onClick={() => { setEditing(resource); setCustom(displayFor(resource, current)); }}>自定义</Button>
                        {current && <Button size="small" appearance="subtle" icon={<ArrowCounterclockwise24Regular />} disabled={saving} onClick={() => openHistory(resource)}>历史</Button>}
                        {current && <Button size="small" appearance="subtle" icon={<Delete24Regular />} disabled={saving} onClick={() => removeOverride(resource)}>移除覆盖</Button>}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}
          </DialogContent>
          <DialogActions><Button appearance="secondary" onClick={close}>关闭</Button></DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>

      <Dialog open={Boolean(editing)} onOpenChange={(_, data) => !data.open && setEditing(undefined)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>自定义名片展示</DialogTitle>
            <DialogContent>
              <p>只影响“{editing?.title}”在此员工公开名片上的标题、摘要、封面和排序；源内容不变。</p>
              <Field label="展示标题"><Input value={custom.title ?? ""} maxLength={240} onChange={(_, data) => setCustom((value) => ({ ...value, title: data.value }))} /></Field>
              <Field label="展示摘要"><Textarea value={custom.summary ?? ""} maxLength={5000} resize="vertical" onChange={(_, data) => setCustom((value) => ({ ...value, summary: data.value }))} /></Field>
              <Field label="图片地址（可选）"><Input value={custom.imageUrl ?? ""} maxLength={2048} onChange={(_, data) => setCustom((value) => ({ ...value, imageUrl: data.value }))} /></Field>
              <Field label="显示排序（可选）"><Input type="number" min="0" max="1000000" value={custom.sortOrder?.toString() ?? ""} onChange={(_, data) => setCustom((value) => ({ ...value, sortOrder: data.value === "" ? undefined : Number(data.value) }))} /></Field>
            </DialogContent>
            <DialogActions>
              <Button appearance="secondary" disabled={saving} onClick={() => setEditing(undefined)}>取消</Button>
              <Button appearance="primary" disabled={saving || !custom.title?.trim() || !custom.summary?.trim()} onClick={() => editing && mutate(editing, "custom", custom)}>保存自定义展示</Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      <Dialog open={Boolean(historyTarget)} onOpenChange={(_, data) => !data.open && setHistoryTarget(undefined)}>
        <DialogSurface>
          <DialogBody>
            <DialogTitle>覆盖历史与回滚</DialogTitle>
            <DialogContent>
              <p>回滚会生成一个新的覆盖版本，不会抹除历史记录。</p>
              {historyError ? <MessageBar intent="error"><MessageBarBody>{friendlyError(historyError)}</MessageBarBody></MessageBar> : !revisions ? <div className="inline-loading"><Spinner size="tiny" />正在读取历史…</div> : (
                <div className="override-history-list">
                  {revisions.map((revision) => <div key={revision.version} className="override-history-row"><span>版本 {revision.version} · {revision.mode === "inherit" ? "继承企业默认" : revision.mode === "hidden" ? "隐藏" : "自定义展示"}</span><Button size="small" appearance="secondary" disabled={saving} onClick={() => rollback(revision.version)}>回滚到此版本</Button></div>)}
                </div>
              )}
            </DialogContent>
            <DialogActions><Button appearance="secondary" disabled={saving} onClick={() => setHistoryTarget(undefined)}>关闭</Button></DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </>
  );
}
