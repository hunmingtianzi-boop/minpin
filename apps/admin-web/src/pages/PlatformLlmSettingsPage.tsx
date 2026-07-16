import { useEffect, useId, useRef, useState } from "react";

import styles from "./PlatformLlmSettingsPage.module.css";

export type PlatformLlmReadinessStatus =
  | "unconfigured"
  | "partial"
  | "ready"
  | "failed";

export type PlatformLlmCapabilityStatus =
  | "unconfigured"
  | "ready"
  | "failed"
  | "disabled";

export interface PlatformLlmCapabilityReadiness {
  id: string;
  label: string;
  status: PlatformLlmCapabilityStatus;
  profileName?: string;
  detail?: string;
}

export interface PlatformLlmReadiness {
  status: PlatformLlmReadinessStatus;
  message?: string;
  capabilities: PlatformLlmCapabilityReadiness[];
}

export interface PlatformLlmCurrentConfig {
  source: "database" | "environment" | "unconfigured";
  profileId?: string;
  profileName?: string;
  provider?: string;
  model?: string;
  baseUrl?: string;
  keyConfigured?: boolean;
  updatedAt?: string;
}

export interface PlatformLlmProfile {
  id: string;
  name: string;
  provider: string;
  model: string;
  baseUrl: string;
  keyConfigured: boolean;
  keyHint?: string;
  enabled: boolean;
  thinkingMode?: "disabled" | "enabled";
  reasoningEffort?: "high" | "max";
  timeoutSeconds?: number;
  maxRetries?: number;
  dailyBudgetCny?: number;
  updatedAt?: string;
  version?: number;
}

export interface PlatformLlmProfileInput {
  name: string;
  provider: string;
  model: string;
  baseUrl: string;
  apiKey: string;
  enabled: boolean;
  thinkingMode: "disabled" | "enabled";
  reasoningEffort: "high" | "max";
  timeoutSeconds: number;
  maxRetries: number;
  dailyBudgetCny: number;
}

export interface PlatformLlmConnectionResult {
  ok: boolean;
  provider?: string;
  model?: string;
  latencyMs?: number;
  errorCode?: string;
  message?: string;
}

export interface PlatformLlmSettingsPageProps {
  profiles: PlatformLlmProfile[];
  current?: PlatformLlmCurrentConfig | null;
  readiness: PlatformLlmReadiness;
  loading?: boolean;
  onSave: (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ) => Promise<void>;
  onTest: (
    input: PlatformLlmProfileInput,
    profile?: PlatformLlmProfile,
  ) => Promise<PlatformLlmConnectionResult>;
  onActivate: (profile: PlatformLlmProfile) => Promise<void>;
  onRefresh?: () => void;
}

type EditorState = {
  profile?: PlatformLlmProfile;
  form: PlatformLlmProfileInput;
};

type Feedback = {
  tone: "success" | "warning" | "error";
  title: string;
  message: string;
  code?: string;
};

const emptyForm: PlatformLlmProfileInput = {
  name: "",
  provider: "deepseek",
  model: "",
  baseUrl: "https://api.deepseek.com",
  apiKey: "",
  enabled: true,
  thinkingMode: "disabled",
  reasoningEffort: "high",
  timeoutSeconds: 30,
  maxRetries: 2,
  dailyBudgetCny: 100,
};

const readinessCopy: Record<
  PlatformLlmReadinessStatus,
  { label: string; description: string }
> = {
  unconfigured: {
    label: "未配置",
    description: "先保存并测试一条配置，再将其设为当前主配置。",
  },
  partial: {
    label: "部分就绪",
    description: "仍有能力没有可用配置，请逐项检查。",
  },
  ready: {
    label: "运行就绪",
    description: "当前能力均已有明确、可用的配置来源。",
  },
  failed: {
    label: "运行异常",
    description: "至少一项能力连接失败，请修复后重新测试。",
  },
};

const capabilityCopy: Record<PlatformLlmCapabilityStatus, string> = {
  unconfigured: "未配置",
  ready: "已就绪",
  failed: "异常",
  disabled: "已停用",
};

function profileToForm(profile: PlatformLlmProfile): PlatformLlmProfileInput {
  return {
    name: profile.name,
    provider: profile.provider,
    model: profile.model,
    baseUrl: profile.baseUrl,
    apiKey: "",
    enabled: profile.enabled,
    thinkingMode: profile.thinkingMode ?? "disabled",
    reasoningEffort: profile.reasoningEffort ?? "high",
    timeoutSeconds: profile.timeoutSeconds ?? 30,
    maxRetries: profile.maxRetries ?? 2,
    dailyBudgetCny: profile.dailyBudgetCny ?? 100,
  };
}

function isValidForm(form: PlatformLlmProfileInput): boolean {
  return Boolean(
    form.name.trim() &&
      form.provider.trim() &&
      form.model.trim() &&
      form.baseUrl.trim() &&
      Number.isFinite(form.timeoutSeconds) &&
      form.timeoutSeconds >= 2 &&
      form.timeoutSeconds <= 120 &&
      Number.isFinite(form.maxRetries) &&
      form.maxRetries >= 0 &&
      form.maxRetries <= 5 &&
      Number.isFinite(form.dailyBudgetCny) &&
      form.dailyBudgetCny > 0,
  );
}

function sourceLabel(source: PlatformLlmCurrentConfig["source"]): string {
  if (source === "database") return "平台配置";
  if (source === "environment") return "环境变量";
  return "未配置";
}

function formatUpdatedAt(value?: string): string {
  if (!value) return "未提供";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function operationError(caught: unknown): Feedback {
  const value = caught as {
    status?: number;
    code?: string;
    message?: string;
  };
  const status = value?.status;
  const code = value?.code;
  if (status === 403 || code === "HTTP_403" || code === "FORBIDDEN") {
    return {
      tone: "error",
      title: "没有配置权限",
      message: "当前账号不能管理平台 LLM 配置，请联系平台管理员。",
      code: code ?? "HTTP_403",
    };
  }
  if (status === 409 || code === "HTTP_409" || code === "VERSION_CONFLICT") {
    return {
      tone: "warning",
      title: "配置已发生变化",
      message: "其他操作已更新这条配置。请刷新后重新编辑，避免覆盖新版本。",
      code: code ?? "HTTP_409",
    };
  }
  return {
    tone: "error",
    title: "操作未完成",
    message: value?.message || "服务暂时无法完成请求，请稍后重试。",
    code,
  };
}

function connectionFeedback(result: PlatformLlmConnectionResult): Feedback {
  if (result.ok) {
    const latency = result.latencyMs === undefined ? "" : `，${result.latencyMs} ms`;
    return {
      tone: "success",
      title: "连接测试通过",
      message: `${result.provider || "Provider"} / ${result.model || "模型"}${latency}。`,
    };
  }
  return {
    tone: "warning",
    title: "连接测试未通过",
    message: result.message || "请检查地址、模型名称、密钥和网络后重试。",
    code: result.errorCode,
  };
}

function FeedbackBanner({ feedback }: { feedback: Feedback }) {
  return (
    <div
      className={`${styles.feedback} ${styles[feedback.tone]}`}
      role={feedback.tone === "success" ? "status" : "alert"}
    >
      <strong>{feedback.title}</strong>
      <span>{feedback.message}</span>
      {feedback.code && <code>错误码：{feedback.code}</code>}
    </div>
  );
}

function ProfileEditor({
  state,
  saving,
  testing,
  feedback,
  onChange,
  onSave,
  onTest,
  onClose,
}: {
  state: EditorState;
  saving: boolean;
  testing: boolean;
  feedback?: Feedback;
  onChange: (form: PlatformLlmProfileInput) => void;
  onSave: () => void;
  onTest: () => void;
  onClose: () => void;
}) {
  const titleId = useId();
  const drawerRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);
  const editing = Boolean(state.profile);
  const keyRequired = editing ? !state.profile?.keyConfigured : state.form.enabled;
  const valid = isValidForm(state.form) && (!keyRequired || Boolean(state.form.apiKey.trim()));
  const testValid =
    isValidForm(state.form) &&
    Boolean(state.form.apiKey.trim() || state.profile?.keyConfigured);

  useEffect(() => {
    firstInputRef.current?.focus();
  }, []);

  const update = <K extends keyof PlatformLlmProfileInput>(
    key: K,
    value: PlatformLlmProfileInput[K],
  ) => onChange({ ...state.form, [key]: value });

  const handleKeys = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && !saving && !testing) {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      drawerRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), select:not([disabled]), summary, [href]',
      ) ?? [],
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className={styles.backdrop} onMouseDown={(event) => {
      if (event.target === event.currentTarget && !saving && !testing) onClose();
    }}>
      <div
        ref={drawerRef}
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={handleKeys}
      >
        <header className={styles.drawerHeader}>
          <div>
            <span className={styles.eyebrow}>平台模型配置</span>
            <h2 id={titleId}>{editing ? "编辑配置" : "新建配置"}</h2>
          </div>
          <button
            type="button"
            className={styles.iconButton}
            aria-label="关闭配置面板"
            disabled={saving || testing}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <form
          className={styles.form}
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            onSave();
          }}
        >
          <p className={styles.secretNote}>
            API Key 只写入、不回显。{editing ? "留空会保留已有密钥。" : "保存后输入框会立即清空。"}
          </p>
          {feedback && <FeedbackBanner feedback={feedback} />}

          <div className={styles.formGrid}>
            <label>
              <span>配置名称</span>
              <input
                ref={firstInputRef}
                aria-label="配置名称"
                required
                value={state.form.name}
                onChange={(event) => update("name", event.target.value)}
                placeholder="例如：DeepSeek 主模型"
              />
            </label>
            <label>
              <span>Provider</span>
              <select
                aria-label="Provider"
                value={state.form.provider}
                onChange={(event) => update("provider", event.target.value)}
              >
                <option value="deepseek">DeepSeek（OpenAI Compatible）</option>
                <option value="openai_compatible">OpenAI Compatible</option>
                <option value="openai">OpenAI</option>
              </select>
            </label>
            <label>
              <span>模型</span>
              <input
                aria-label="模型"
                required
                value={state.form.model}
                onChange={(event) => update("model", event.target.value)}
                placeholder="模型标识"
              />
            </label>
            <label>
              <span>Base URL</span>
              <input
                aria-label="Base URL"
                required
                type="url"
                value={state.form.baseUrl}
                onChange={(event) => update("baseUrl", event.target.value)}
                placeholder="https://api.example.com/v1"
              />
              <small>只填写服务根地址，不要包含密钥、query 或 fragment。</small>
            </label>
            <label className={styles.fullWidth}>
              <span>{editing ? "API Key（留空保留）" : "API Key"}</span>
              <input
                aria-label={editing ? "API Key（留空保留）" : "API Key"}
                type="password"
                autoComplete="new-password"
                value={state.form.apiKey}
                onChange={(event) => update("apiKey", event.target.value)}
                placeholder={editing ? "输入新密钥才会替换" : "输入此配置的密钥"}
              />
              {editing && state.profile?.keyConfigured && (
                <small>当前已配置{state.profile.keyHint ? `（${state.profile.keyHint}）` : ""}</small>
              )}
            </label>
          </div>

          <details className={styles.advanced}>
            <summary>高级运行参数</summary>
            <div className={styles.formGrid}>
              <label>
                <span>Thinking Mode</span>
                <select
                  aria-label="Thinking Mode"
                  value={state.form.thinkingMode}
                  onChange={(event) =>
                    update(
                      "thinkingMode",
                      event.target.value === "enabled" ? "enabled" : "disabled",
                    )
                  }
                >
                  <option value="disabled">关闭</option>
                  <option value="enabled">开启</option>
                </select>
              </label>
              <label>
                <span>Reasoning Effort</span>
                <select
                  aria-label="Reasoning Effort"
                  disabled={state.form.thinkingMode !== "enabled"}
                  value={state.form.reasoningEffort}
                  onChange={(event) =>
                    update("reasoningEffort", event.target.value === "max" ? "max" : "high")
                  }
                >
                  <option value="high">High</option>
                  <option value="max">Max</option>
                </select>
              </label>
              <label>
                <span>超时（秒）</span>
                <input
                  aria-label="超时（秒）"
                  type="number"
                  min={2}
                  max={120}
                  value={state.form.timeoutSeconds}
                  onChange={(event) => update("timeoutSeconds", Number(event.target.value))}
                />
              </label>
              <label>
                <span>最大重试次数</span>
                <input
                  aria-label="最大重试次数"
                  type="number"
                  min={0}
                  max={5}
                  value={state.form.maxRetries}
                  onChange={(event) => update("maxRetries", Number(event.target.value))}
                />
              </label>
              <label>
                <span>每日预算（元）</span>
                <input
                  aria-label="每日预算（元）"
                  type="number"
                  min={0.01}
                  step={1}
                  value={state.form.dailyBudgetCny}
                  onChange={(event) => update("dailyBudgetCny", Number(event.target.value))}
                />
              </label>
              <label className={styles.switchLabel}>
                <input
                  aria-label="保存后启用此配置"
                  type="checkbox"
                  checked={state.form.enabled}
                  onChange={(event) => update("enabled", event.target.checked)}
                />
                <span>保存后启用此配置</span>
              </label>
            </div>
          </details>

          <footer className={styles.drawerActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={!testValid || testing}
              onClick={onTest}
            >
              {testing ? "正在测试" : "测试当前填写值"}
            </button>
            <button
              type="submit"
              className={styles.primaryButton}
              disabled={!valid || saving}
            >
              {saving ? "正在保存" : "保存配置"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}

export function PlatformLlmSettingsPage({
  profiles,
  current,
  readiness,
  loading = false,
  onSave,
  onTest,
  onActivate,
  onRefresh,
}: PlatformLlmSettingsPageProps) {
  const [editor, setEditor] = useState<EditorState>();
  const [saving, setSaving] = useState(false);
  const [testingTarget, setTestingTarget] = useState<string>();
  const [activatingId, setActivatingId] = useState<string>();
  const [feedback, setFeedback] = useState<Feedback>();
  const [editorFeedback, setEditorFeedback] = useState<Feedback>();
  const openerRef = useRef<HTMLElement | null>(null);
  const readinessText = readinessCopy[readiness.status];

  const openEditor = (profile: PlatformLlmProfile | undefined, opener: HTMLElement) => {
    openerRef.current = opener;
    setEditor({
      profile,
      form: profile ? profileToForm(profile) : { ...emptyForm },
    });
    setEditorFeedback(undefined);
  };

  const closeEditor = () => {
    setEditor(undefined);
    setEditorFeedback(undefined);
    window.setTimeout(() => openerRef.current?.focus(), 0);
  };

  const saveEditor = async () => {
    if (!editor || saving) return;
    setSaving(true);
    setEditorFeedback(undefined);
    try {
      await onSave({ ...editor.form }, editor.profile);
      setEditor((currentEditor) =>
        currentEditor
          ? { ...currentEditor, form: { ...currentEditor.form, apiKey: "" } }
          : currentEditor,
      );
      setFeedback({
        tone: "success",
        title: "配置已保存",
        message: "密钥输入已清空。请测试通过后再激活为当前主配置。",
      });
      closeEditor();
    } catch (caught) {
      setEditorFeedback(operationError(caught));
    } finally {
      setSaving(false);
    }
  };

  const testEditor = async () => {
    if (!editor || testingTarget) return;
    setTestingTarget("editor");
    setEditorFeedback(undefined);
    try {
      setEditorFeedback(connectionFeedback(await onTest({ ...editor.form }, editor.profile)));
    } catch (caught) {
      setEditorFeedback(operationError(caught));
    } finally {
      setTestingTarget(undefined);
    }
  };

  const testProfile = async (profile: PlatformLlmProfile) => {
    if (testingTarget) return;
    setTestingTarget(profile.id);
    setFeedback(undefined);
    try {
      setFeedback(connectionFeedback(await onTest(profileToForm(profile), profile)));
    } catch (caught) {
      setFeedback(operationError(caught));
    } finally {
      setTestingTarget(undefined);
    }
  };

  const activateProfile = async (profile: PlatformLlmProfile) => {
    if (activatingId) return;
    setActivatingId(profile.id);
    setFeedback(undefined);
    try {
      await onActivate(profile);
      setFeedback({
        tone: "success",
        title: "主配置已切换",
        message: `后续名片问答将使用“${profile.name}”。`,
      });
    } catch (caught) {
      setFeedback(operationError(caught));
    } finally {
      setActivatingId(undefined);
    }
  };

  return (
    <main className={styles.page} aria-busy={loading}>
      <header className={styles.pageHeader}>
        <div>
          <span className={styles.eyebrow}>平台设置</span>
          <h1>LLM API 配置</h1>
          <p>先确认运行能力，再管理模型配置。保存、连接测试与激活互不混淆。</p>
        </div>
        <div className={styles.headerActions}>
          {onRefresh && (
            <button type="button" className={styles.ghostButton} onClick={onRefresh}>
              刷新
            </button>
          )}
          <button
            type="button"
            className={styles.primaryButton}
            onClick={(event) => openEditor(undefined, event.currentTarget)}
          >
            新建配置
          </button>
        </div>
      </header>

      {feedback && <FeedbackBanner feedback={feedback} />}

      <section className={styles.readinessPanel} aria-labelledby="llm-readiness-title">
        <div className={styles.readinessSummary}>
          <span
            className={`${styles.statusBadge} ${styles[`readiness_${readiness.status}`]}`}
          >
            {readinessText.label}
          </span>
          <div>
            <h2 id="llm-readiness-title">能力就绪情况</h2>
            <p>{readiness.message || readinessText.description}</p>
          </div>
        </div>
        <ul className={styles.capabilityList}>
          {readiness.capabilities.map((capability) => (
            <li key={capability.id}>
              <div>
                <strong>{capability.label}</strong>
                <span>{capability.profileName || "尚未绑定配置"}</span>
              </div>
              <span
                className={`${styles.capabilityStatus} ${styles[`capability_${capability.status}`]}`}
              >
                {capabilityCopy[capability.status]}
              </span>
              {capability.detail && <small>{capability.detail}</small>}
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.currentPanel} aria-labelledby="llm-current-title">
        <div>
          <span className={styles.sectionLabel}>当前运行配置</span>
          <h2 id="llm-current-title">
            {current?.profileName || (current?.source === "environment" ? "环境变量配置" : "尚未激活")}
          </h2>
          <p>
            {current?.provider && current?.model
              ? `${current.provider} / ${current.model}`
              : "保存并测试配置后，将其设为主配置。"}
          </p>
        </div>
        <dl className={styles.currentFacts}>
          <div><dt>来源</dt><dd>{sourceLabel(current?.source ?? "unconfigured")}</dd></div>
          <div><dt>密钥</dt><dd>{current?.keyConfigured ? "已配置（不回显）" : "未配置"}</dd></div>
          <div><dt>更新时间</dt><dd>{formatUpdatedAt(current?.updatedAt)}</dd></div>
        </dl>
        {current?.baseUrl && <code className={styles.endpoint}>{current.baseUrl}</code>}
      </section>

      <section className={styles.profilesPanel} aria-labelledby="llm-profiles-title">
        <div className={styles.sectionHeading}>
          <div>
            <span className={styles.sectionLabel}>配置档案</span>
            <h2 id="llm-profiles-title">已保存配置</h2>
          </div>
          <span>{profiles.length} 条</span>
        </div>

        {loading ? (
          <p className={styles.emptyState}>正在读取平台配置…</p>
        ) : profiles.length === 0 ? (
          <div className={styles.emptyState}>
            <strong>还没有可用配置</strong>
            <span>新建第一条配置，完成连接测试后再激活。</span>
          </div>
        ) : (
          <ul className={styles.profileList}>
            {profiles.map((profile) => {
              const active = current?.profileId === profile.id;
              return (
                <li key={profile.id} className={active ? styles.activeProfile : undefined}>
                  <div className={styles.profileSummary}>
                    <div className={styles.profileTitle}>
                      <strong>{profile.name}</strong>
                      {active && <span className={styles.currentBadge}>当前主配置</span>}
                      {!profile.enabled && <span className={styles.disabledBadge}>已停用</span>}
                    </div>
                    <span>{profile.provider} / {profile.model}</span>
                    <code>{profile.baseUrl}</code>
                    <small>
                      密钥：{profile.keyConfigured ? `已配置${profile.keyHint ? `（${profile.keyHint}）` : ""}` : "未配置"}
                      {profile.updatedAt ? ` · 更新于 ${formatUpdatedAt(profile.updatedAt)}` : ""}
                    </small>
                  </div>
                  <div className={styles.profileActions}>
                    <button
                      type="button"
                      className={styles.ghostButton}
                      onClick={(event) => openEditor(profile, event.currentTarget)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      disabled={!profile.keyConfigured || testingTarget === profile.id}
                      onClick={() => void testProfile(profile)}
                    >
                      {testingTarget === profile.id ? "正在测试" : "测试"}
                    </button>
                    <button
                      type="button"
                      className={styles.primaryButton}
                      disabled={active || !profile.enabled || !profile.keyConfigured || activatingId === profile.id}
                      onClick={() => void activateProfile(profile)}
                    >
                      {activatingId === profile.id ? "正在激活" : active ? "已激活" : "设为主配置"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {editor && (
        <ProfileEditor
          state={editor}
          saving={saving}
          testing={testingTarget === "editor"}
          feedback={editorFeedback}
          onChange={(form) => {
            setEditor((currentEditor) => currentEditor ? { ...currentEditor, form } : currentEditor);
            setEditorFeedback(undefined);
          }}
          onSave={() => void saveEditor()}
          onTest={() => void testEditor()}
          onClose={closeEditor}
        />
      )}
    </main>
  );
}
