import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
  Input,
  OverlayDrawer,
  Select,
  Switch,
  Textarea,
} from "@fluentui/react-components";
import { Dismiss24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type {
  ForbiddenAction,
  ForbiddenTopic,
  ForbiddenTopicInput,
} from "../api/types";
import { FormFeedback } from "./FormFeedback";

const emptyTopic: ForbiddenTopicInput = {
  topic: "",
  matchTerms: [],
  action: "refuse",
  safeResponse: "",
  isActive: true,
};

function topicInput(item?: ForbiddenTopic): ForbiddenTopicInput {
  if (!item) return emptyTopic;
  return {
    topic: item.topic,
    matchTerms: item.matchTerms,
    action: item.action,
    safeResponse: item.safeResponse,
    isActive: item.isActive,
  };
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存禁答主题时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

type ForbiddenTopicEditorProps = {
  open: boolean;
  item?: ForbiddenTopic;
  onClose: () => void;
  onSaved: () => void;
};

export function ForbiddenTopicEditor({
  open,
  item,
  onClose,
  onSaved,
}: ForbiddenTopicEditorProps) {
  const [form, setForm] = useState<ForbiddenTopicInput>(emptyTopic);
  const [termsText, setTermsText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    if (!open) return;
    const input = topicInput(item);
    setForm(input);
    setTermsText(input.matchTerms.join("\n"));
    setAttempted(false);
    setError(undefined);
  }, [item, open]);

  const terms = termsText
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const termsValid =
    terms.length <= 64 && terms.every((value) => value.length <= 160);
  const safeResponseValid =
    form.action !== "safe_template" || Boolean(form.safeResponse.trim());
  const valid = Boolean(form.topic.trim()) && termsValid && safeResponseValid;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      const input = { ...form, matchTerms: terms };
      if (item) {
        await adminApi.updateForbiddenTopic(item.id, item.version, input);
      } else {
        await adminApi.createForbiddenTopic(input);
      }
      onSaved();
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setSaving(false);
    }
  };

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
              aria-label="关闭禁答主题编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {item ? "编辑禁答主题" : "新建禁答主题"}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <form className="catalog-editor-form" onSubmit={submit} noValidate>
          <FormFeedback error={error} />

          <Field
            label="主题名称"
            required
            hint="使用清晰的业务名称，例如价格承诺或竞争对手贬损。"
            validationState={attempted && !form.topic.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.topic.trim() ? "请输入主题名称。" : undefined
            }
          >
            <Input
              value={form.topic}
              onChange={(_, data) =>
                setForm((current) => ({ ...current, topic: data.value }))
              }
              disabled={saving}
            />
          </Field>

          <Field
            label="匹配词"
            hint="每行一个匹配词，最多 64 条，每条不超过 160 个字符。"
            validationState={attempted && !termsValid ? "error" : "none"}
            validationMessage={
              attempted && !termsValid ? "请检查匹配词的数量和长度。" : undefined
            }
          >
            <Textarea
              value={termsText}
              onChange={(_, data) => setTermsText(data.value)}
              rows={8}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <Field label="处理动作">
            <Select
              value={form.action}
              onChange={(_, data) =>
                setForm((current) => ({
                  ...current,
                  action: data.value as ForbiddenAction,
                }))
              }
              disabled={saving}
            >
              <option value="refuse">拒绝回答</option>
              <option value="handoff">建议转人工</option>
              <option value="safe_template">使用安全模板</option>
            </Select>
          </Field>

          <Field
            label="安全回复"
            required={form.action === "safe_template"}
            hint="当动作选择安全模板时，该回复为必填项。"
            validationState={attempted && !safeResponseValid ? "error" : "none"}
            validationMessage={
              attempted && !safeResponseValid ? "请输入安全回复。" : undefined
            }
          >
            <Textarea
              value={form.safeResponse}
              onChange={(_, data) =>
                setForm((current) => ({ ...current, safeResponse: data.value }))
              }
              rows={6}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          {!item && (
            <Switch
              checked={form.isActive}
              label="创建后立即启用"
              onChange={(_, data) =>
                setForm((current) => ({ ...current, isActive: data.checked }))
              }
              disabled={saving}
            />
          )}

          <div className="drawer-form-actions">
            <Button type="button" appearance="secondary" onClick={onClose} disabled={saving}>
              取消
            </Button>
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={saving}
            >
              {saving ? "正在保存" : "保存禁答主题"}
            </Button>
          </div>
        </form>
      </DrawerBody>
    </OverlayDrawer>
  );
}
