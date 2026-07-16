## ADDED Requirements

### Requirement: 平台管理员管理多个主 Chat 配置
系统 SHALL 允许 `platform_admin` 创建、查看、编辑、测试和启用多个命名的 OpenAI-compatible Chat 配置，并在存在配置时保持恰好一个选中的主配置。

#### Scenario: 创建首个配置
- **WHEN** 平台管理员创建第一条有效配置
- **THEN** 系统保存该配置并将其设为唯一主配置

#### Scenario: 切换主配置
- **WHEN** 平台管理员确认将另一条已配置密钥且启用的配置设为主配置
- **THEN** 系统原子切换主配置、更新版本并记录不含密钥的审计事件

#### Scenario: 并发上下文过期
- **WHEN** 管理员基于过期版本或过期主配置 ID 提交编辑或切换
- **THEN** 系统返回冲突且不覆盖较新的配置

### Requirement: LLM 密钥不可回显
系统 MUST 使用现有字段加密能力保存 API key，任何读取响应、审计、日志和前端持久状态都不得包含明文密钥。

#### Scenario: 读取配置列表
- **WHEN** 平台管理员读取 LLM profiles
- **THEN** 响应只包含 `key_configured` 与脱敏 `key_hint`，不包含密文或明文

#### Scenario: 空密钥更新
- **WHEN** 管理员编辑配置但未提供新密钥
- **THEN** 系统保留该 profile 原有密钥且响应仍不回显密钥

### Requirement: 连接测试遵守出站安全边界
系统 MUST 对 base URL 做 scheme、credentials、query、fragment、DNS 与生产 HTTPS 校验；连接测试 SHALL 使用严格超时、禁重定向、禁自动重试的受限请求，并只返回脱敏结果。

#### Scenario: 合法连接测试
- **WHEN** 平台管理员测试一个允许访问的配置
- **THEN** 系统返回成功状态、provider、model 和延迟，不返回上游正文

#### Scenario: 可疑地址
- **WHEN** base URL 指向不允许的本地/私网目标或包含 credentials、query、fragment
- **THEN** 系统拒绝测试且不发送 API key

### Requirement: AI 运行时与公开可用状态一致
访客 Chat SHALL 在每次请求时解析当前主配置；只有数据库中零 profile 时才允许环境配置兜底。公开名片返回的 AI 可用状态 MUST 使用同一解析规则。

#### Scenario: 主配置即时生效
- **WHEN** 平台管理员切换到另一条有效主配置
- **THEN** 后续访客 Chat 和 `ai_assistant.available` 无需重启即可使用新配置

#### Scenario: 主配置显式停用
- **WHEN** 当前主配置被显式停用
- **THEN** 访客 AI 明确不可用且系统不得静默回退到环境配置或另一供应商

### Requirement: LLM 配置界面可在桌面和窄屏使用
平台 LLM 页面 SHALL 使用配置列表、当前主配置摘要和创建/编辑抽屉；窄屏下动作必须纵向可达且密钥输入在保存后清空。

#### Scenario: 390px 编辑配置
- **WHEN** 管理员在 390px 宽视口打开并编辑配置
- **THEN** 所有字段、测试、保存和设为主配置动作无需横向滚动即可完成
