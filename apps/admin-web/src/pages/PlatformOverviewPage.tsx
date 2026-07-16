import { Badge, Button } from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  Building24Regular,
  Settings24Regular,
} from "@fluentui/react-icons";

import { platformApi } from "../api/platformApi";
import { navigate, APP_PATHS } from "../routing";
import { PageHeader } from "../components/PageHeader";
import { ResourceState } from "../components/ResourceState";
import { useResource } from "../hooks/useResource";
import { formatTimestamp } from "../utils/format";

export function PlatformOverviewPage() {
  const resource = useResource(() => platformApi.getOverview());
  const overview = resource.data;
  const readinessIssues = overview
    ? Number(!overview.llmReady) + Number(!overview.importReady)
    : 0;
  const pendingCount = overview
    ? overview.onboardingCount + overview.failedTaskCount + readinessIssues
    : 0;
  const activity: Array<[string, number]> = overview
    ? ([
        ["近 30 天访问", overview.visits30d],
        ["近 30 天对话", overview.conversations30d],
        ["近 30 天线索", overview.leads30d],
      ] satisfies Array<[string, number]>).filter(([, value]) => value > 0)
    : [];

  return (
    <main className="page-stack platform-console">
      <PageHeader
        title="平台运营中心"
        description="先处理入驻、能力就绪与异常，再查看平台级聚合运营状态。"
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

      {resource.status === "ready" && overview ? (
        <>
          <section className="platform-status-grid" aria-label="平台企业概览">
            <article className="platform-status-primary">
              <span>待处理事项</span>
              <strong>{pendingCount}</strong>
              <p>
                {pendingCount > 0
                  ? `${overview.onboardingCount} 家待完成入驻，${overview.failedTaskCount} 项处理异常。`
                  : "关键能力和企业入驻均处于正常状态。"}
              </p>
            </article>
            <article className="platform-status-item">
              <span>企业开通进度</span>
              <strong>
                {overview.activeEnterpriseCount}/{overview.enterpriseCount}
              </strong>
              <p>{overview.onboardingCount} 家企业仍在完善入驻资料。</p>
            </article>
            <article className="platform-status-item">
              <span>已发布名片</span>
              <strong>{overview.publishedCardCount}</strong>
              <p>只统计已可公开访问的企业名片。</p>
            </article>
          </section>

          <section className="platform-operations-panel">
            <div>
              <Badge
                appearance="tint"
                color={readinessIssues === 0 ? "success" : "warning"}
              >
                {readinessIssues === 0 ? "关键能力已就绪" : "关键能力待配置"}
              </Badge>
              <h2>LLM 与资料导入</h2>
              <p>
                LLM {overview.llmReady ? "已就绪" : "尚未就绪"}；资料导入
                {overview.importReady ? "已就绪" : "尚未就绪"}。平台只展示聚合状态，不读取企业私域正文。
              </p>
            </div>
            {overview.llmReady ? (
              <Button
                appearance="primary"
                icon={<Building24Regular />}
                onClick={() => navigate(APP_PATHS.platformEnterprises)}
              >
                查看企业
              </Button>
            ) : (
              <Button
                appearance="primary"
                icon={<Settings24Regular />}
                onClick={() => navigate(APP_PATHS.platformLlmSettings)}
              >
                配置 LLM
              </Button>
            )}
          </section>

          {activity.length > 0 && (
            <section className="content-panel dashboard-metrics" aria-label="近 30 天聚合活动">
              {activity.map(([label, value]) => (
                <article className="dashboard-metric" key={label}>
                  <strong>{value}</strong>
                  <span>{label}</span>
                </article>
              ))}
            </section>
          )}

          <p className="dashboard-generated">
            聚合数据生成于 {formatTimestamp(overview.generatedAt)}
          </p>
        </>
      ) : (
        <section className="content-panel">
          <ResourceState
            status={resource.status === "ready" ? "empty" : resource.status}
            title={resource.status === "empty" ? "平台总览暂不可用" : undefined}
            description={
              resource.status === "empty"
                ? "平台服务尚未返回运营聚合数据。"
                : resource.error?.message
            }
            errorCode={resource.error?.code}
            requestId={resource.error?.requestId}
            onRetry={resource.status === "error" ? resource.reload : undefined}
            emptyAction={
              <Button
                appearance="primary"
                onClick={() => navigate(APP_PATHS.platformEnterprises)}
              >
                进入企业中心
              </Button>
            }
          />
        </section>
      )}
    </main>
  );
}
