# 合规说明

本文档涵盖项目在 robots.txt、ToS、数据隐私、LLM 使用以及评分细则中合规评分项上的立场。

## 1. 网页抓取

### robots.txt 强制执行

* 实现于 [`backend/app/collectors/robots.py`](../backend/app/collectors/robots.py)。
* 抓取器使用 Python 标准库 `urllib.robotparser` 并带一个异步缓存。
* 每次抓取都会以我们的 `USER_AGENT`（默认 `"CompetitiveAnalysisAgent/1.0 (+https://example.com/contact)"`）调用 `can_fetch(url)`。
* 若某主机在某路径上禁止我们的 UA，抓取器返回 `FetchedPage(blocked_by_robots=True)`——绝不返回页面内容。
* `RESPECT_ROBOTS` 默认为 `1`。*仅*在受控测试环境中才置为 `0`。

### 限速

* 每主机限速默认为 `1 请求 / 秒 / 主机`，由 `CRAWL_RATE_LIMIT_PER_HOST` 控制。
* 在 [`backend/app/collectors/web.py`](../backend/app/collectors/web.py) 中实现为每主机一个 asyncio 锁加单调时钟节流。

### User-Agent

* `USER_AGENT` 环境变量设置每次抓取和每次 robots.txt 请求所发送的字符串。
* 默认值含一个联系 URL 占位符。**在任何生产部署之前，请把该占位符替换为真实的联系 URL。**

### 域名白名单

每个市场画像都携带一个 `allowed_source_domains` 列表。未来版本可以把采集器硬性限制到该列表。今天该列表是信息性的，由搜索查询调优器使用。

## 2. 搜索服务商 ToS

可插拔的搜索后端（`SEARCH_PROVIDER`）支持 Tavily、Serper 和 Bing。每个都通过其官方 API 调用，API Key 由运营方提供。**不进行任何对搜索引擎结果页的抓取**——只使用获授权的 API。

## 3. LLM 使用

### 提供方

火山方舟 Ark（Volcengine / 火山引擎）。运营方需提供：

* `ARK_API_KEY` —— 从火山方舟控制台签发。
* `ARK_MODEL_ID` —— 所选模型的 endpoint ID（例如豆包，或自部署的模型）。
* `ARK_BASE_URL` —— 默认 `https://ark.cn-beijing.volces.com/api/v3`，若你的部署使用不同区域请覆盖。

### Mock 模式

未配置 Key（或 `VOLC_MOCK=1`）时，LLM 客户端返回内置的预设输出。**mock 输出在 UI 中（黄色"mock 模式"横幅）和追踪记录中（`extras.mocked = true`）都被明确标注。**这能防止演示产物被误认为真实的模型输出。

### 发送给 LLM 的数据

* 智能体 prompt（system + user）。
* 从公开网页抓取的片段（受 robots 约束）。
* 用户输入（产品名 + 市场 + 可选的额外竞品）。

系统**不会**发送：
* 用户身份 / 认证令牌（当前没有按用户的账号体系）。
* 智能体 prompt 之外的任何东西。

若你在未来版本中导入私有文档，它们**必须**先经过一道 PII 脱敏处理（见 §4）。

## 4. PII 处理

### 合成的访谈与问卷

采集器智能体可以产出"合成的"访谈片段和问卷摘要。它们被标记为 `kind="interview"` 或 `kind="questionnaire"` 并带有低置信度（≤ 0.6）。系统 prompt 指示模型把它们写得明显虚构（"合成访谈 #1"等）——它们绝不应被当作真实的用户陈述呈现。

### 导入真实访谈 / 问卷数据（v1.1，计划中）

schema 已支持用于真实数据的 `kind="interview"` 和 `kind="questionnaire"`。当 v1.1 加入导入端点时，它**必须**：

1. 通过正则 + 命名实体识别，剥离标准 PII（邮箱、电话、政府证件号）。
2. 把人名替换为角色标签（`"Persona A"`、`"某中端金融科技公司的 PM"`）。
3. 对来源行 ID 做哈希——绝不存储原始标识符。
4. 在数据进入存储之前，向运营方弹出确认对话框。

### 数据留存

* SQLite 存储默认无限期保留报告和追踪。运营方应按其辖区添加一个留存清理任务（cron + `DELETE FROM ... WHERE generated_at < ?`）。
* 追踪包含完整的 prompt 和响应，其中可能含有来自公开页面的引用摘录。把该存储视为含有第三方内容，并套用你常规的 IP / 留存策略。

## 5. 与挑战赛"工具与资源使用准则"的合规

* 所有第三方库均为开源（MIT / BSD / Apache 2.0）。见 [`backend/requirements.txt`](../backend/requirements.txt) 和 [`frontend/package.json`](../frontend/package.json)。
* 唯一的闭源依赖是火山方舟 Ark API，它是赛事指定的 LLM 提供方。
* 不捆绑任何专有数据集；mock 数据由项目作者合成且明显虚构。
* 开发过程中使用了 AI 编程辅助（TRAE / Claude / 类似工具）；该使用已在仓库和提交日志中声明。

## 6. 提交材料清单

完整的提交材料集包括：

* **方案文档** —— `docs/architecture.md`、`docs/agents.md`、`docs/schema.md`。
* **代码仓库** —— 本目录。
* **演示视频脚本** —— `docs/demo-script.md`。
* **README 与运行说明** —— 顶层 `README.md` 和 `docs/deployment.md`。
* **合规声明** —— 本文件。

## 7. 运营方检查清单

在让本系统对接生产流量之前：

- [ ] 把 `USER_AGENT` 中的占位联系 URL 替换为真实的。
- [ ] 设置 `ARK_API_KEY`、`ARK_MODEL_ID`，并在 `ARK_BASE_URL` 中选择区域。
- [ ] 选择一个搜索服务商并设置其 Key。
- [ ] 决定是否保持 `RESPECT_ROBOTS=1`（是）和 `CRAWL_RATE_LIMIT_PER_HOST`（≥ 1.0）。
- [ ] 给 SQLite 存储添加一个留存清理任务。
- [ ] 若对公网暴露，把 `/api/analysis/start` 端点置于认证之后。
- [ ] 考虑是否应把 `CORSMiddleware` 从 `"*"` 收紧到只允许你的前端来源。
