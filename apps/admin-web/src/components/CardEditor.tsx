import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Field,
  Input,
  OverlayDrawer,
  Textarea,
} from "@fluentui/react-components";
import { Dismiss24Regular, Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { ManagedCard, ManagedCardInput } from "../api/types";
import { FormFeedback } from "./FormFeedback";

const emptyCard: ManagedCardInput = {
  ownerUserId: "",
  displayName: "",
  title: "",
  avatarUrl: "",
  assistantName: "",
  welcomeMessage: "",
  suggestedQuestions: [],
  policyVersions: {
    privacy: "",
    chatNotice: "",
    leadConsent: "",
  },
};

function cardInput(item?: ManagedCard): ManagedCardInput {
  if (!item) return emptyCard;
  return {
    ownerUserId: item.ownerUserId,
    displayName: item.displayName,
    title: item.title,
    avatarUrl: item.avatarUrl,
    assistantName: item.assistantName,
    welcomeMessage: item.welcomeMessage,
    suggestedQuestions: item.suggestedQuestions,
    policyVersions: item.policyVersions,
  };
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存名片时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

type CardEditorProps = {
  open: boolean;
  item?: ManagedCard;
  onClose: () => void;
  onSaved: () => void;
};

export function CardEditor({ open, item, onClose, onSaved }: CardEditorProps) {
  const [form, setForm] = useState<ManagedCardInput>(emptyCard);
  const [questionsText, setQuestionsText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    if (!open) return;
    const input = cardInput(item);
    setForm(input);
    setQuestionsText(input.suggestedQuestions.join("\n"));
    setAttempted(false);
    setError(undefined);
  }, [item, open]);

  const update = (field: keyof ManagedCardInput, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };
  const updatePolicy = (
    field: keyof ManagedCardInput["policyVersions"],
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      policyVersions: { ...current.policyVersions, [field]: value },
    }));
  };

  const questions = questionsText
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const questionsValid =
    questions.length <= 6 && questions.every((value) => value.length <= 200);
  const ownerValid = !item || Boolean(form.ownerUserId?.trim());
  const valid =
    ownerValid &&
    Boolean(form.displayName.trim()) &&
    Boolean(form.title.trim()) &&
    questionsValid;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      const input = { ...form, suggestedQuestions: questions };
      if (item) {
        await adminApi.updateManagedCard(item.id, item.version, input);
      } else {
        await adminApi.createManagedCard(input);
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
              aria-label="关闭名片编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {item ? "编辑名片" : "新建名片"}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <form className="catalog-editor-form" onSubmit={submit} noValidate>
          <FormFeedback error={error} />

          {item && (
            <div className="immutable-resource-note">
              <strong>公开标识</strong>
              <code>{item.slug}</code>
              <span>安全链接由服务端生成，编辑时不会更改。</span>
            </div>
          )}

          <div className="form-grid two-columns">
            <Field
              label="展示姓名"
              required
              validationState={
                attempted && !form.displayName.trim() ? "error" : "none"
              }
              validationMessage={
                attempted && !form.displayName.trim() ? "请输入展示姓名。" : undefined
              }
            >
              <Input
                value={form.displayName}
                onChange={(_, data) => update("displayName", data.value)}
                disabled={saving}
              />
            </Field>
            <Field
              label="职务或头衔"
              required
              validationState={attempted && !form.title.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.title.trim() ? "请输入职务或头衔。" : undefined
              }
            >
              <Input
                value={form.title}
                onChange={(_, data) => update("title", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <Field
            label="所有者用户 ID"
            required={Boolean(item)}
            hint={
              item
                ? "企业管理员可将名片转移给本企业有效成员。"
                : "留空时，服务端会将当前账号设为所有者。"
            }
            validationState={attempted && !ownerValid ? "error" : "none"}
            validationMessage={
              attempted && !ownerValid ? "请保留有效的所有者用户 ID。" : undefined
            }
          >
            <Input
              value={form.ownerUserId ?? ""}
              onChange={(_, data) => update("ownerUserId", data.value)}
              disabled={saving}
            />
          </Field>

          <div className="form-grid two-columns">
            <Field label="头像地址" hint="允许站内路径或公开 HTTPS 地址。">
              <Input
                value={form.avatarUrl}
                onChange={(_, data) => update("avatarUrl", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="助手名称">
              <Input
                value={form.assistantName}
                onChange={(_, data) => update("assistantName", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <Field label="欢迎语">
            <Textarea
              value={form.welcomeMessage}
              onChange={(_, data) => update("welcomeMessage", data.value)}
              rows={4}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <Field
            label="建议问题"
            hint="每行一个问题，最多 6 条，每条不超过 200 个字符。"
            validationState={attempted && !questionsValid ? "error" : "none"}
            validationMessage={
              attempted && !questionsValid ? "请检查建议问题的数量和长度。" : undefined
            }
          >
            <Textarea
              value={questionsText}
              onChange={(_, data) => setQuestionsText(data.value)}
              rows={7}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <div className="form-section-heading secondary">
            <div>
              <h2>政策版本</h2>
              <p>公开前请确认政策版本与服务端发布内容一致。</p>
            </div>
          </div>
          <div className="form-grid two-columns">
            <Field label="隐私政策版本">
              <Input
                value={form.policyVersions.privacy}
                onChange={(_, data) => updatePolicy("privacy", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="对话提示版本">
              <Input
                value={form.policyVersions.chatNotice}
                onChange={(_, data) => updatePolicy("chatNotice", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="留资同意版本">
              <Input
                value={form.policyVersions.leadConsent}
                onChange={(_, data) => updatePolicy("leadConsent", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

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
              {saving ? "正在保存" : "保存名片"}
            </Button>
          </div>
        </form>
      </DrawerBody>
    </OverlayDrawer>
  );
}
