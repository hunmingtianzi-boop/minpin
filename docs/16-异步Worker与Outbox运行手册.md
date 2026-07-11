# 16 异步 Worker 与 Outbox 运行手册

## 1. 边界

Worker 是独立进程，使用 Celery 5.6 和 Redis broker。业务事实、租约、重试次数、幂等结果和评测证据都在 PostgreSQL；Redis 只传递“处理哪个 event id/lease token”，不是事实源。

API 与 Worker 使用不同数据库身份：

- API：`cf_ai_card_app`；
- Worker：`cf_ai_card_worker`；
- 迁移：平台托管的 schema owner。

Worker 身份不是超级用户、不能创建角色、不能绕过 RLS。跨租户领取只能调用固定 `search_path`、仅授权 Worker 的 `app.claim_outbox_events` 函数；领取后处理事务必须设置事件自身 tenant/company 作用域。

## 2. 投递语义

```text
业务事务写 outbox(pending)
        ↓
Beat 调度 poll_outbox
        ↓
PostgreSQL FOR UPDATE SKIP LOCKED
        ↓
processing + lock_token + lease_expires_at
        ↓
Redis/Celery JSON 消息（不含 payload）
        ↓
处理器续租 → 静态 payload 白名单 → 业务动作
        ↓
通知/结果 + outbox_deliveries + published 同事务提交
```

语义为至少一次。以下机制把重复投递收敛为一次业务效果：

- 每次领取生成新的 `lock_token`，旧任务不能提交；
- 长任务周期续租，进程崩溃后租约到期可重新领取；
- `outbox_deliveries(event_id, handler_name)` 唯一；
- 通知 ID 由 event/handler/recipient 确定性生成，并检查同资源通知；
- 评测结果以 event id 唯一并保存 SHA-256。

瞬时失败进入 `failed`，按 `base × 2^(attempt-1)` 退避；达到最大次数或 payload 永久非法进入 `dead_letter`。错误字段只保存固定错误码，不保存异常正文。

## 3. 事件目录

| Event | 处理器 | 结果 |
|---|---|---|
| `knowledge.evaluate.requested.v1` | 选择租户版本化评测集并运行 RAG release gate | `worker_job_results` 版本 1 报告 + 站内通知 |
| `lead.created.v1` | 线索到达提醒 | 幂等站内通知 |
| `privacy_request.created.v1` | 隐私权利请求提醒 | 幂等站内通知 |
| `enterprise.created.v1` | 企业初始化提醒 | 幂等站内通知 |
| `visit_summary.ready.v1` / `visit_summary.generated.v1` | 纪要完成提醒（生产者启用后） | 幂等站内通知 |

所有 payload 仅允许事件目录定义的 UUID 和枚举字段。`headers.contains_pii=true`、额外字段、错误 UUID 或作用域不一致会直接进入 dead-letter。日志从不输出 payload、headers、连接串、令牌或异常文本。

## 4. 健康与停止

- `GET :8020/health/live`：Worker 主进程和健康线程存活；
- `GET :8020/health/ready`：Worker 已进入 ready，PostgreSQL 与 Redis 均可用；
- 容器使用 `REMAP_SIGTERM=SIGQUIT`、20 秒 soft shutdown 和 30 秒停止宽限；
- Celery 使用 late ACK、worker lost reject、prefetch=1 和大于数据库租约的 Redis visibility timeout。

## 5. 告警建议

至少采集：

- pending/failed 数量和最老 `available_at`；
- processing 超时租约数量；
- dead-letter 新增速率；
- 各 event type 处理时延和尝试次数；
- Worker readiness、Redis/数据库连接失败；
- RAG 评测 gate 失败和报告版本。

建议阈值：最老可用事件超过 5 分钟、任意 dead-letter、新增租约连续回收、readiness 连续失败 3 次均告警。

## 6. 人工处置

1. 先查询 dead-letter 的 `event_type`、`attempts`、固定 `last_error`，禁止直接导出 payload 到工单或日志。
2. 修复根因并部署处理器。
3. 在受审计运维事务中把指定 event 改为 `failed`、清空租约、设置新的 `available_at`；不要复制事件或修改 deduplication key。
4. 确认 `outbox_deliveries` 是否已完成；已完成事件不得重放副作用。
5. 对知识评测检查 `worker_job_results.report_hash` 和 schema version。

## 7. 验收

- 两个并发 poller 不得领取同一 token；
- 进程在领取后崩溃，租约到期后必须以新 token 回收；
- 相同 Celery 消息重复到达，业务动作只发生一次；
- 瞬时失败按指数退避，耗尽后 dead-letter；
- A 企业任务不能读取或写入 B 企业通知/报告；
- 日志断言不得出现手机号、邮箱、Key、JWT 或 payload 哨兵值；
- 评测报告可按 event id 查询，包含 suite version、gate、指标和 SHA-256。
