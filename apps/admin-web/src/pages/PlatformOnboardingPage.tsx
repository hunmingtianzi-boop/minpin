import {
  Button,
  Checkbox,
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
  ProgressBar,
  Textarea,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  ArrowUpload24Regular,
  CheckmarkCircle24Regular,
  Dismiss24Regular,
  Sparkle24Regular,
} from "@fluentui/react-icons";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";

import type {
  ConfirmPlatformOnboardingInput,
  PlatformOnboardingSession,
  PlatformOnboardingSuggestion,
  StartPlatformOnboardingInput,
} from "../api/types";
import { validateKnowledgeImportFiles } from "../components/KnowledgeImportPanel";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";

import styles from "./PlatformOnboardingPage.module.css";

export type PlatformOnboardingImportItem = {
  id: string;
  fileName: string;
  status: "pending" | "processing" | "completed" | "failed" | "dead_letter";
  errorCode?: string;
  errorMessage?: string;
};

export type PlatformOnboardingOperationError = {
  status?: number;
  code?: string;
  message: string;
  requestId?: string;
};

export type PlatformOnboardingAdminSummary = {
  account: string;
  displayName: string;
};

type ReviewValues = Omit<ConfirmPlatformOnboardingInput, "expectedVersion">;

export type PlatformOnboardingPageProps = {
  session?: PlatformOnboardingSession | null;
  importItems?: PlatformOnboardingImportItem[];
  adminSummary?: PlatformOnboardingAdminSummary;
  initialReview?: Partial<ReviewValues>;
  llmAvailability: "ready" | "unavailable" | "failed";
  resourceStatus?: "ready" | "loading" | "permission" | "error";
  resourceError?: PlatformOnboardingOperationError;
  onStart: (input: StartPlatformOnboardingInput) => Promise<void>;
  onUpload: (onboardingSessionId: string, files: File[]) => Promise<void>;
  onGenerate: (onboardingSessionId: string, expectedVersion: number) => Promise<void>;
  onConfirm: (
    onboardingSessionId: string,
    input: ConfirmPlatformOnboardingInput,
  ) => Promise<void>;
  onCancel: (
    onboardingSessionId: string,
    reason: string,
    expectedVersion: number,
  ) => Promise<void>;
  onRefresh?: () => void;
  onStartAnother?: () => void;
  onOpenEnterprises?: () => void;
};

type BusyOperation = "start" | "upload" | "generate" | "confirm" | "cancel";

const emptyStart: StartPlatformOnboardingInput = {
  tenantSlug: "",
  tenantName: "",
  adminAccount: "",
  adminDisplayName: "",
  adminPassword: "",
};

const emptyReview: ReviewValues = {
  tenantName: "",
  companyName: "",
  industry: "",
  summary: "",
  website: "",
  initialCardDisplayName: "",
  initialCardTitle: "",
  assistantName: "",
  welcomeMessage: "",
};

const slugPattern = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

const reviewFieldMeta: Array<{
  key: keyof ReviewValues;
  label: string;
  area?: boolean;
  required?: boolean;
  group: "enterprise" | "card";
}> = [
  { key: "tenantName", label: "租户名称", required: true, group: "enterprise" },
  { key: "companyName", label: "企业名称", required: true, group: "enterprise" },
  { key: "industry", label: "行业", group: "enterprise" },
  { key: "website", label: "企业网站", group: "enterprise" },
  { key: "summary", label: "企业简介", area: true, group: "enterprise" },
  {
    key: "initialCardDisplayName",
    label: "初始名片姓名",
    required: true,
    group: "card",
  },
  { key: "initialCardTitle", label: "初始名片职位", group: "card" },
  { key: "assistantName", label: "AI 助手名称", group: "card" },
  { key: "welcomeMessage", label: "欢迎语", area: true, group: "card" },
];

const suggestionFieldMap: Record<string, keyof ReviewValues> = {
  tenant_name: "tenantName",
  tenantName: "tenantName",
  company_name: "companyName",
  companyName: "companyName",
  industry: "industry",
  website: "website",
  summary: "summary",
  initial_card_display_name: "initialCardDisplayName",
  initialCardDisplayName: "initialCardDisplayName",
  initial_card_title: "initialCardTitle",
  initialCardTitle: "initialCardTitle",
  assistant_name: "assistantName",
  assistantName: "assistantName",
  welcome_message: "welcomeMessage",
  welcomeMessage: "welcomeMessage",
};

const businessProfileLabels: Record<string, string> = {
  business_positioning: "业务定位",
  products_services: "产品与服务",
  target_customers: "目标客户与场景",
  customer_pain_points: "客户痛点",
  core_capabilities: "核心能力",
  business_model: "业务与交付模式",
  differentiators: "可验证差异点",
  business_directions: "明确业务方向",
  sales_opening: "建议业务开场",
  evidence_conflicts: "资料冲突与待确认项",
  missing_information: "待补资料",
};

const stepLabels = ["基础信息", "上传解析", "智能分析", "人工确认", "完成"];

function sessionStep(session?: PlatformOnboardingSession | null): number {
  if (!session) return 0;
  if (session.status === "confirmed") return 4;
  if (["review", "manual_required", "ready_to_confirm"].includes(session.status)) return 3;
  if (session.suggestions.length > 0) return 2;
  return 1;
}

function asOperationError(value: unknown): PlatformOnboardingOperationError {
  const error = value as Partial<PlatformOnboardingOperationError>;
  if (error?.status === 409 || error?.code === "VERSION_CONFLICT") {
    return {
      status: 409,
      code: error.code ?? "VERSION_CONFLICT",
      message: "开通会话已被其他操作更新。请刷新后重新复核，避免覆盖最新版本。",
      requestId: error.requestId,
    };
  }
  if (error?.status === 403 || error?.code === "FORBIDDEN") {
    return {
      status: 403,
      code: error.code ?? "FORBIDDEN",
      message: "当前账号不能操作该开通会话，且未对临时企业授予任何访问权。",
      requestId: error.requestId,
    };
  }
  return {
    status: error?.status,
    code: error?.code ?? "ONBOARDING_OPERATION_FAILED",
    message: error?.message || "服务暂时无法完成此操作，请稍后重试。",
    requestId: error?.requestId,
  };
}

function OperationError({ error }: { error: PlatformOnboardingOperationError }) {
  return (
    <MessageBar intent={error.status === 409 ? "warning" : "error"}>
      <MessageBarBody>
        <strong>{error.status === 409 ? "会话版本冲突" : "操作未完成"}</strong>
        <div>{error.message}</div>
        {(error.code || error.requestId) && (
          <div className={styles.errorReference}>
            {error.code && <span>错误代码：{error.code}</span>}
            {error.requestId && <span>请求编号：{error.requestId}</span>}
          </div>
        )}
      </MessageBarBody>
    </MessageBar>
  );
}

function StartPanel({
  busy,
  onStart,
}: {
  busy: boolean;
  onStart: (input: StartPlatformOnboardingInput) => Promise<void>;
}) {
  const [input, setInput] = useState(emptyStart);
  const [attempted, setAttempted] = useState(false);
  const valid =
    slugPattern.test(input.tenantSlug) &&
    Boolean(input.adminAccount.trim()) &&
    Boolean(input.adminDisplayName.trim()) &&
    input.adminPassword.length >= 12;

  const update = <K extends keyof StartPlatformOnboardingInput>(
    key: K,
    value: StartPlatformOnboardingInput[K],
  ) => setInput((current) => ({ ...current, [key]: value }));

  return (
    <section className={styles.startPanel} aria-labelledby="onboarding-start-title">
      <div className={styles.sectionHeading}>
        <span>步骤 1 / 5</span>
        <h2 id="onboarding-start-title">填写开通基础信息</h2>
        <p>
          先填写无法从资料中安全判断的账号信息。企业确认前，管理员不能登录，名片也不会公开。
        </p>
      </div>
      <form
        className={styles.startForm}
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setAttempted(true);
          if (valid && !busy) void onStart(input);
        }}
      >
        <Field
          label="租户标识"
          required
          validationState={attempted && !slugPattern.test(input.tenantSlug) ? "error" : "none"}
          validationMessage={
            attempted && !slugPattern.test(input.tenantSlug)
              ? "使用 3–64 位小写字母、数字和连字符。"
              : undefined
          }
        >
          <Input
            value={input.tenantSlug}
            autoComplete="off"
            onChange={(_, data) => update("tenantSlug", data.value.toLowerCase())}
          />
        </Field>
        <Field label="租户名称（可稍后从建议补充）">
          <Input value={input.tenantName ?? ""} onChange={(_, data) => update("tenantName", data.value)} />
        </Field>
        <Field label="管理员账号" required>
          <Input
            value={input.adminAccount}
            autoComplete="off"
            onChange={(_, data) => update("adminAccount", data.value)}
          />
        </Field>
        <Field label="管理员姓名" required>
          <Input
            value={input.adminDisplayName}
            onChange={(_, data) => update("adminDisplayName", data.value)}
          />
        </Field>
        <Field
          label="管理员初始密码"
          required
          validationState={attempted && input.adminPassword.length < 12 ? "error" : "none"}
          validationMessage={
            attempted && input.adminPassword.length < 12 ? "初始密码至少 12 个字符。" : undefined
          }
        >
          <Input
            type="password"
            autoComplete="new-password"
            value={input.adminPassword}
            onChange={(_, data) => update("adminPassword", data.value)}
          />
        </Field>
        <div className={styles.startActions}>
          <Button appearance="primary" type="submit" disabled={busy || (attempted && !valid)}>
            {busy ? "正在准备" : "进入资料导入"}
          </Button>
        </div>
      </form>
    </section>
  );
}

function Steps({ current }: { current: number }) {
  return (
    <nav className={styles.steps} aria-label="资料辅助建企进度">
      <ol>
        {stepLabels.map((label, index) => (
          <li key={label} aria-current={current === index ? "step" : undefined}>
            <span>{index + 1}</span>
            <strong>{label}</strong>
          </li>
        ))}
      </ol>
    </nav>
  );
}

type AnalysisPhaseState = "complete" | "active" | "pending";

function AnalysisProgress({
  hasImports,
  importsProcessing,
  generating,
  hasInsights,
  insightCount,
}: {
  hasImports: boolean;
  importsProcessing: boolean;
  generating: boolean;
  hasInsights: boolean;
  insightCount: number;
}) {
  const phases: Array<{ label: string; detail: string; state: AnalysisPhaseState }> = [
    {
      label: "接收资料",
      detail: hasImports ? "资料已进入隔离导入范围" : "等待选择企业资料",
      state: hasImports ? "complete" : "pending",
    },
    {
      label: "解析内容",
      detail: importsProcessing ? "正在提取可引用的文本与表格" : hasImports ? "解析结果可供归纳" : "上传后自动开始",
      state: importsProcessing ? "active" : hasImports ? "complete" : "pending",
    },
    {
      label: "归纳业务",
      detail: generating
        ? "正在识别业务定位、产品服务、客户与资料缺口"
        : hasInsights
          ? `已形成 ${insightCount} 项带来源结论`
          : "解析完成后由你手动启动",
      state: generating ? "active" : hasInsights ? "complete" : "pending",
    },
    {
      label: "人工复核",
      detail: hasInsights ? "请核对来源、冲突和低置信内容" : "不会自动写入或发布",
      state: hasInsights ? "active" : "pending",
    },
  ];

  const active = phases.find((phase) => phase.state === "active");
  return (
    <section className={styles.analysisProgress} aria-label="资料分析进度" aria-live="polite">
      <div className={styles.analysisLead}>
        <div>
          <span>{generating || importsProcessing ? "正在处理" : hasInsights ? "分析完成，等待复核" : "分析准备"}</span>
          <strong>{active?.detail ?? (hasImports ? "资料已准备，可以开始业务归纳" : "上传后会在这里显示真实处理进度")}</strong>
        </div>
        {(generating || importsProcessing) && <i aria-hidden />}
      </div>
      <ol>
        {phases.map((phase, index) => (
          <li key={phase.label} data-state={phase.state}>
            <span aria-hidden>{phase.state === "complete" ? "✓" : index + 1}</span>
            <div><strong>{phase.label}</strong><small>{phase.detail}</small></div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function confidenceText(value?: number): string {
  if (value === undefined) return "未提供置信提示";
  if (value >= 0.8) return "高置信";
  if (value >= 0.55) return "中等置信";
  return "低置信，建议重点核对";
}

function SuggestionCard({
  suggestion,
  onApply,
  label: explicitLabel,
  readOnly = false,
}: {
  suggestion: PlatformOnboardingSuggestion;
  onApply: () => void;
  label?: string;
  readOnly?: boolean;
}) {
  const field = suggestionFieldMap[suggestion.field];
  const label = explicitLabel ?? reviewFieldMeta.find((item) => item.key === field)?.label ?? suggestion.field;
  return (
    <article className={styles.suggestionCard} aria-label={`${label}建议`}>
      <header>
        <div>
          <strong>{label}</strong>
          <span>{confidenceText(suggestion.confidence)} · 生成版本 {suggestion.generationVersion}</span>
        </div>
        {!readOnly && <Button appearance="subtle" size="small" onClick={onApply} disabled={!field}>采用建议</Button>}
      </header>
      <p className={styles.suggestionValue}>{suggestion.value}</p>
      <details>
        <summary>查看来源（{suggestion.sources.length}）</summary>
        <ul className={styles.sourceList}>
          {suggestion.sources.map((source) => (
            <li key={`${source.importItemId}-${source.documentId ?? source.fileName}`}>
              <strong>{source.fileName}</strong>
              {source.excerpt && <blockquote>{source.excerpt}</blockquote>}
              <span>导入项：{source.importItemId}</span>
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}

export function PlatformOnboardingPage({
  session,
  importItems = [],
  adminSummary,
  initialReview,
  llmAvailability,
  resourceStatus = "ready",
  resourceError,
  onStart,
  onUpload,
  onGenerate,
  onConfirm,
  onCancel,
  onRefresh,
  onStartAnother,
  onOpenEnterprises,
}: PlatformOnboardingPageProps) {
  const [busy, setBusy] = useState<BusyOperation>();
  const [operationError, setOperationError] = useState<PlatformOnboardingOperationError>();
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string>();
  const [review, setReview] = useState<ReviewValues>(emptyReview);
  const [reviewed, setReviewed] = useState({ enterprise: false, admin: false, card: false });
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const cancelOpenerRef = useRef<HTMLButtonElement>(null);
  const previousSessionId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!session || previousSessionId.current === session.id) return;
    previousSessionId.current = session.id;
    setReview({
      ...emptyReview,
      ...initialReview,
      tenantName: initialReview?.tenantName ?? session.tenantName ?? "",
    });
    setReviewed({ enterprise: false, admin: false, card: false });
    setSelectedFiles([]);
    setFileError(undefined);
    setOperationError(undefined);
  }, [initialReview, session]);

  const activeError = operationError ?? resourceError;
  const currentStep = sessionStep(session);
  const completedItems = importItems.filter((item) => item.status === "completed").length;
  const processedItems = importItems.filter((item) =>
    ["completed", "failed", "dead_letter"].includes(item.status),
  ).length;
  const importProgress = importItems.length ? processedItems / importItems.length : 0;
  const reviewValid = useMemo(
    () =>
      Boolean(
        review.tenantName.trim() &&
          review.companyName.trim() &&
          review.initialCardDisplayName.trim(),
      ),
    [review],
  );
  const confirmationReady =
    reviewValid && reviewed.enterprise && reviewed.admin && reviewed.card;
  const terminal = session && ["cancelled", "expired"].includes(session.status);
  const hasImports = importItems.length > 0 || Boolean(session?.importBatchIds.length);
  const importsProcessing =
    busy === "upload" ||
    session?.status === "processing" ||
    importItems.some((item) => ["pending", "processing"].includes(item.status));
  const insightCount = (session?.businessProfile?.length ?? 0) + (session?.suggestions.length ?? 0);
  const hasInsights = insightCount > 0;

  const run = async (operation: BusyOperation, action: () => Promise<void>) => {
    if (busy) return;
    setBusy(operation);
    setOperationError(undefined);
    try {
      await action();
    } catch (caught) {
      setOperationError(asOperationError(caught));
    } finally {
      setBusy(undefined);
    }
  };

  const updateReview = <K extends keyof ReviewValues>(key: K, value: ReviewValues[K]) => {
    setReview((current) => ({ ...current, [key]: value }));
    if (reviewFieldMeta.find((field) => field.key === key)?.group === "enterprise") {
      setReviewed((current) => ({ ...current, enterprise: false }));
    } else {
      setReviewed((current) => ({ ...current, card: false }));
    }
  };

  const chooseFiles = (files: File[]) => {
    const error = validateKnowledgeImportFiles(files);
    setFileError(error);
    setSelectedFiles(error ? [] : files);
  };

  const submitUpload = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!session) return;
    const error = validateKnowledgeImportFiles(selectedFiles);
    setFileError(error);
    if (!error) {
      void run("upload", async () => {
        await onUpload(session.id, selectedFiles);
        setSelectedFiles([]);
      });
    }
  };

  const closeCancel = () => {
    setCancelOpen(false);
    setCancelReason("");
    window.setTimeout(() => cancelOpenerRef.current?.focus(), 0);
  };

  if (resourceStatus !== "ready") {
    return (
      <main className="page-stack">
        <PageHeader
          title="资料辅助建企"
          description="复用当前资料导入链路，生成带来源建议，并由平台管理员最终确认。"
        />
        <section className="content-panel">
          <ResourceState
            status={resourceStatus}
            description={resourceError?.message}
            errorCode={resourceError?.code}
            requestId={resourceError?.requestId}
            onRetry={resourceStatus === "error" ? onRefresh : undefined}
          />
        </section>
      </main>
    );
  }

  return (
    <main className={`page-stack ${styles.page}`}>
      <PageHeader
        title="资料辅助建企"
        description="上传后可看到解析和智能分析进度；所有结论带来源，人工复核后才会激活企业。"
        actions={
          session && onRefresh ? (
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={onRefresh}>
              {session.status === "confirmed" ? "刷新结果" : "刷新进度"}
            </Button>
          ) : undefined
        }
      />

      <Steps current={currentStep} />
      {activeError && <OperationError error={activeError} />}

      {!session && (
        <StartPanel
          busy={busy === "start"}
          onStart={(input) => run("start", () => onStart(input))}
        />
      )}

      {session && session.status === "confirmed" && session.confirmedEnterprise && (
        <section className={styles.resultPanel} aria-labelledby="onboarding-result-title">
          <CheckmarkCircle24Regular aria-hidden />
          <div>
            <span>步骤 5 / 5</span>
            <h2 id="onboarding-result-title">企业已由服务端确认激活</h2>
            <p>
              {session.confirmedEnterprise.companyName}（{session.confirmedEnterprise.tenantSlug}）已生成唯一企业、管理员身份和一张未发布初始名片。
            </p>
            <dl>
              <div><dt>企业 ID</dt><dd>{session.confirmedEnterprise.companyId}</dd></div>
              <div><dt>初始名片 ID</dt><dd>{session.confirmedEnterprise.initialCardId}</dd></div>
              <div><dt>名片状态</dt><dd><StatusBadge status="draft" /></dd></div>
            </dl>
            <div className={styles.resultActions} aria-label="建企完成后操作">
              {onStartAnother && (
                <Button appearance="primary" onClick={onStartAnother}>
                  继续开通新企业
                </Button>
              )}
              {onOpenEnterprises && (
                <Button appearance="secondary" onClick={onOpenEnterprises}>
                  前往企业中心
                </Button>
              )}
            </div>
          </div>
        </section>
      )}

      {terminal && (
        <section className="content-panel">
          <ResourceState
            status="empty"
            title={session.status === "cancelled" ? "开通会话已取消" : "开通会话已过期"}
            description="该临时范围不能继续上传、生成或确认，管理员仍不可登录，名片仍不可公开。"
          />
        </section>
      )}

      {session && session.status !== "confirmed" && !terminal && (
        <>
          {llmAvailability !== "ready" && (
            <MessageBar intent="warning">
              <MessageBarBody>
                <strong>LLM 当前不可用，已切换为人工填写</strong>
                <div>
                  已成功解析的资料草稿不会回滚。你仍可查看逐文件结果并手工填写全部企业和名片字段。
                </div>
              </MessageBarBody>
            </MessageBar>
          )}

          <div className={styles.workspace}>
            <section className={styles.sourcesPanel} aria-labelledby="onboarding-sources-title">
              <div className={styles.panelHeading}>
                <div>
                  <span>步骤 2–3</span>
                  <h2 id="onboarding-sources-title">资料分析与业务归纳</h2>
                </div>
              </div>

              <AnalysisProgress
                hasImports={hasImports}
                importsProcessing={importsProcessing}
                generating={busy === "generate"}
                hasInsights={hasInsights}
                insightCount={insightCount}
              />

              <form className={styles.uploadBox} onSubmit={submitUpload}>
                <Field
                  label="选择建企资料"
                  validationState={fileError ? "error" : "none"}
                  validationMessage={fileError}
                >
                  <input
                    className={styles.fileInput}
                    aria-label="选择建企资料"
                    type="file"
                    multiple
                    accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html,.htm,.png,.jpg,.jpeg,.webp,.tiff,.bmp"
                    disabled={busy === "upload"}
                    onChange={(event) => chooseFiles(Array.from(event.target.files ?? []))}
                  />
                </Field>
                <p>
                  每批 1–5 个，单文件不超过 10 MiB、批次不超过 25 MiB。目标企业只由服务端会话推导。
                </p>
                <Button
                  appearance="primary"
                  icon={<ArrowUpload24Regular />}
                  type="submit"
                  disabled={selectedFiles.length === 0 || busy === "upload"}
                >
                  {busy === "upload" ? "正在上传" : `上传并解析${selectedFiles.length ? `（${selectedFiles.length}）` : ""}`}
                </Button>
              </form>

              {importItems.length > 0 && (
                <div className={styles.importResults} aria-label="逐文件解析结果">
                  <div className={styles.progressCopy}>
                    <strong>{processedItems}/{importItems.length} 个文件已处理</strong>
                    <span>成功草稿 {completedItems} 个</span>
                  </div>
                  <ProgressBar value={importProgress} aria-label="资料解析进度" />
                  <ul>
                    {importItems.map((item) => (
                      <li key={item.id}>
                        <div>
                          <strong>{item.fileName}</strong>
                          {item.errorMessage && <span>{item.errorMessage}</span>}
                          {item.errorCode && <code>{item.errorCode}</code>}
                        </div>
                        <StatusBadge status={item.status} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className={styles.generateBox}>
                <div>
                  <strong>智能归纳企业业务</strong>
                  <p>从已解析资料识别业务、客户、能力、方向和缺口；所有结论保留来源。</p>
                </div>
                <Button
                  appearance="secondary"
                  icon={<Sparkle24Regular />}
                  disabled={
                    (completedItems === 0 && session.importBatchIds.length === 0) ||
                    llmAvailability !== "ready" ||
                    busy === "generate"
                  }
                  onClick={() =>
                    void run("generate", () => onGenerate(session.id, session.version))
                  }
                >
                  {busy === "generate" ? "正在分析企业资料" : "开始智能分析"}
                </Button>
              </div>

              <details className={styles.technicalDetails}>
                <summary>查看处理编号</summary>
                <dl>
                  <div><dt>会话编号</dt><dd>{session.id}</dd></div>
                  <div><dt>结果版本</dt><dd>{session.version}</dd></div>
                </dl>
              </details>

              <div className={styles.suggestions} aria-live="polite">
                {(session.businessProfile?.length ?? 0) > 0 && (
                  <section className={styles.businessProfile} aria-labelledby="business-profile-title">
                    <div>
                      <span>资料归纳</span>
                      <h3 id="business-profile-title">企业业务画像（待审核）</h3>
                      <p>只整理有资料依据的业务线索；不会自动写入企业公开页、AI 知识库或名片。</p>
                    </div>
                    {session.businessProfile?.map((insight, index) => (
                      <SuggestionCard
                        key={`business-${insight.field}-${insight.generationVersion}-${index}`}
                        suggestion={insight}
                        label={businessProfileLabels[insight.field] ?? insight.field}
                        onApply={() => undefined}
                        readOnly
                      />
                    ))}
                  </section>
                )}
                {session.suggestions.length === 0 ? (
                  <div className={styles.emptySuggestions}>
                    <strong>{llmAvailability === "ready" ? "暂无建议" : "当前使用人工填写"}</strong>
                    <p>任何字段都不会因为上传或生成而自动写入右侧确认表单。</p>
                  </div>
                ) : (
                  session.suggestions.map((suggestion, index) => (
                    <SuggestionCard
                      key={`${suggestion.field}-${suggestion.generationVersion}-${index}`}
                      suggestion={suggestion}
                      onApply={() => {
                        const field = suggestionFieldMap[suggestion.field];
                        if (field) updateReview(field, suggestion.value);
                      }}
                    />
                  ))
                )}
              </div>
            </section>

            <section className={styles.reviewPanel} aria-labelledby="onboarding-review-title">
              <div className={styles.panelHeading}>
                <div>
                  <span>步骤 4 / 5</span>
                  <h2 id="onboarding-review-title">人工复核与确认</h2>
                  <p>采用建议后仍可编辑；任一字段变化都会撤销对应复核勾选。</p>
                </div>
              </div>

              <form
                className={styles.reviewForm}
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!confirmationReady) return;
                  void run("confirm", () =>
                    onConfirm(session.id, { ...review, expectedVersion: session.version }),
                  );
                }}
              >
                <fieldset>
                  <legend>企业信息</legend>
                  <div className={styles.formGrid}>
                    {reviewFieldMeta.filter((field) => field.group === "enterprise").map((field) => (
                      <Field key={field.key} label={field.label} required={field.required}>
                        {field.area ? (
                          <Textarea
                            aria-label={field.label}
                            value={review[field.key]}
                            resize="vertical"
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        ) : (
                          <Input
                            aria-label={field.label}
                            value={review[field.key]}
                            type={field.key === "website" ? "url" : "text"}
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        )}
                      </Field>
                    ))}
                  </div>
                </fieldset>

                <fieldset>
                  <legend>管理员交付</legend>
                  <dl className={styles.adminSummary}>
                    <div><dt>管理员账号</dt><dd>{adminSummary?.account ?? "由初始化步骤锁定"}</dd></div>
                    <div><dt>管理员姓名</dt><dd>{adminSummary?.displayName ?? "由初始化步骤锁定"}</dd></div>
                    <div><dt>确认前状态</dt><dd>不可登录</dd></div>
                  </dl>
                </fieldset>

                <fieldset>
                  <legend>初始草稿名片</legend>
                  <div className={styles.formGrid}>
                    {reviewFieldMeta.filter((field) => field.group === "card").map((field) => (
                      <Field key={field.key} label={field.label} required={field.required}>
                        {field.area ? (
                          <Textarea
                            aria-label={field.label}
                            value={review[field.key]}
                            resize="vertical"
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        ) : (
                          <Input
                            aria-label={field.label}
                            value={review[field.key]}
                            onChange={(_, data) => updateReview(field.key, data.value)}
                          />
                        )}
                      </Field>
                    ))}
                  </div>
                  <p className={styles.draftNote}>初始名片只创建为草稿，不会自动发布或生成公开链接。</p>
                </fieldset>

                <fieldset className={styles.confirmationGate}>
                  <legend>显式确认门</legend>
                  <Checkbox
                    checked={reviewed.enterprise}
                    onChange={(_, data) =>
                      setReviewed((current) => ({ ...current, enterprise: data.checked === true }))
                    }
                    label="我已逐项复核企业信息"
                  />
                  <Checkbox
                    checked={reviewed.admin}
                    onChange={(_, data) =>
                      setReviewed((current) => ({ ...current, admin: data.checked === true }))
                    }
                    label="我已核对管理员账号与交付对象"
                  />
                  <Checkbox
                    checked={reviewed.card}
                    onChange={(_, data) =>
                      setReviewed((current) => ({ ...current, card: data.checked === true }))
                    }
                    label="我已核对初始名片，并确认保持草稿"
                  />
                </fieldset>

                <div className={styles.stickyActions} aria-label="开通会话主操作">
                  <div>
                    <strong>{confirmationReady ? "可以提交确认" : "尚未满足确认条件"}</strong>
                    <span>将提交服务端会话版本 {session.version}</span>
                  </div>
                  <Button
                    ref={cancelOpenerRef}
                    appearance="subtle"
                    icon={<Dismiss24Regular />}
                    type="button"
                    onClick={() => setCancelOpen(true)}
                  >
                    取消会话
                  </Button>
                  <Button appearance="primary" type="submit" disabled={!confirmationReady || busy === "confirm"}>
                    {busy === "confirm" ? "正在确认" : "确认并激活企业"}
                  </Button>
                </div>
              </form>
            </section>
          </div>

          <Dialog
            open={cancelOpen}
            onOpenChange={(_, data) => {
              if (!data.open && busy !== "cancel") closeCancel();
            }}
          >
            <DialogSurface>
              <DialogBody>
                <DialogTitle>取消资料辅助建企会话</DialogTitle>
                <DialogContent>
                  <p>取消是软锁定，不会激活临时企业，也不会删除审计记录。请填写原因。</p>
                  <Field label="取消原因" required>
                    <Textarea
                      aria-label="取消原因"
                      value={cancelReason}
                      resize="vertical"
                      onChange={(_, data) => setCancelReason(data.value)}
                    />
                  </Field>
                </DialogContent>
                <DialogActions>
                  <Button appearance="secondary" disabled={busy === "cancel"} onClick={closeCancel}>
                    返回复核
                  </Button>
                  <Button
                    appearance="primary"
                    disabled={!cancelReason.trim() || busy === "cancel"}
                    onClick={() =>
                      void run("cancel", async () => {
                        await onCancel(session.id, cancelReason.trim(), session.version);
                        closeCancel();
                      })
                    }
                  >
                    {busy === "cancel" ? "正在取消" : "确认取消会话"}
                  </Button>
                </DialogActions>
              </DialogBody>
            </DialogSurface>
          </Dialog>
        </>
      )}
    </main>
  );
}
