import {
  Button,
  Field,
  Input,
  Textarea,
} from "@fluentui/react-components";
import { Save24Regular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { CardSettingsInput } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

const emptyCard: CardSettingsInput = {
  displayName: "",
  title: "",
  slug: "",
  avatarUrl: "",
  assistantName: "",
  welcomeMessage: "",
  suggestedQuestions: [],
  policyVersions: {
    privacy: "",
    chatNotice: "",
    leadConsent: "",
  },
  version: undefined,
};

const slugPattern = /^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$/;

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("保存名片设置时发生未知错误。", {
        code: "UNKNOWN_ERROR",
      });
}

export function CardSettingsPage() {
  const resource = useResource(() => adminApi.getCard());
  const [form, setForm] = useState<CardSettingsInput>(emptyCard);
  const [questionsText, setQuestionsText] = useState("");
  const [saving, setSaving] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [saveError, setSaveError] = useState<ApiError>();
  const [success, setSuccess] = useState<string>();

  useEffect(() => {
    if (resource.status !== "ready" || !resource.data) return;
    const {
      id: _id,
      status: _status,
      updatedAt: _updatedAt,
      ...input
    } = resource.data;
    setForm(input);
    setQuestionsText(input.suggestedQuestions.join("\n"));
  }, [resource.data, resource.status]);

  const update = (field: keyof CardSettingsInput, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setSuccess(undefined);
  };

  const updatePolicy = (
    field: keyof CardSettingsInput["policyVersions"],
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      policyVersions: { ...current.policyVersions, [field]: value },
    }));
    setSuccess(undefined);
  };

  const questions = questionsText
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const questionsValid =
    questions.length <= 6 && questions.every((value) => value.length <= 200);
  const slugValid = slugPattern.test(form.slug);
  const requiredValid =
    Boolean(form.displayName.trim()) && Boolean(form.title.trim()) && slugValid;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setSaveError(undefined);
    setSuccess(undefined);
    if (!requiredValid || !questionsValid || form.version === undefined || saving) {
      return;
    }

    setSaving(true);
    try {
      await adminApi.updateCard({ ...form, suggestedQuestions: questions });
      setSuccess("名片设置已由服务端确认保存。");
      resource.reload();
    } catch (error) {
      setSaveError(toApiError(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="名片设置"
        description="维护名片展示和 AI 助手入口。保存时使用服务端版本号进行并发冲突保护。"
        actions={
          resource.status === "ready" ? (
            <StatusBadge status={resource.data?.status} />
          ) : undefined
        }
      />

      {resource.status !== "ready" && (
        <section className="content-panel">
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "名片资料为空" : undefined}
            description={
              resource.status === "empty"
                ? "服务端没有返回名片资料，请联系平台管理员。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
          />
        </section>
      )}

      {resource.status === "ready" && (
        <form className="content-panel form-panel" onSubmit={submit} noValidate>
          <div className="form-section-heading">
            <div>
              <h2>名片资料</h2>
              <p>公开标识、显示姓名和职务为必填项。</p>
            </div>
            {resource.data?.updatedAt && (
              <span>上次更新：{formatTimestamp(resource.data.updatedAt)}</span>
            )}
          </div>

          <FormFeedback success={success} error={saveError} />

          <div className="form-grid two-columns">
            <Field
              label="显示姓名"
              required
              validationState={
                attempted && !form.displayName.trim() ? "error" : "none"
              }
              validationMessage={
                attempted && !form.displayName.trim()
                  ? "请输入名片显示姓名。"
                  : undefined
              }
            >
              <Input
                value={form.displayName}
                onChange={(_, data) => update("displayName", data.value)}
                disabled={saving}
              />
            </Field>

            <Field
              label="职务"
              required
              validationState={attempted && !form.title.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.title.trim() ? "请输入职务。" : undefined
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
            label="公开标识"
            required
            hint="长度为 3-96，仅允许小写字母、数字和连字符，首尾必须为字母或数字。"
            validationState={attempted && !slugValid ? "error" : "none"}
            validationMessage={
              attempted && !slugValid ? "公开标识格式不正确。" : undefined
            }
          >
            <Input
              value={form.slug}
              onChange={(_, data) =>
                update("slug", data.value.toLowerCase().replace(/\s+/g, "-"))
              }
              disabled={saving}
            />
          </Field>

          <Field label="头像图片地址">
            <Input
              type="url"
              value={form.avatarUrl}
              onChange={(_, data) => update("avatarUrl", data.value)}
              placeholder="https://"
              disabled={saving}
            />
          </Field>

          <div className="form-section-heading secondary">
            <div>
              <h2>AI 助手</h2>
              <p>配置访客进入问答区域时看到的助手名称、欢迎语和推荐问题。</p>
            </div>
          </div>

          <Field label="助手名称">
            <Input
              value={form.assistantName}
              onChange={(_, data) => update("assistantName", data.value)}
              disabled={saving}
            />
          </Field>

          <Field label="欢迎语">
            <Textarea
              value={form.welcomeMessage}
              onChange={(_, data) => update("welcomeMessage", data.value)}
              resize="vertical"
              rows={4}
              disabled={saving}
            />
          </Field>

          <Field
            label="推荐问题"
            hint="每行一个问题，最多 6 个，每个不超过 200 个字符。"
            validationState={attempted && !questionsValid ? "error" : "none"}
            validationMessage={
              attempted && !questionsValid
                ? "推荐问题数量或长度超出限制。"
                : undefined
            }
          >
            <Textarea
              value={questionsText}
              onChange={(_, data) => {
                setQuestionsText(data.value);
                setSuccess(undefined);
              }}
              resize="vertical"
              rows={6}
              disabled={saving}
            />
          </Field>

          <div className="form-section-heading secondary">
            <div>
              <h2>政策版本</h2>
              <p>仅填写已正式发布的政策版本标识，空白版本不会提交。</p>
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
            <Field label="聊天提示版本">
              <Input
                value={form.policyVersions.chatNotice}
                onChange={(_, data) => updatePolicy("chatNotice", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="线索同意版本">
              <Input
                value={form.policyVersions.leadConsent}
                onChange={(_, data) => updatePolicy("leadConsent", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <div className="form-actions">
            <Button
              type="submit"
              appearance="primary"
              icon={<Save24Regular />}
              disabled={
                saving ||
                !requiredValid ||
                !questionsValid ||
                form.version === undefined
              }
            >
              {saving ? "正在保存" : "保存名片设置"}
            </Button>
          </div>
        </form>
      )}
    </main>
  );
}
