# 通用数智名片 H5

`card-web` 是创非凡数智名片的通用访客端，不是某一家企业的独立网站。页面由通用渲染器、运行时 tenant 解析和企业内容包组成。

当前有两个可运行内容包：`template` 是无真实企业品牌的通用模板，`tuotu` 是首个企业 seed。通用模板用于复制接入结构，`tuotu` 用于验证真实资料整理、品牌主题、响应式页面、受控 FAQ、引用和拒答。

## 运行

在仓库根目录执行：

```powershell
pnpm web:dev
```

入口说明：

- `http://127.0.0.1:4173/`：无品牌通用模板。
- `http://127.0.0.1:4173/c/template`：无品牌通用模板。
- `http://127.0.0.1:4173/c/tuotu`：首个企业 seed。
- `http://127.0.0.1:4173/?tenant=tuotu`：查询参数形式的 seed 地址。

tenant 解析优先使用 `/c/{tenant}`，其次使用 `?tenant={tenant}`。没有 tenant 时加载 `template`。未知 tenant 显示无品牌安全状态，不得回退到 `template`、`tuotu` 或其他企业。

## 验证

```powershell
pnpm web:test
pnpm web:build
```

生产产物输出到 `apps/card-web/dist/`。测试应覆盖 tenant 解析、未知租户、内容包校验、知识匹配、拒答和跨租户内容隔离。

## 架构边界

```text
URL 或域名
  -> tenant 解析和注册表
  -> 加载该企业的已发布内容包
  -> 通用渲染器
  -> 页面、AI 助手和行动事件
```

通用层负责：

- 响应式页面结构、可复用模块、主题、动效和无障碍。
- tenant 解析、未知租户状态、内容 Schema 和安全默认值。
- AI 助手 UI、引用、拒答、加载态和转人工协议。
- 访问、链接点击、咨询和留资事件的统一接口。

企业内容包负责：

- 品牌身份、SEO、主题令牌和模块配置。
- 业务、指标、路径、案例、联系入口和素材。
- FAQ、来源、有效期、禁答和转人工条件。
- 审核状态、发布版本和素材授权信息。

禁止在通用组件中写死企业名称、业务文案、企业资产路径或企业专用问答规则。

## 当前目录

```text
src/
  domain/
    card.ts          # 内容包、主题、模块、行动和知识类型
  components/        # 企业无关的主题与 AI 助手 UI
  lib/
    knowledge.ts     # 通用知识匹配、引用与拒答逻辑
    tenantRuntime.ts # SEO、主题和租户素材运行时注入
    validateTenantConfig.ts # 内容包结构与安全校验
  tenants/
    index.ts         # MVP 注册表、tenant 解析和内容加载
    defineTenant.ts  # 内容包定义与类型约束
    template/
      tenant.ts      # 可复制的完整通用内容包示例
    tuotu/
      tenant.ts      # seed 元数据、页面内容、主题、FAQ 和策略
  App.tsx            # 通用页面编排和模块渲染
  main.tsx
  styles.css
public/
  tenants/
    template/
      assets/        # 通用模板示意素材，不可作为企业正式素材
    tuotu/
      assets/        # tuotu 独立素材
```

目录命名可随实现演进，但渲染器、tenant 解析和企业内容必须保持单向依赖：通用层定义协议，企业内容包实现协议，通用层不能反向导入某个企业。

## 通用模板的 7 类 block

所有 block 共享 `type`、`id`、`navLabel`、`showInNav`、`heading` 和 `description`。`eyebrow` 可选。当前渲染器支持：

| `type` | 用途 | 附加必填字段 |
|---|---|---|
| `feature-grid` | 业务、产品或能力分组 | `businesses` |
| `media-showcase` | 图片配能力说明 | `capabilities`、`action`、`visualLabel`、`visualTitle`、`visual` |
| `process` | 流程、分支路径与参与角色 | `steps`、`audienceHeading`、`audiences`；`steps[].path` 可选 `shared`、`branch-a`、`branch-b` |
| `evidence` | 案例、指标、证据与支持信息 | `visual`、指标文案、主题列表、说明文案和支持列表 |
| `engagement` | 接入、合作或转化步骤 | `steps`、`cta` |
| `faq` | 从知识库选择常见问题 | `itemIds`，`action` 可选 |
| `closing` | 页面收束与行动入口 | `art`、`actions` |

完整 tenant 还必须提供 `id`、`version`、`seo`、`brand`、`theme`、`hero`、`sections`、`assistant` 和 `footer`。字段细节、列表数量和复制步骤见 [企业内容包模板使用说明](../../docs/13-企业内容包模板使用说明.md)。

## 接入新企业

1. 分配稳定的 tenant key。
2. 使用 `docs/10-样板企业资料采集模板.md` 收集资料和授权。
3. 复制 `src/tenants/template/tenant.ts` 到 `src/tenants/{tenant}/tenant.ts`。
4. 复制模板素材目录到 `public/tenants/{tenant}/assets/`，然后全部替换为该企业已授权素材。
5. 只修改企业内容包中的品牌、主题、首屏、7 类 block、知识问答和页脚。
6. 在 `src/tenants/index.ts` 增加一次 import、注册表记录和 export。
7. 运行测试与构建，并访问 `/c/{tenant}` 检查桌面端、移动端、外链和问答。
8. 经企业审核人与平台审核人确认后再发布。

新增企业不得修改 `App.tsx` 或 `styles.css`，不得复制整套页面或建立独立构建工程。企业不需要的 block 可以从 `sections` 中移除，缺失内容不能用虚构信息补齐。

通用模板中的 `example.com`、模板图标、示意图片、审核数字、“等待企业资料”“占位”“示意”等内容都不得直接上线。预览前必须逐项替换，无法确认的 block 应移除。

完整架构见 [`docs/12-通用数智名片引擎与企业初始化.md`](../../docs/12-通用数智名片引擎与企业初始化.md)。逐字段操作见 [`docs/13-企业内容包模板使用说明.md`](../../docs/13-企业内容包模板使用说明.md)。`tuotu` seed 的事实口径见 [`docs/11-拓浙AI生态样板企业资料包.md`](../../docs/11-拓浙AI生态样板企业资料包.md)。

## AI 演示边界

当前助手可以使用本地知识匹配验证问答入口、引用、加载态和拒答体验。即使是本地实现，调用也必须绑定 tenant，不能从其他企业知识中补全答案。

生产接入时保持 UI 协议稳定，将本地匹配替换为 SSE 对话接口，并补齐：

1. tenant、名片、知识版本和审核状态。
2. 检索引用、低置信度拒答与转人工。
3. 会话、线索、访客同意记录和审计日志。
4. 速率限制、输入安全、敏感信息脱敏和用量控制。
5. 租户级缓存、索引、评测集和成本隔离。

## `tuotu` seed 内容与素材

`tuotu` 的企业资料来自用户提供的规划文档、生态总纲、IPO 结构稿、双轴图、业务讨论纪要和拓途浙享公开网站。页面按用户确认使用“拓浙 AI 集团”展示名称，但原始资料未提供工商主体证明。正式发布前仍需确认运营主体、联系人、数据证据、合作称谓、图片版权和人物肖像授权。

`hero-ecosystem.webp` 是该 seed 的原创氛围素材，不是通用平台默认图。后续企业应使用自身已授权素材或单独生成适合其品牌的视觉资产。
