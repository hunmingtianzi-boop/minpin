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
  CaseStudy,
  CaseStudyInput,
  ContentVisibility,
  Product,
  ProductInput,
} from "../api/types";
import { FormFeedback } from "./FormFeedback";

const slugPattern = /^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$/;

const emptyProduct: ProductInput = {
  slug: "",
  name: "",
  category: "",
  summary: "",
  detail: "",
  audience: "",
  priceBoundary: "",
  imageUrl: "",
  visibility: "public",
  sortOrder: 0,
  settings: {},
};

const emptyCaseStudy: CaseStudyInput = {
  slug: "",
  title: "",
  industry: "",
  background: "",
  solution: "",
  result: "",
  clientDisplayName: "",
  imageUrl: "",
  visibility: "public",
  sortOrder: 0,
  settings: {},
};

function toApiError(error: unknown, message: string): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError(message, { code: "UNKNOWN_ERROR" });
}

function productInput(item?: Product): ProductInput {
  if (!item) return emptyProduct;
  const {
    id: _id,
    status: _status,
    version: _version,
    publishedAt: _publishedAt,
    createdAt: _createdAt,
    updatedAt: _updatedAt,
    ...input
  } = item;
  return input;
}

function caseStudyInput(item?: CaseStudy): CaseStudyInput {
  if (!item) return emptyCaseStudy;
  const {
    id: _id,
    status: _status,
    version: _version,
    publishedAt: _publishedAt,
    createdAt: _createdAt,
    updatedAt: _updatedAt,
    ...input
  } = item;
  return input;
}

type ProductEditorProps = {
  open: boolean;
  item?: Product;
  onClose: () => void;
  onSaved: () => void;
};

export function ProductEditor({
  open,
  item,
  onClose,
  onSaved,
}: ProductEditorProps) {
  const [form, setForm] = useState<ProductInput>(emptyProduct);
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    if (!open) return;
    setForm(productInput(item));
    setAttempted(false);
    setError(undefined);
  }, [item, open]);

  const update = <K extends keyof ProductInput>(field: K, value: ProductInput[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
  };
  const valid =
    slugPattern.test(form.slug) &&
    Boolean(form.name.trim()) &&
    Boolean(form.summary.trim()) &&
    Boolean(form.detail.trim());

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      if (item) {
        await adminApi.updateProduct(item.id, item.version, form);
      } else {
        await adminApi.createProduct(form);
      }
      onSaved();
    } catch (caught) {
      setError(toApiError(caught, "保存产品时发生未知错误。"));
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
              aria-label="关闭产品编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {item ? "编辑产品" : "新建产品"}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <form className="catalog-editor-form" onSubmit={submit} noValidate>
          <FormFeedback error={error} />

          <div className="form-grid two-columns">
            <Field
              label="产品名称"
              required
              validationState={attempted && !form.name.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.name.trim() ? "请输入产品名称。" : undefined
              }
            >
              <Input
                value={form.name}
                onChange={(_, data) => update("name", data.value)}
                disabled={saving}
              />
            </Field>
            <Field
              label="链接标识"
              required
              hint="使用小写字母、数字和连字符，至少 3 个字符。"
              validationState={attempted && !slugPattern.test(form.slug) ? "error" : "none"}
              validationMessage={
                attempted && !slugPattern.test(form.slug)
                  ? "请输入有效的链接标识。"
                  : undefined
              }
            >
              <Input
                value={form.slug}
                onChange={(_, data) => update("slug", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="产品分类">
              <Input
                value={form.category}
                onChange={(_, data) => update("category", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="排序值" hint="数字越小越靠前。">
              <Input
                type="number"
                min={0}
                value={String(form.sortOrder)}
                onChange={(_, data) =>
                  update("sortOrder", Math.max(0, Number(data.value) || 0))
                }
                disabled={saving}
              />
            </Field>
          </div>

          <Field
            label="产品摘要"
            required
            validationState={attempted && !form.summary.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.summary.trim() ? "请输入产品摘要。" : undefined
            }
          >
            <Textarea
              value={form.summary}
              onChange={(_, data) => update("summary", data.value)}
              rows={3}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <Field
            label="产品详情"
            required
            validationState={attempted && !form.detail.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.detail.trim() ? "请输入产品详情。" : undefined
            }
          >
            <Textarea
              value={form.detail}
              onChange={(_, data) => update("detail", data.value)}
              rows={8}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <div className="form-grid two-columns">
            <Field label="适用客户">
              <Textarea
                value={form.audience}
                onChange={(_, data) => update("audience", data.value)}
                rows={3}
                resize="vertical"
                disabled={saving}
              />
            </Field>
            <Field label="价格边界">
              <Textarea
                value={form.priceBoundary}
                onChange={(_, data) => update("priceBoundary", data.value)}
                rows={3}
                resize="vertical"
                disabled={saving}
              />
            </Field>
            <Field label="可见范围">
              <Select
                value={form.visibility}
                onChange={(_, data) =>
                  update("visibility", data.value as ContentVisibility)
                }
                disabled={saving}
              >
                <option value="public">公开访客</option>
                <option value="authenticated">已认证访客</option>
                <option value="internal">仅内部</option>
              </Select>
            </Field>
            <Field label="图片地址" hint="允许站内路径或公开 HTTPS 地址。">
              <Input
                value={form.imageUrl}
                onChange={(_, data) => update("imageUrl", data.value)}
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
              {saving ? "正在保存" : "保存产品"}
            </Button>
          </div>
        </form>
      </DrawerBody>
    </OverlayDrawer>
  );
}

type CaseStudyEditorProps = {
  open: boolean;
  item?: CaseStudy;
  onClose: () => void;
  onSaved: () => void;
};

export function CaseStudyEditor({
  open,
  item,
  onClose,
  onSaved,
}: CaseStudyEditorProps) {
  const [form, setForm] = useState<CaseStudyInput>(emptyCaseStudy);
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();

  useEffect(() => {
    if (!open) return;
    setForm(caseStudyInput(item));
    setAttempted(false);
    setError(undefined);
  }, [item, open]);

  const update = <K extends keyof CaseStudyInput>(
    field: K,
    value: CaseStudyInput[K],
  ) => setForm((current) => ({ ...current, [field]: value }));
  const valid =
    slugPattern.test(form.slug) &&
    Boolean(form.title.trim()) &&
    Boolean(form.background.trim()) &&
    Boolean(form.solution.trim()) &&
    Boolean(form.result.trim());

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      if (item) {
        await adminApi.updateCaseStudy(item.id, item.version, form);
      } else {
        await adminApi.createCaseStudy(form);
      }
      onSaved();
    } catch (caught) {
      setError(toApiError(caught, "保存案例时发生未知错误。"));
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
              aria-label="关闭案例编辑器"
              onClick={onClose}
              disabled={saving}
            />
          }
        >
          {item ? "编辑案例" : "新建案例"}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <form className="catalog-editor-form" onSubmit={submit} noValidate>
          <FormFeedback error={error} />

          <div className="form-grid two-columns">
            <Field
              label="案例标题"
              required
              validationState={attempted && !form.title.trim() ? "error" : "none"}
              validationMessage={
                attempted && !form.title.trim() ? "请输入案例标题。" : undefined
              }
            >
              <Input
                value={form.title}
                onChange={(_, data) => update("title", data.value)}
                disabled={saving}
              />
            </Field>
            <Field
              label="链接标识"
              required
              hint="使用小写字母、数字和连字符，至少 3 个字符。"
              validationState={attempted && !slugPattern.test(form.slug) ? "error" : "none"}
              validationMessage={
                attempted && !slugPattern.test(form.slug)
                  ? "请输入有效的链接标识。"
                  : undefined
              }
            >
              <Input
                value={form.slug}
                onChange={(_, data) => update("slug", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="所属行业">
              <Input
                value={form.industry}
                onChange={(_, data) => update("industry", data.value)}
                disabled={saving}
              />
            </Field>
            <Field label="客户展示名称">
              <Input
                value={form.clientDisplayName}
                onChange={(_, data) => update("clientDisplayName", data.value)}
                disabled={saving}
              />
            </Field>
          </div>

          <Field
            label="项目背景"
            required
            validationState={attempted && !form.background.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.background.trim() ? "请输入项目背景。" : undefined
            }
          >
            <Textarea
              value={form.background}
              onChange={(_, data) => update("background", data.value)}
              rows={5}
              resize="vertical"
              disabled={saving}
            />
          </Field>
          <Field
            label="解决方案"
            required
            validationState={attempted && !form.solution.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.solution.trim() ? "请输入解决方案。" : undefined
            }
          >
            <Textarea
              value={form.solution}
              onChange={(_, data) => update("solution", data.value)}
              rows={6}
              resize="vertical"
              disabled={saving}
            />
          </Field>
          <Field
            label="项目成果"
            required
            validationState={attempted && !form.result.trim() ? "error" : "none"}
            validationMessage={
              attempted && !form.result.trim() ? "请输入项目成果。" : undefined
            }
          >
            <Textarea
              value={form.result}
              onChange={(_, data) => update("result", data.value)}
              rows={5}
              resize="vertical"
              disabled={saving}
            />
          </Field>

          <div className="form-grid two-columns">
            <Field label="可见范围">
              <Select
                value={form.visibility}
                onChange={(_, data) =>
                  update("visibility", data.value as ContentVisibility)
                }
                disabled={saving}
              >
                <option value="public">公开访客</option>
                <option value="authenticated">已认证访客</option>
                <option value="internal">仅内部</option>
              </Select>
            </Field>
            <Field label="排序值" hint="数字越小越靠前。">
              <Input
                type="number"
                min={0}
                value={String(form.sortOrder)}
                onChange={(_, data) =>
                  update("sortOrder", Math.max(0, Number(data.value) || 0))
                }
                disabled={saving}
              />
            </Field>
            <Field label="图片地址" hint="允许站内路径或公开 HTTPS 地址。">
              <Input
                value={form.imageUrl}
                onChange={(_, data) => update("imageUrl", data.value)}
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
              {saving ? "正在保存" : "保存案例"}
            </Button>
          </div>
        </form>
      </DrawerBody>
    </OverlayDrawer>
  );
}
