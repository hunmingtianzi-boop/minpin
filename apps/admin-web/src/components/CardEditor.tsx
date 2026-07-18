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
import {
  ArrowUpload24Regular,
  Delete24Regular,
  Dismiss24Regular,
  Save24Regular,
} from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { adminApi } from "../api/adminApi";
import { ApiError } from "../api/client";
import type { ManagedCard, ManagedCardInput } from "../api/types";
import { FormFeedback } from "./FormFeedback";

const MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024;
const CARD_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function emptyCard(cardKind: ManagedCard["cardKind"]): ManagedCardInput {
  return {
    cardKind,
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
}

function cardInput(item?: ManagedCard): ManagedCardInput {
  if (!item) return emptyCard("employee");
  return {
    cardKind: item.cardKind,
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
  createKind?: ManagedCard["cardKind"];
  onClose: () => void;
  onSaved: () => void;
};

export function CardEditor({
  open,
  item,
  createKind = "employee",
  onClose,
  onSaved,
}: CardEditorProps) {
  const [form, setForm] = useState<ManagedCardInput>(() => emptyCard(createKind));
  const [questionsText, setQuestionsText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [imageFile, setImageFile] = useState<File>();
  const [imagePreview, setImagePreview] = useState("");
  const imageInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const input = item ? cardInput(item) : emptyCard(createKind);
    setForm(input);
    setQuestionsText(input.suggestedQuestions.join("\n"));
    setImageFile(undefined);
    setAttempted(false);
    setError(undefined);
  }, [createKind, item, open]);

  useEffect(() => {
    if (!imageFile || typeof URL.createObjectURL !== "function") {
      setImagePreview("");
      return;
    }
    const preview = URL.createObjectURL(imageFile);
    setImagePreview(preview);
    return () => URL.revokeObjectURL(preview);
  }, [imageFile]);

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
  const ownerValid =
    form.cardKind === "enterprise" || !item || Boolean(form.ownerUserId?.trim());
  const valid =
    ownerValid &&
    Boolean(form.displayName.trim()) &&
    Boolean(form.title.trim()) &&
    questionsValid;

  const chooseImage = (file?: File) => {
    if (!file) return;
    setError(undefined);
    if (!CARD_IMAGE_TYPES.has(file.type)) {
      setError(
        new ApiError("仅支持 PNG、JPEG 或 WebP 图片。", {
          code: "CARD_ASSET_UNSUPPORTED_TYPE",
        }),
      );
      return;
    }
    if (file.size > MAX_CARD_IMAGE_BYTES) {
      setError(
        new ApiError("图片不能超过 5 MiB。", {
          code: "CARD_ASSET_TOO_LARGE",
        }),
      );
      return;
    }
    setImageFile(file);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      const uploaded = imageFile
        ? await adminApi.uploadCardAsset(imageFile)
        : undefined;
      const input = {
        ...form,
        avatarUrl: uploaded?.url ?? form.avatarUrl,
        suggestedQuestions: questions,
      };
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
          {item
            ? `编辑${item.cardKind === "enterprise" ? "企业" : "员工"}名片`
            : `新建${createKind === "enterprise" ? "企业" : "员工"}名片`}
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
              label={form.cardKind === "enterprise" ? "企业名称" : "展示姓名"}
              required
              validationState={
                attempted && !form.displayName.trim() ? "error" : "none"
              }
              validationMessage={
                attempted && !form.displayName.trim()
                  ? form.cardKind === "enterprise"
                    ? "请输入企业名称。"
                    : "请输入展示姓名。"
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
              label={
                form.cardKind === "enterprise" ? "业务定位或品牌标语" : "职务或头衔"
              }
              required
              validationState={attempted && !form.title.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.title.trim()
                  ? form.cardKind === "enterprise"
                    ? "请输入业务定位或品牌标语。"
                    : "请输入职务或头衔。"
                  : undefined
              }
            >
              <Input
                value={form.title}
                onChange={(_, data) => update("title", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          {form.cardKind === "employee" ? (
            <Field
              label="所有者用户 ID"
              required={Boolean(item)}
              hint={
                item
                  ? "企业管理员可将员工名片转移给本企业有效成员。"
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
          ) : (
            <div className="immutable-resource-note">
              <strong>企业官方名片</strong>
              <span>归企业所有，不绑定任何员工；发布后作为企业公开主页。</span>
            </div>
          )}

          <section
            className={`card-image-upload ${form.cardKind}`}
            aria-label={form.cardKind === "enterprise" ? "企业 Logo" : "员工头像"}
          >
            <div className="card-image-preview">
              {imagePreview || form.avatarUrl ? (
                <img
                  src={imagePreview || form.avatarUrl}
                  alt={form.cardKind === "enterprise" ? "企业 Logo 预览" : "员工头像预览"}
                />
              ) : (
                <span aria-hidden="true">
                  {(form.displayName.trim() || (form.cardKind === "enterprise" ? "企" : "员"))
                    .slice(0, 1)
                    .toUpperCase()}
                </span>
              )}
            </div>
            <div className="card-image-upload-copy">
              <strong>{form.cardKind === "enterprise" ? "企业 Logo" : "员工头像"}</strong>
              <span>支持 PNG、JPEG、WebP，最大 5 MiB；保存时自动上传并压缩。</span>
              {imageFile && <em>{imageFile.name}</em>}
              <div className="card-image-upload-actions">
                <input
                  ref={imageInputRef}
                  className="visually-hidden"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  aria-label={form.cardKind === "enterprise" ? "选择企业 Logo" : "选择员工头像"}
                  disabled={saving}
                  onChange={(event) => {
                    chooseImage(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
                <Button
                  type="button"
                  appearance="secondary"
                  icon={<ArrowUpload24Regular />}
                  onClick={() => imageInputRef.current?.click()}
                  disabled={saving}
                >
                  选择图片
                </Button>
                {(imageFile || form.avatarUrl) && (
                  <Button
                    type="button"
                    appearance="subtle"
                    icon={<Delete24Regular />}
                    onClick={() => {
                      setImageFile(undefined);
                      update("avatarUrl", "");
                    }}
                    disabled={saving}
                  >
                    移除
                  </Button>
                )}
              </div>
            </div>
          </section>

          <div className="form-grid two-columns">
            <Field label="图片地址（可选）" hint="也可填写站内路径或公开 HTTPS 地址。">
              <Input
                value={form.avatarUrl}
                onChange={(_, data) => {
                  setImageFile(undefined);
                  update("avatarUrl", data.value);
                }}
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
