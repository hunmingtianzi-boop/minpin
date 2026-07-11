import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
  Input,
  OverlayDrawer,
  Select,
  Textarea,
} from "@fluentui/react-components";
import { Dismiss24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  KnowledgeDocument,
  KnowledgeDocumentDetail,
  KnowledgeDocumentInput,
  KnowledgeVisibility,
} from "../api/types";
import { FormFeedback } from "./FormFeedback";
import { ResourceState } from "./ResourceState";

const emptyKnowledge: KnowledgeDocumentInput = {
  title: "",
  answer: "",
  visibility: "public",
  metadata: { source_label: "企业后台" },
};

export type KnowledgeEditorFormProps = {
  initial?: KnowledgeDocumentInput;
  saving: boolean;
  error?: ApiError;
  onSubmit: (input: KnowledgeDocumentInput) => Promise<void>;
  onCancel: () => void;
};

export function KnowledgeEditorForm({
  initial,
  saving,
  error,
  onSubmit,
  onCancel,
}: KnowledgeEditorFormProps) {
  const [form, setForm] = useState<KnowledgeDocumentInput>(emptyKnowledge);
  const [attempted, setAttempted] = useState(false);

  useEffect(() => {
    setForm(initial ?? emptyKnowledge);
    setAttempted(false);
  }, [initial]);

  const update = (field: "title" | "answer", value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const sourceLabel =
    typeof form.metadata.source_label === "string"
      ? form.metadata.source_label
      : "";
  const valid = Boolean(form.title.trim()) && Boolean(form.answer.trim());

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (!valid || saving) return;
    void onSubmit({
      ...form,
      title: form.title.trim(),
      answer: form.answer.trim(),
      metadata: {
        ...form.metadata,
        source_label: sourceLabel.trim() || "企业后台",
      },
    });
  };

  return (
    <form className="knowledge-editor-form" onSubmit={submit} noValidate>
      <FormFeedback error={error} />

      <Field
        label="FAQ 问题"
        required
        hint="该问题同时作为知识文档标题。"
        validationState={attempted && !form.title.trim() ? "error" : "none"}
        validationMessage={
          attempted && !form.title.trim() ? "请输入 FAQ 问题。" : undefined
        }
      >
        <Textarea
          value={form.title}
          onChange={(_, data) => update("title", data.value)}
          resize="vertical"
          rows={3}
          disabled={saving}
        />
      </Field>

      <Field
        label="标准答案"
        required
        hint="发布后，该内容会进入 AI 知识索引流程。"
        validationState={attempted && !form.answer.trim() ? "error" : "none"}
        validationMessage={
          attempted && !form.answer.trim() ? "请输入标准答案。" : undefined
        }
      >
        <Textarea
          value={form.answer}
          onChange={(_, data) => update("answer", data.value)}
          resize="vertical"
          rows={12}
          disabled={saving}
        />
      </Field>

      <div className="form-grid two-columns">
        <Field label="可见范围">
          <Select
            value={form.visibility}
            onChange={(_, data) =>
              setForm((current) => ({
                ...current,
                visibility: data.value as KnowledgeVisibility,
              }))
            }
            disabled={saving}
          >
            <option value="public">公开访客</option>
            <option value="authenticated">已认证访客</option>
            <option value="internal">仅内部</option>
          </Select>
        </Field>

        <Field label="来源标签">
          <Input
            value={sourceLabel}
            onChange={(_, data) =>
              setForm((current) => ({
                ...current,
                metadata: {
                  ...current.metadata,
                  source_label: data.value,
                },
              }))
            }
            disabled={saving}
          />
        </Field>
      </div>

      <div className="drawer-form-actions">
        <Button type="button" appearance="secondary" onClick={onCancel} disabled={saving}>
          取消
        </Button>
        <Button
          type="submit"
          appearance="primary"
          icon={<Save24Regular />}
          disabled={saving || !valid}
        >
          {saving ? "正在保存" : "保存草稿"}
        </Button>
      </div>
    </form>
  );
}

type DetailState =
  | { status: "idle" | "loading" }
  | { status: "ready"; detail: KnowledgeDocumentDetail }
  | { status: "error" | "permission"; error: ApiError };

type KnowledgeEditorProps = {
  open: boolean;
  document?: KnowledgeDocument;
  onClose: () => void;
  onSaved: () => void;
};

export function KnowledgeEditor({
  open,
  document,
  onClose,
  onSaved,
}: KnowledgeEditorProps) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [createdDocumentId, setCreatedDocumentId] = useState<string>();
  const [detailState, setDetailState] = useState<DetailState>({ status: "idle" });
  const [detailReloadKey, setDetailReloadKey] = useState(0);

  useEffect(() => {
    if (!open) {
      setError(undefined);
      setCreatedDocumentId(undefined);
      setDetailState({ status: "idle" });
      return;
    }
    if (!document) {
      setDetailState({ status: "idle" });
      return;
    }

    let active = true;
    setDetailState({ status: "loading" });
    void adminApi.getKnowledgeDocument(document.id).then(
      (detail) => {
        if (active) setDetailState({ status: "ready", detail });
      },
      (caught: unknown) => {
        if (!active) return;
        const apiError =
          caught instanceof ApiError
            ? caught
            : new ApiError("加载知识详情时发生未知错误。", {
                code: "UNKNOWN_ERROR",
              });
        setDetailState({
          status: apiError.status === 403 ? "permission" : "error",
          error: apiError,
        });
      },
    );
    return () => {
      active = false;
    };
  }, [detailReloadKey, document, open]);

  const save = async (input: KnowledgeDocumentInput) => {
    setSaving(true);
    setError(undefined);
    try {
      let documentId = document?.id ?? createdDocumentId;
      if (!documentId) {
        documentId = await adminApi.createKnowledgeDocument(input.title);
        setCreatedDocumentId(documentId);
      }
      await adminApi.updateKnowledgeDocument(documentId, input);
      onSaved();
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError("保存知识内容时发生未知错误。", {
              code: "UNKNOWN_ERROR",
            }),
      );
    } finally {
      setSaving(false);
    }
  };

  const initial: KnowledgeDocumentInput | undefined =
    detailState.status === "ready"
      ? {
          title: detailState.detail.title,
          answer: detailState.detail.rawText,
          visibility: detailState.detail.visibility,
          metadata: detailState.detail.metadata,
        }
      : document
        ? undefined
        : emptyKnowledge;

  const showForm = !document || detailState.status === "ready";

  return (
    <OverlayDrawer
      position="end"
      size="medium"
      open={open}
      onOpenChange={(_, data) => {
        if (!data.open && !saving) onClose();
      }}
    >
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button
              appearance="subtle"
              icon={<Dismiss24Regular />}
              aria-label="关闭编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {document ? "编辑知识 FAQ" : "新建知识 FAQ"}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        {document && detailState.status !== "ready" && (
          <ResourceState
            compact
            status={detailState.status === "idle" ? "loading" : detailState.status}
            description={
              detailState.status === "error" || detailState.status === "permission"
                ? detailState.error.message
                : undefined
            }
            errorCode={
              detailState.status === "error" || detailState.status === "permission"
                ? detailState.error.code
                : undefined
            }
            requestId={
              detailState.status === "error" || detailState.status === "permission"
                ? detailState.error.requestId
                : undefined
            }
            onRetry={
              detailState.status === "error"
                ? () => setDetailReloadKey((value) => value + 1)
                : undefined
            }
          />
        )}
        {showForm && initial && (
          <KnowledgeEditorForm
            initial={initial}
            saving={saving}
            error={error}
            onSubmit={save}
            onCancel={onClose}
          />
        )}
      </DrawerBody>
    </OverlayDrawer>
  );
}
