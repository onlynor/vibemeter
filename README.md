# VibeMeter · 舆情洞察员

[![GitHub](https://img.shields.io/badge/GitHub-onlynor%2Fvibemeter-181717?logo=github)](https://github.com/onlynor/vibemeter)

> 输入关键词，从 **B 站 / 微博 / 豆瓣 / 知乎 / 贴吧** 抓取公开评论，做清洗、分词与 `SnowNLP` 情感打分，在仪表板里看情感分布、观点词云和代表性评论；同时用**搜索引擎**补充事件背景，可选挂 LLM 做对话式解读。
>
> FastAPI + React/Vite，前后端分离。

<img src="assets/screenshots/home.png" width="880" alt="首页">

---

## 快速开始

**1. 配 Cookie（可选）**

```bash
cp .env.example .env     
```

全留空也能跑：豆瓣、贴吧、B 站匿名可用；微博和知乎必须配 Cookie。

**2. 起服务**（两个终端）

```bash
# 后端 → http://127.0.0.1:8092
cd backend && uv run python run.py

# 前端 → http://127.0.0.1:5173
cd frontend && pnpm install && pnpm dev
```

打开 <http://127.0.0.1:5173> 即可。

**Docker 一键**

```bash
docker compose up --build     # 前端 :8080，后端 :8092
```

---

## 数据源

跑之前点首页的「检测可用性」，能直接看出谁在风控，不用等几分钟才发现。

| 数据源 | 匿名可用 | Cookie | 备注 |
|---|:---:|---|---|
| 豆瓣 | ✅ | 可选 | 移动端接口读公开短评（影视 + 图书） |
| 贴吧 | ✅ | 可选 | 移动端接口搜主题 + 读楼层 |
| B 站 | ⚠️ | 建议配 | 评论接口 `-412` 风控常态化，配 Cookie 可绕过 |
| 微博 | ❌ | **必需** | 公开搜索强制登录态，需含 `SUB` 字段 |
| 知乎 | ❌ | **必需** | 匿名搜索恒 400；没 Cookie 只能退回热榜摘要，量很小 |

另有一层**检索增强**，与上面的评论采集并发执行：

| 检索源 | 匿名可用 | 备注 |
|---|:---:|---|
| 百度搜索 | ✅ | 解析网页检索结果，自动跳过广告；频繁请求会触发安全验证，稍等即恢复 |

> 检索结果只作为**事件背景**喂给 LLM 并在页面上单独展示，**不参与情感分析**。
> 标题与摘要是对事件的客观描述而非网友观点，混进 `SnowNLP` 会以中性分稀释真实的情感分布。
>
> 新增检索源（必应 / 搜狗 / 360 / GitHub …）见 [`backend/app/search/README.md`](backend/app/search/README.md)，
> 只需新增一个文件，不必改动任何既有代码。

> **本项目一律直连**：所有 `httpx` 客户端固定 `trust_env=False`，不读取 `ALL_PROXY`、`HTTP_PROXY` 等环境变量。
> 终端里的代理配置不受影响；目标站点都在国内，走境外代理反而更容易触发风控。

> **复制 Cookie 务必取完整值**：开发者工具里过长的值会用省略号 `…` 截断显示，直接复制会得到一个无法作为请求头发送的坏值。请在控制台执行 `document.cookie`，或右键 → Copy value。

---

## 功能

### 首页监测台

关键词 → 检索模式（快速分析 / 深度研究 / 实时监测）→ 数据源多选 → 高级检索设置 → 分析选项，
高级项默认折叠，主流程始终在首屏。实时热搜支持来源筛选、定时刷新（手动 / 5 分钟 / 15 分钟 / 1 小时）
与趋势标记；最近任务卡片可直接回看结果。

> 部分选项后端尚未支持（排序策略、情感粒度、新闻/GitHub 检索源等），
> 界面上会标注 **前端预设**，只保存偏好、不谎称已生效。

### 采集

`auto` 模式五源并发，单源首批 8 s 未返回自动跳过、总时长上限 60 s。
各源结果**按来源轮转合并**并跨源去重——直接按到达顺序拼接的话，最快的源会吃光整个配额，
"五源聚合"很容易变成九成来自同一个平台，情感分布也就跟着失真。
结果页的「样本构成」卡片会显示各来源的实际占比。进度经 WebSocket 实时推送。

<img src="assets/screenshots/progress.png" width="880" alt="采集进度">

### 分析结果

`jieba` 分词 + 词性过滤（名词/动词/形容词）+ 停用词，`SnowNLP` 打分：> 0.6 记正向、< 0.4 记负向。展示情感分布、Top 15 高频词、最正/最负各 3 条代表评论，以及各平台原帖（B 站视频可内嵌播放）。

<img src="assets/screenshots/dashboard.png" width="640" alt="结果总览">

### 观点词云

正负向短语按差减值排序，自动剔除两边都高频的争议词。

<img src="assets/screenshots/wordcloud.png" width="640" alt="观点词云">

### LLM 解读（可选）

侧边栏基于本次任务的结构化数据对话，SSE 流式输出、随时可中止。API Key 只存在服务端进程内存里，关进程即清空，不写文件、不写 localStorage。

<img src="assets/screenshots/llm-chat.png" width="880" alt="LLM 对话">

### 导出

原始 / 清洗后 / 带情感标注 / 摘要四份 JSON，点下载时现场从 SQLite 生成，服务端不留中间文件。

---

## 项目结构

```text
backend/
├── app/
│   ├── crawlers/   每个平台一个爬虫；auto.py 是并发聚合器
│   ├── search/     搜索引擎检索层（见该目录 README）
│   ├── analysis/   清洗、情感打分、词频、LLM 上下文
│   ├── hotspots/   首页热搜聚合
│   ├── routers/    REST + WebSocket
│   └── tasks/      任务流水线编排
└── tests/          自包含测试脚本（非 pytest）
frontend/           React + Vite + TypeScript，pnpm 管理
.env                数据源 Cookie（仅进程内使用，不落盘）
```

后端只提供 API + WebSocket，不 serve 前端；SPA 路由由前端处理。完整接口文档见 <http://127.0.0.1:8092/docs>。

> 每次后端启动会重置任务历史，运行期只保留最近 10 个任务。

---

## 测试

后端测试是**自包含脚本**，没有引入 pytest，直接跑即可：

```bash
cd backend
.venv/bin/python tests/run_all.py        # 全部
.venv/bin/python tests/test_search.py    # 单个模块
```

| 模块 | 覆盖 |
|---|---|
| `test_search.py` | 百度解析（广告过滤 / 占位地址 / 去重 / rank 连续性）、统一模型校验、provider 注册与重名冲突、聚合层的失败隔离与超时隔离 |
| `test_auto.py` | 聚合爬虫的来源均衡、跨源去重、慢源超时、配额满后取消 |
| `test_sources.py` | 豆瓣分页流式产出与并发、贴吧楼层兜底 |
| `test_pipeline.py` | `TaskManager` 全链路直到结果落库 |
| `test_search_pipeline.py` | 检索结果接入 summary 与 LLM 上下文，且**不进入情感分析** |

> 除 `test_sources.py` 会真实访问豆瓣/贴吧外，其余均不依赖网络。

前端只有静态检查：

```bash
cd frontend
pnpm typecheck
pnpm build
```

## 技术栈

FastAPI · Uvicorn · SQLite (aiosqlite) · httpx · BeautifulSoup · jieba · SnowNLP · wordcloud

React 18 · Vite 5 · TypeScript 5 · ECharts 5 · marked · DOMPurify

LLM 侧兼容任意 OpenAI 格式 endpoint（自带 Base URL + Key）。

---

## License

[MIT License](LICENSE)
