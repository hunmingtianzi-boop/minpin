import { Badge, Button } from "@fluentui/react-components";
import { Add24Regular, ArrowClockwise24Regular, Building24Regular } from "@fluentui/react-icons";

import { platformApi } from "../api/platformApi";
import { navigate, APP_PATHS } from "../routing";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

export function PlatformOverviewPage() {
  const resource = useResource(() => platformApi.listEnterprises());
  const enterprises = resource.data ?? [];
  const active = enterprises.filter((item) => item.status === "active").length;
  const latest = [...enterprises].sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0];

  return (
    <main className="page-stack platform-console">
      <PageHeader
        title="平台运营中心"
        description="统一开通企业、掌握入驻状态，并保持企业经营数据在各自租户内隔离。"
        actions={
          <>
            <Button appearance="subtle" icon={<ArrowClockwise24Regular />} onClick={resource.reload}>
              刷新状态
            </Button>
            <Button appearance="primary" icon={<Add24Regular />} onClick={() => navigate(APP_PATHS.platformEnterprises)}>
              开通企业
            </Button>
          </>
        }
      />

      {resource.status === "ready" ? (
        <>
          <section className="platform-status-grid" aria-label="平台企业概览">
            <article className="platform-status-primary">
              <span>已开通企业</span>
              <strong>{enterprises.length}</strong>
              <p>企业管理员可独立维护名片、内容与知识库。</p>
            </article>
            <article className="platform-status-item">
              <span>正常运营</span>
              <strong>{active}</strong>
              <p>状态由企业开通记录提供。</p>
            </article>
            <article className="platform-status-item">
              <span>最近开通</span>
              <strong>{latest ? latest.companyName : "暂无"}</strong>
              <p>{latest ? formatTimestamp(latest.createdAt) : "先开通第一家企业"}</p>
            </article>
          </section>

          <section className="platform-operations-panel">
            <div>
              <Badge appearance="tint" color="brand">平台权限</Badge>
              <h2>企业入驻与隔离运营</h2>
              <p>平台侧只管理企业开通和聚合运行状态。企业内容、访客联系方式与私密对话仍由企业管理员在其工作台内管理。</p>
            </div>
            <Button appearance="primary" icon={<Building24Regular />} onClick={() => navigate(APP_PATHS.platformEnterprises)}>
              进入企业管理
            </Button>
          </section>
        </>
      ) : (
        <section className="content-panel">
          <ResourceState
            status={resource.status}
            title={resource.status === "empty" ? "尚未开通企业" : undefined}
            description={resource.status === "empty" ? "从企业开通开始创建第一个独立企业空间。" : resource.error?.message}
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={<Button appearance="primary" onClick={() => navigate(APP_PATHS.platformEnterprises)}>开通第一家企业</Button>}
          />
        </section>
      )}
    </main>
  );
}
