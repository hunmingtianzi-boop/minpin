## ADDED Requirements

### Requirement: 当前 knowledge_import 是唯一资料导入链路
系统 SHALL 继续使用当前仓库的 `KnowledgeImportPanel`、`knowledgeImportsApi`、`knowledge_import` 解析器/存储和 `cf_worker.knowledge_imports` Worker；本变更不得引入 `document_import`、Docling、MinerU、独立 OCR 服务或第二套原始文档解析链路。资料辅助建企 MAY 在当前解析草稿之上调用已激活 LLM 生成可审核结构化建议，但不得替代解析器、直接读取原始二进制或自动生效。

#### Scenario: 实施范围检查
- **WHEN** 本变更完成范围审查
- **THEN** 依赖、迁移和运行服务中不存在新增的参考项目文档导入实验组件

### Requirement: 保持现有格式与限额合同
系统 SHALL 支持当前已实现的 PDF、DOCX、PPTX、XLSX、CSV、TXT、MD、HTML/HTM 和 PNG/JPG/JPEG/WEBP/TIFF/BMP；每批最多 5 个文件、单文件不超过 10 MiB、批次不超过 25 MiB。

#### Scenario: 支持格式导入
- **WHEN** 企业用户上传符合 MIME、文件签名和限额的支持文件
- **THEN** 系统创建异步导入批次并返回逐文件状态

#### Scenario: 超限或伪装文件
- **WHEN** 文件数量、大小、MIME、签名或归档安全限制不符合合同
- **THEN** 系统在安全边界拒绝并返回稳定错误码

### Requirement: 导入默认产生可审核草稿
导入解析结果 SHALL 默认创建草稿并等待人工审核发布；只有具备明确发布权限且显式选择自动发布时才能直接发布。

#### Scenario: 默认导入
- **WHEN** 企业用户未选择授权的自动发布
- **THEN** 所有成功解析条目保持草稿状态且不出现在公开知识中

#### Scenario: 部分文件失败
- **WHEN** 同一批次中部分文件解析失败
- **THEN** 系统保留成功草稿并逐文件展示失败原因，不把整个批次伪装成成功

### Requirement: 导入严格租户隔离
普通企业导入的创建、批次查询、草稿审核和发布 MUST 从当前 membership 推导企业范围。平台资料辅助建企只能从服务端绑定且由创建者拥有的开通会话推导临时企业范围，客户端不得提交任意 tenant/company 作为授权依据。任何跨租户或跨开通会话访问都必须拒绝并记录安全审计所需上下文。

#### Scenario: 跨企业读取批次
- **WHEN** A 企业账号请求 B 企业的导入批次或草稿
- **THEN** 系统返回拒绝且不泄漏资源是否存在

#### Scenario: 平台开通会话访问其他临时企业
- **WHEN** 平台管理员使用开通会话 A 请求开通会话 B 的导入批次或草稿
- **THEN** 系统返回拒绝，且目标企业范围只能由服务端会话绑定关系确定

### Requirement: 导入关键链路有轻量直接证据
实施验收 SHALL 覆盖一个真实小型支持文件的上传、异步处理、草稿生成和人工发布/保留草稿路径，并覆盖一个不支持或超限失败路径；无需运行参考项目的大文件 Docling 验证。

#### Scenario: 本地集成冒烟
- **WHEN** 在当前 Compose/本地服务运行导入冒烟
- **THEN** API、Worker、数据库状态和企业控制台显示一致且无未处理错误
