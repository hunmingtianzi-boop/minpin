# CF AI Card Worker

独立 Celery/Redis Worker，负责从 PostgreSQL transactional outbox 领取并处理异步事件。

核心保证：

- `SELECT ... FOR UPDATE SKIP LOCKED` 并发领取；
- 数据库租约、心跳续租和崩溃回收；
- Celery late ACK、Redis visibility timeout 与至少一次投递；
- `outbox_deliveries` 原子幂等账本；
- 指数退避、最大次数和 dead-letter；
- 独立 `cf_ai_card_worker` 数据库身份，无超级权限和 `BYPASSRLS`；
- 事件 payload 白名单，不记录 payload、凭证或异常正文；
- `/health/live` 与 `/health/ready` 健康端点（默认端口 `8020`）。

本地安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install --no-deps ..\api .
```

运行：

Windows 本地需要两个进程（Celery 不允许在 Windows worker 上使用 `--beat`）：

```powershell
.\.venv\Scripts\celery -A cf_worker.celery_app:celery_app beat --loglevel=INFO
.\.venv\Scripts\celery -A cf_worker.celery_app:celery_app worker `
  --pool=solo --queues=outbox.poll,outbox.process --loglevel=INFO
```

Linux/容器使用默认 prefork，并可由同一容器加 `--beat`；多副本生产环境应只运行一个 Beat。

测试：

```powershell
.\.venv\Scripts\python -m ruff check cf_worker tests
.\.venv\Scripts\python -m pytest tests -m "not integration"
```
