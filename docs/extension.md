# 扩展指南

本文档准确展示当你扩展系统时究竟会改动什么。三种常见扩展会被详细演示：

1. 新增一个市场（例如日本）
2. 新增一个智能体角色（例如事实核查员）
3. 新增一个 schema 字段（例如"go-to-market 模式"支柱）

## 1. 新增一个市场

市场层是最干净的扩展点。三个小文件，无需改动智能体或编排器。

### 第 1 步 —— 添加一个 `MarketProfile`

创建 `backend/app/market/jp.py`：

```python
from dataclasses import dataclass, field
from typing import List
from .base import MarketProfile


def _default_seeds() -> List[str]:
    return [
        "{product} 競合",
        "{product} 比較",
        "{product} 価格",
        "{product} レビュー",
        "{product} 機能",
    ]


@dataclass
class JapanMarket(MarketProfile):
    code: str = "jp"
    display_name: str = "Japan"
    locale: str = "ja-JP"
    language: str = "ja"
    currency: str = "JPY"
    flag: str = "🇯🇵"
    search_seeds: List[str] = field(default_factory=_default_seeds)
    preferred_search_provider: str = "bing"
    allowed_source_domains: List[str] = field(default_factory=lambda: [
        "note.com", "qiita.com", "itreview.jp", "boxil.jp",
    ])
```

### 第 2 步 —— 注册它

在 `backend/app/market/__init__.py`：

```python
from .jp import JapanMarket

REGISTRY: Dict[str, MarketProfile] = {
    "cn": ChinaMarket(),
    "us": USMarket(),
    "jp": JapanMarket(),     # ← 新增
}
```

### 第 3 步 —— 添加服务端语言包

在 `backend/app/i18n/locales.py` 中，添加一个 `"ja-JP"` 块，镜像 `"zh-CN"` / `"en-US"` 中的键。保持键完全一致——章节标签和 prompt 字符串会自动拾取新 locale。

### 第 4 步 —— 添加前端语言包

创建 `frontend/src/i18n/ja.ts`，镜像 `zh.ts` / `en.ts`。在 `frontend/src/i18n/index.ts` 中注册它：

```ts
import { ja } from "./ja";

const BUNDLES: Record<Locale, Record<string, string>> = {
  "zh-CN": zh, "en-US": en, "ja-JP": ja,   // ← 新增
};

export function marketToLocale(market: string): Locale {
  if (market === "cn") return "zh-CN";
  if (market === "us") return "en-US";
  if (market === "jp") return "ja-JP";     // ← 新增
  return "en-US";
}
```

同时把 `Locale` 类型联合扩展为包含 `"ja-JP"`。

### 第 5 步 —— 更新语言名映射（可选）

在 `backend/app/agents/base.py` 中，添加日语显示名，使系统 prompt 能把语言约束表述得更自然：

```python
return {"zh": "Simplified Chinese (简体中文)", "en": "English",
        "ja": "Japanese (日本語)"}.get(self.market.language, self.market.language)
```

### 大功告成

DAG、智能体、schema、前端组件——这些都不碰市场代码。它们从当前激活的 `MarketProfile` 读取。`/api/analysis/markets` 端点现在会列出日本，表单也会渲染出带其国旗的新选项。

## 2. 新增一个智能体角色

假设你想要一个**事实核查员（Fact-Checker）**智能体，运行在撰写器与 QC 之间，从报告草稿中挑出断言并对照来源进行交叉核验。

### 第 1 步 —— 实现该智能体

创建 `backend/app/agents/fact_checker.py`：

```python
from .base import BaseAgent

class FactCheckerAgent(BaseAgent):
    role = "fact_checker"

    async def check(self, *, report: FinalReport) -> List[FactCheckIssue]:
        ...
```

添加到 `backend/app/agents/__init__.py`。

### 第 2 步 —— 添加一个 DAG 节点

在 `backend/app/orchestration/state.py`：

```python
DagNode("fact_check", "事实核查", "Fact check", "fact_checker",
        "校验报告中的事实是否与来源一致。", "Verify each claim against its source."),
```

以及一条边：`DagEdge("write", "fact_check")`，然后 `DagEdge("fact_check", "qc")`。移除旧的 `("write", "qc")` 边。

### 第 3 步 —— 接入图

在 `backend/app/orchestration/graph.py` 的 `_make_nodes` 内：

```python
fact_checker = FactCheckerAgent(market)

async def n_fact_check(state: GraphState) -> GraphState:
    report = FinalReport.model_validate(state["report"])
    issues = await fact_checker.check(report=report)
    return {**state, "fact_check_issues": [i.model_dump() for i in issues]}
```

以及在 `build_graph` 中：

```python
g.add_node("fact_check", n_fact_check)
g.add_edge("write", "fact_check")
g.add_edge("fact_check", "qc")
```

### 第 4 步 —— 前端改动

DAG 无需改动——它从 `/api/analysis/dag` 读取定义，而后者现在已包含新节点。`TraceList` 已按 `agent` 分组，因此新智能体的事件会以自己的标签颜色出现（若想要自定义颜色，在 `TraceList.tsx` 的 `AGENT_COLOR` 里加一行即可）。

## 3. 新增一个 schema 字段

schema 刻意保持宽松——新增**可选**字段是非破坏性的。

示例：新增一个 `gtm_motion` 字段，描述每个竞品的 go-to-market 模式（`"plg"`、`"sales_led"`、`"hybrid"`）。

### 第 1 步 —— 加入 schema

在 `backend/app/schema/competitor.py`：

```python
class GTMMotion(BaseModel):
    primary: Optional[Literal["plg", "sales_led", "hybrid"]] = None
    notes: str = ""
    sources: List[SourceRef] = Field(default_factory=list)

class CompetitorKnowledge(BaseModel):
    ...
    gtm_motion: Optional[GTMMotion] = None
```

### 第 2 步 —— 提升 schema 版本

设 `schema_version: str = "1.1.0"`。

### 第 3 步 —— 更新采集器 prompt

在 `backend/app/prompts/collector.py` 中，给 schema 提醒列表加一条要点。模型会自动开始产出新字段。

### 第 4 步 —— 更新 QC 检查（可选）

若希望 QC 强制 `gtm_motion` 非空，在 `backend/app/agents/qc.py` 中加一条确定性检查。否则该字段保持为建议性。

### 第 5 步 —— 更新前端渲染（可选）

在 `frontend/src/pages/Report.tsx` 的竞品标签页下加一张卡片。渲染器已能优雅处理缺失字段。

### 向后兼容

旧报告（schema 1.0.0）没有新字段。因为它是 `Optional`，Pydantic 会照常加载它们。对于这种增量改动，无需迁移脚本。

## 4. 新增一个数据源

假设你想新增一个"G2 评论"连接器，让采集器在通用网络搜索之外额外调用它。

### 第 1 步 —— 添加连接器

创建 `backend/app/collectors/g2.py`，提供一个 `async def fetch_g2(product: str) -> List[Cited]` 函数。

### 第 2 步 —— 接入采集器

在 `backend/app/agents/collector.py` 中，修改 `_build_evidence`，当激活市场的 `allowed_source_domains` 包含 `"g2.com"` 时调用 `fetch_g2(competitor_name)`。

### 第 3 步 —— 完成

无需改 schema——产生的事实使用既有的 `SourceRef`，`kind="web"` 加上真实的 G2 URL。

---

这套布局的全部要点在于：**智能体是无状态的工人**，**市场是配置**，**schema 是契约**。新增能力意味着触碰正确的那条轴——几乎从不需要碰编排器。
