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
  Select,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
} from "@fluentui/react-components";
import {
  Add24Regular,
  Dismiss24Regular,
  Search24Regular,
} from "@fluentui/react-icons";
import { type FormEvent, useRef, useState } from "react";

import { ApiError } from "../api/client";
import { platformApi } from "../api/platformApi";
import type { CreatePlatformEnterpriseInput } from "../api/types";
import { FormFeedback } from "../components/FormFeedback";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { StatusBadge } from "../components/StatusBadge";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";
import { PlatformEnterpriseDrawer } from "./PlatformEnterpriseDrawer";
import styles from "./PlatformEnterpriseDrawer.module.css";

const emptyInput: CreatePlatformEnterpriseInput = {
  tenantSlug: "",
  tenantName: "",
  companyName: "",
  industry: "",
  adminAccount: "",
  adminDisplayName: "",
  adminPassword: "",
  initialCardTitle: "",
};

const slugPattern = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

function toApiError(value: unknown): ApiError {
  return value instanceof ApiError
    ? value
    : new ApiError("创建企业时发生未知错误。", { code: "UNKNOWN_ERROR" });
}

export function PlatformEnterprisesPage() {
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "" | "active" | "suspended" | "disabled"
  >("");
  const [selectedCompanyId, setSelectedCompanyId] = useState<string>();
  const detailTriggerRef = useRef<HTMLButtonElement>(null);
  const resource = useResource(
    () =>
      platformApi.listEnterprises({
        search: search || undefined,
        status: statusFilter || undefined,
        limit: 100,
      }),
    `${search}:${statusFilter}`,
  );
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState(emptyInput);
  const [attempted, setAttempted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<ApiError>();
  const [notice, setNotice] = useState<string>();
  const valid =
    slugPattern.test(input.tenantSlug) &&
    Boolean(input.tenantName.trim()) &&
    Boolean(input.companyName.trim()) &&
    Boolean(input.adminAccount.trim()) &&
    Boolean(input.adminDisplayName.trim()) &&
    input.adminPassword.length >= 12;

  const update = <K extends keyof CreatePlatformEnterpriseInput>(
    field: K,
    value: CreatePlatformEnterpriseInput[K],
  ) => setInput((current) => ({ ...current, [field]: value }));

  const showCreate = () => {
    setInput(emptyInput);
    setAttempted(false);
    setError(undefined);
    setOpen(true);
  };

  const applyFilters = () => {
    const next = searchDraft.trim();
    if (next === search) resource.reload();
    setSearch(next);
  };

  const showDetail = (companyId: string, trigger: HTMLButtonElement) => {
    detailTriggerRef.current = trigger;
    setSelectedCompanyId(companyId);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    setError(undefined);
    if (!valid || saving) return;
    setSaving(true);
    try {
      const created = await platformApi.createEnterprise(input);
      setNotice(
        `企业 ${created.companyName} 已开通，初始名片标识为 ${created.initialCardSlug}。`,
      );
      setInput(emptyInput);
      setOpen(false);
      resource.reload();
    } catch (caught) {
      setError(toApiError(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="page-stack">
      <PageHeader
        title="企业中心"
        description="检索已确认企业，查看入驻进度、运营聚合与每张名片的发布状态。"
        actions={
          resource.status === "permission" ? undefined : (
            <Button appearance="primary" icon={<Add24Regular />} onClick={showCreate}>
              开通企业
            </Button>
          )
        }
      />

      {notice && (
        <MessageBar intent="success">
          <MessageBarBody>{notice}</MessageBarBody>
        </MessageBar>
      )}

      <section className="content-panel filter-panel" aria-label="企业筛选">
        <Select
          aria-label="企业状态"
          value={statusFilter}
          onChange={(_, data) =>
            setStatusFilter(
              data.value as "" | "active" | "suspended" | "disabled",
            )
          }
        >
          <option value="">全部状态</option>
          <option value="active">正常运营</option>
          <option value="suspended">已暂停</option>
          <option value="disabled">已停用</option>
        </Select>
        <Input
          aria-label="搜索企业"
          placeholder="企业名称、租户名称或标识"
          value={searchDraft}
          onChange={(_, data) => setSearchDraft(data.value)}
          onKeyDown={(event) => event.key === "Enter" && applyFilters()}
        />
        <Button icon={<Search24Regular />} onClick={applyFilters}>
          搜索
        </Button>
        {(search || statusFilter) && (
          <Button
            appearance="subtle"
            icon={<Dismiss24Regular />}
            onClick={() => {
              setSearchDraft("");
              setSearch("");
              setStatusFilter("");
            }}
          >
            清除
          </Button>
        )}
      </section>

      <section className="content-panel catalog-panel">
        {resource.status !== "ready" && (
          <ResourceState
            status={resource.status}
            title={
              resource.status === "empty"
                ? search || statusFilter
                  ? "没有符合条件的企业"
                  : "尚未开通企业"
                : undefined
            }
            description={
              resource.status === "empty"
                ? search || statusFilter
                  ? "调整关键词或状态后重新搜索。"
                  : "开通后，企业管理员可登录并维护自己的资料和名片。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button appearance="primary" icon={<Add24Regular />} onClick={showCreate}>
                开通第一家企业
              </Button>
            }
          />
        )}

        {resource.status === "ready" && resource.data && (
          <div className={`table-scroll ${styles.desktopTable}`}>
            <Table aria-label="平台企业列表" size="small">
              <TableHeader>
                <TableRow>
                  <TableHeaderCell>租户</TableHeaderCell>
                  <TableHeaderCell>企业</TableHeaderCell>
                  <TableHeaderCell>状态</TableHeaderCell>
                  <TableHeaderCell>开通时间</TableHeaderCell>
                  <TableHeaderCell>操作</TableHeaderCell>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resource.data.map((item) => (
                  <TableRow key={item.companyId}>
                    <TableCell>
                      <strong>{item.tenantName}</strong>
                      <div className="cell-secondary">{item.tenantSlug}</div>
                    </TableCell>
                    <TableCell>{item.companyName}</TableCell>
                    <TableCell>
                      <StatusBadge status={item.status} />
                    </TableCell>
                    <TableCell>{formatTimestamp(item.createdAt)}</TableCell>
                    <TableCell>
                      <Button
                        appearance="subtle"
                        size="small"
                        onClick={(event) =>
                          showDetail(item.companyId, event.currentTarget)
                        }
                      >
                        查看详情
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {resource.status === "ready" && resource.data && (
          <div className={styles.mobileRecords} aria-label="平台企业列表">
            {resource.data.map((item) => (
              <article className={styles.recordCard} key={item.companyId}>
                <div className={styles.recordHeader}>
                  <strong>{item.companyName}</strong>
                  <StatusBadge status={item.status} />
                </div>
                <p>
                  {item.tenantName} · {item.tenantSlug}
                </p>
                <div className={styles.recordActions}>
                  <span className="cell-secondary">
                    {formatTimestamp(item.createdAt)}
                  </span>
                  <Button
                    appearance="secondary"
                    size="small"
                    onClick={(event) =>
                      showDetail(item.companyId, event.currentTarget)
                    }
                  >
                    查看详情
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <Dialog
        open={open}
        onOpenChange={(_, data) => {
          if (!data.open && !saving) setOpen(false);
        }}
      >
        <DialogSurface>
          <form onSubmit={submit} noValidate>
            <DialogBody>
              <DialogTitle>开通隔离企业</DialogTitle>
              <DialogContent className="catalog-editor-form">
                <FormFeedback error={error} />
                <div className="form-grid two-column">
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
                      onChange={(_, data) => update("tenantSlug", data.value.toLowerCase())}
                      autoComplete="off"
                    />
                  </Field>
                  <Field label="租户名称" required>
                    <Input
                      value={input.tenantName}
                      onChange={(_, data) => update("tenantName", data.value)}
                    />
                  </Field>
                  <Field label="企业名称" required>
                    <Input
                      value={input.companyName}
                      onChange={(_, data) => update("companyName", data.value)}
                    />
                  </Field>
                  <Field label="行业">
                    <Input
                      value={input.industry}
                      onChange={(_, data) => update("industry", data.value)}
                    />
                  </Field>
                  <Field label="管理员账号" required>
                    <Input
                      value={input.adminAccount}
                      onChange={(_, data) => update("adminAccount", data.value)}
                      autoComplete="off"
                    />
                  </Field>
                  <Field label="管理员姓名" required>
                    <Input
                      value={input.adminDisplayName}
                      onChange={(_, data) => update("adminDisplayName", data.value)}
                    />
                  </Field>
                  <Field
                    label="初始密码"
                    required
                    validationState={attempted && input.adminPassword.length < 12 ? "error" : "none"}
                    validationMessage={
                      attempted && input.adminPassword.length < 12
                        ? "初始密码至少 12 个字符，并通过安全渠道交付。"
                        : undefined
                    }
                  >
                    <Input
                      type="password"
                      value={input.adminPassword}
                      onChange={(_, data) => update("adminPassword", data.value)}
                      autoComplete="new-password"
                    />
                  </Field>
                  <Field label="初始名片标题">
                    <Input
                      value={input.initialCardTitle}
                      onChange={(_, data) => update("initialCardTitle", data.value)}
                    />
                  </Field>
                </div>
              </DialogContent>
              <DialogActions>
                <Button appearance="secondary" onClick={() => setOpen(false)} disabled={saving}>
                  取消
                </Button>
                <Button appearance="primary" type="submit" disabled={saving || (attempted && !valid)}>
                  {saving ? "正在开通" : "确认开通"}
                </Button>
              </DialogActions>
            </DialogBody>
          </form>
        </DialogSurface>
      </Dialog>

      {selectedCompanyId && (
        <PlatformEnterpriseDrawer
          companyId={selectedCompanyId}
          returnFocusRef={detailTriggerRef}
          onChanged={resource.reload}
          onClose={() => setSelectedCompanyId(undefined)}
        />
      )}
    </main>
  );
}
