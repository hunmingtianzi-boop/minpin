# 性能压测与 SLA 验收

版本：V1.0  <br>
更新：2026-07-11  <br>
适用范围：公开名片 API、企业管理 API、公开 AI 问答全链路

## 1. 验收口径

详细开发文档早期草案提出“名片页 2 秒、AI 3–8 秒、后台 1 秒”；开发基线把口径进一步固定为可计算的分位数。正式验收采用开发基线：

| 场景 | V1.0 门槛 | 本工具测量点 |
|---|---:|---|
| 名片首屏 | 常用 4G、生产构建，P75 ≤ 2.5 秒 | 本工具只测公开 HTTP；页面首屏另用 Lighthouse/Web Vitals |
| AI 首 token | P95 ≤ 5 秒 | 发出消息请求至首个非空 `message.delta` |
| AI 完整回答 | P95 ≤ 10 秒 | 发出消息请求至 `message.completed` |
| 常用后台列表 | P95 ≤ 1 秒 | 完整读取 HTTP 响应体 |
| 试点容量 | 目标并发和 2 倍短时峰值均通过 | 并发数必须在测试计划中预先签字确认 |
| 可用性 | 试点期月度 99.5% | 由监控和事故记录验证，不用一次压测代替 |

延迟分位数使用 nearest-rank；延迟分布只统计成功请求，错误率单独设门。内部发布门默认错误率 ≤ 1%，这不是对外 SLA，项目可在评审后收紧，不能静默放宽。

## 2. 工具边界

`tools/perf` 提供两类真实环境负载：

- `http`：对一个 HTTP 端点按固定请求数、并发和预热执行负载；`public-card` 预设检查 P75 2.5 秒，`admin-list` 预设检查 P95 1 秒。
- `rag`：每个虚拟用户建立独立的 visit → chat consent → conversation，再向 SSE 消息端点顺序提问，检查首内容、完整回答和错误率。

报告不会保存问题正文、响应正文、Token、Header 值或 URL query；只保存问题集 SHA-256、Header 名称、状态码和固定错误类别。命令不自动重试，因为重试会掩盖真实延迟和故障。

`python -m tools.perf.smoke` 启动本机 mock 服务，只验证负载器、SSE 解析器、脱敏和 fail-closed gate。它不访问 PostgreSQL、Redis 或模型，也不代表任何部署环境达到 SLA。CI smoke JSON 必须保留这条免责声明。

## 3. 正式测试前置条件

1. 使用隔离的 staging/容量环境，应用、PostgreSQL、Redis、Worker、反向代理与生产规格一致；不得直接对生产公开流量压测。
2. 固定 Git SHA、迁移 head、企业内容包、评测集、模型、Prompt、Embedding、输出上限和网络区域。
3. 预先确认“目标试点并发”和“2 倍峰值并发”，并设模型费用上限；没有明确并发数字不能签署容量通过。
4. 使用合成访客和无个人信息的问题。测试会创建 visit、consent、conversation、message 与 `ai_runs`，环境应可按 run ID 清理。
5. 保持鉴权、RLS、CSRF 和限流有效。若默认单 IP 每分钟限制妨碍容量场景，只能在隔离环境按测试计划提高阈值或由受控多源发压，报告必须记录差异。
6. 预热完成后再计量。HTTP 正式验收建议至少 100 个计量样本；RAG 成本允许时建议至少 50 个，20 个只算最小冒烟。
7. 同时采集 `GET /api/v1/metrics`、数据库池、Redis、Worker/Outbox、Provider 限流、Token 和费用；模型供应商异常必须单独归因。

当前 SSE 的验收点是浏览器真正收到的首个 `message.delta`。如果服务端先等待完整模型结果再分块，首 token 与完整回答会非常接近；工具会如实暴露这一现象，不把连接建立或 `message.started` 当成首 token。

## 4. HTTP 负载

公开名片示例：

```powershell
services/api/.venv/Scripts/python.exe -m tools.perf.cli http `
  --url https://staging.example.com/api/v1/public/cards/template `
  --profile public-card `
  --requests 200 `
  --concurrency 10 `
  --warmup-requests 20 `
  --timeout-seconds 10 `
  --scenario public-card-steady `
  --output artifacts/perf/public-card-steady.json
```

后台列表的凭证只从环境变量读取，不能放进命令参数或报告。应由 CI/Secret Manager 注入完整的 `Bearer ...` 值：

```powershell
services/api/.venv/Scripts/python.exe -m tools.perf.cli http `
  --url "https://staging.example.com/api/v1/admin/cards?limit=50&offset=0" `
  --profile admin-list `
  --header-env Authorization=PERF_AUTHORIZATION `
  --requests 200 `
  --concurrency 10 `
  --warmup-requests 20 `
  --scenario admin-card-list `
  --output artifacts/perf/admin-card-list.json
```

`custom` 场景可显式传 `--max-p75-ms`、`--max-p95-ms`、`--max-error-rate` 和 `--min-success-rps`。HTTP 302 不会自动跟随；意外跳转会按错误计入，避免错误域名看似通过。

## 5. RAG 全链路负载

问题文件支持字符串数组，或现有 `packages/evals/*.json` 的 `cases[].question`。每个虚拟用户使用一个独立会话，虚拟用户内的问题顺序固定，因而同一数据集、样本数和并发的工作负载可重复。

```powershell
services/api/.venv/Scripts/python.exe -m tools.perf.cli rag `
  --base-url https://staging.example.com/api/v1 `
  --card-slug template `
  --questions packages/evals/template.v1.json `
  --requests 50 `
  --concurrency 5 `
  --warmup-requests 5 `
  --timeout-seconds 20 `
  --max-ttft-p95-ms 5000 `
  --max-total-p95-ms 10000 `
  --max-error-rate 0.01 `
  --scenario rag-steady `
  --output artifacts/perf/rag-steady.json
```

先跑目标并发的稳定场景，再把 `--concurrency` 调为两倍执行短时峰值。样本总数、持续时间、模型并发上限和单 IP 限流必须足以形成真实重叠，不能只提高命令数字但让所有请求排队串行。

RAG 性能报告只验证传输和时延，不判断事实正确性、引用支持或跨租户泄露。发布时仍须运行版本化离线评测，满足 Retrieval Hit@5、有资料回答、拒答、引用与安全门槛。

## 6. 输出、退出码与判定

JSON 报告包含：

- 运行 ID、时间、无凭证目标、环境/build ID；
- 样本数、并发、预热、超时、数据集哈希；
- 成功数、错误率、状态码/错误类别、P50/P75/P95/P99、成功 RPS；
- RAG setup、首 token 和完整回答分布；
- 实际门槛、`passed` 与逐条失败原因。

退出码：`0` 为 gate 通过，`2` 为有完整报告但 gate 未通过，`1` 为参数或运行器错误。任何“无成功样本”“分位数不可用”都 fail closed。

正式评审使用[性能验收报告模板](templates/性能验收报告模板.md)。机器 JSON、监控快照、离线 RAG 评测、失败样本编号和审批记录应关联同一发布版本。禁止以 CI mock smoke、单次手工访问或平均值替代正式证据。

## 7. CI smoke

```powershell
services/api/.venv/Scripts/python.exe -m pytest tools/perf/tests
services/api/.venv/Scripts/python.exe -m tools.perf.smoke `
  --output artifacts/perf/ci-smoke.json
```

CI 上传 `ci-smoke.json` 仅用于证明工具自身仍可运行。部署环境 SLA 应由受控的手动或发布流水线 stage 执行，避免每次普通提交调用收费模型或污染容量数据。
