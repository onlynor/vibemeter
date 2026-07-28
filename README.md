# VibeMeter · 舆情洞察员

[![GitHub](https://img.shields.io/badge/GitHub-onlynor%2Fvibemeter-181717?logo=github)](https://github.com/onlynor/vibemeter)

> 基于 **FastAPI（后端）+ React/Vite（前端）** 的中文舆情情感分析小工具。
> 输入关键词，抓取 B 站 / 微博等公开评论，完成清洗、分词、`SnowNLP` 情感打分，并在仪表板里展示情感分布、词云和代表性评论；可选挂上 LLM 做对话式解读。

---

## 功能

### 采集 & 分析

- **多源采集**：B 站 / 微博 / 百度 / 知乎 / 头条公开接口；`auto` 模式多源并发采集，单源首批 8 s 超时自动跳过，不会无限等待
- **文本分析**：`jieba` 分词 + 词性过滤（仅保留名词/动词/形容词）+ 自定义停用词 + `SnowNLP` 情感得分
- **数据清洗**：自动过滤饭圈短评、清除各平台 UI 残留文本（"展开全文""转发微博"等）
- **结果展示**：情感分布饼图、全量高频词 Top 15 柱状图、正/负向词云（差减值排序，去除双边争议词）、最正面/最负面代表评论原文、原帖列表（B 站视频可在页面内嵌播放）
- **任务进度**：WebSocket 实时推送采集与分析进度，状态条 + 当前阶段文字
- **导出**：自动产出 CSV / JSON 归档文件（可在结果页下载），同时在 `data/output/` 下保存饼图、词云 PNG、代表性评论 JSON

### LLM 解读（可选）

- **侧边栏对话**：在 result 页右侧 LLM 面板里直接问问题，模型基于本次任务的结构化数据回答；支持 Markdown 排版、引用块、表格
- **流式输出 (SSE)**：边写边显示，"发送"按钮在生成中会变红色"停止"，随时可中止
- **不留痕**：中止 / 网络断开 / 出错时，会从内存和 sessionStorage 中删除当前那对消息，刷新后看不到半截答
- **配置不落盘**：API Key 等只保存在**服务端进程内存**里（关闭进程即清空），刷新页面、跨 tab 都会自动回填，但绝不写文件系统、不写浏览器 localStorage
- **测试连接**：填好 Base URL + 模型名后可单点 ping，前端立刻显示模型回包预览
- **XML 上下文卡**：result 页显示本次任务实际投喂给模型的 XML 提示词内容，可一键复制

### 界面

- LLM 侧边栏可**拖拽调整宽度**（右边缘 6 px 把手，双击重置，宽度持久化在 localStorage，会 clamp 在 `[280px, min(50vw, 720px)]`）
- LLM 侧边栏可**折叠**，鼠标点折叠按钮，可在结果页和首页之间共享展开状态
- 首页底部展示**最近任务**，没有历史会显示空状态提示——不需要先建任务才能看历史
- 任务详情页顶部也有最近任务的横向切换列表
- 暗色 navbar + 圆角卡片，1280 px 以上视口自动放宽内容区

---

## 项目结构

前后端分离：`backend/`（Python，由 [uv](https://github.com/astral-sh/uv) 管理虚拟环境）与 `frontend/`（React，由 [pnpm](https://pnpm.io) 管理）。

- **本地开发**：两个独立进程，互不干扰——后端 `uv run python run.py` 起在 :8092，前端 `pnpm dev` 起在 :5173，Vite 自动反代 `/api`、`/ws` 到后端。
- **生产部署**：两个 Docker 容器——后端跑 FastAPI（纯 API + WebSocket），前端用 `nginx` 托管 Vite 构建产物并把 `/api`、`/ws` 反代到后端容器。

```text
.
├── backend/                      # 后端（FastAPI，uv 管理）
│   ├── app/                      # 业务代码
│   │   ├── main.py               # ASGI app 实例（只提供 API + WebSocket，不 serve 前端）
│   │   ├── config.py             # 路径常量、字体查找
│   │   ├── database.py           # SQLite schema + init
│   │   ├── schemas.py            # Pydantic 请求/响应模型
│   │   ├── llm_config_store.py   # 进程内 LLM 配置（替代 .env）
│   │   ├── analysis/             # 情感、词频、LLM 上下文/对话/SSE
│   │   ├── crawlers/             # auto / bilibili / weibo / baidu / zhihu / toutiao + hot fallback
│   │   ├── hotspots/             # 实时热搜
│   │   ├── tasks/                # 任务管理 + 进度调度
│   │   └── routers/              # api / websocket 路由
│   ├── data/                     # SQLite、停用词、原始/清洗/导出/输出数据（运行时生成，.gitignore）
│   ├── run.py                    # 本地开发入口
│   ├── pyproject.toml            # uv 项目定义
│   ├── uv.lock                   # uv 锁文件
│   ├── requirements.txt          # pip 兼容依赖清单（Docker 用）
│   └── .env.example              # 环境变量样例
├── frontend/                     # 前端（React + Vite + TypeScript，pnpm 管理）
│   ├── src/                      # 组件 / 页面 / api / 状态
│   ├── nginx.conf                # 生产容器 nginx 配置（反代 /api、/ws + SPA fallback）
│   ├── package.json              # pnpm 项目定义
│   ├── pnpm-lock.yaml            # pnpm 锁文件
│   ├── pnpm-workspace.yaml       # 构建脚本白名单（esbuild）
│   ├── vite.config.ts            # Vite 配置（dev 反代 /api、/ws）
│   └── dist/                     # 构建产物（.gitignore，生产由 nginx 托管）
├── .npmrc                        # npm/pnpm 镜像源（npmmirror）
├── Dockerfile                    # 多 target：backend / frontend 两个构建阶段
├── docker-compose.yml            # 编排两个容器：backend:8092 + frontend:80
└── README.md
```

---

## 本地运行

### 前置要求

- [uv](https://github.com/astral-sh/uv)（管理 Python 虚拟环境与依赖）
- [pnpm](https://pnpm.io)（管理前端依赖）
- Python >= 3.10、Node >= 22（pnpm 11 要求 Node >= 22.13）

### 一键起后端 + 前端开发服务器

两个终端：

```bash
# 终端 A：后端（uv 管理虚拟环境，首次会自动创建 .venv 并同步依赖）
cd backend
uv run python run.py          # http://127.0.0.1:8092

# 终端 B：前端 HMR（pnpm 管理）
cd frontend
pnpm install                  # 首次安装；若提示 ignored build scripts，见下方 FAQ
pnpm dev                      # http://127.0.0.1:5173，自动反代 /api、/ws 到 :8092
```

开发期无需构建前端，Vite dev server 直连同后端。浏览器打开 [http://127.0.0.1:5173](http://127.0.0.1:5173) 即可。

> 也可以从项目根目录统一启后端：`uv run --directory backend python run.py`。

### 生产构建（前后端各自构建）

```bash
# 1. 构建前端
cd frontend
pnpm install
pnpm build                    # 产物输出到 frontend/dist/

# 2. 起后端
uv run --directory backend python run.py
```

生产模式下前端由 nginx 托管（见 Docker 部署），后端只提供 API。

> **每次启动会重置任务历史**：[backend/app/main.py](backend/app/main.py) 的 lifespan 会清空 `backend/data/sentiment.db`，保证从干净状态开始。`backend/data/raw/`、`backend/data/cleaned/`、`backend/data/exports/`、`backend/data/output/` 中的数据文件会保留。

---

## Docker 部署

两个容器，由 `docker-compose.yml` 编排：

| 容器 | 基础镜像 | 端口 | 说明 |
|---|---|---|---|
| `vibemeter-backend` | `python:3.11-slim` | **8092** | FastAPI + uvicorn，纯 API/WebSocket |
| `vibemeter-frontend` | `nginx:alpine`（前端产物由 `node:22-slim` 构建） | **8080 → 80** | nginx 托管 SPA，反代 `/api`、`/ws` 到 backend 容器 |

```bash
docker compose up --build
```

启动后浏览器打开 [http://localhost:8080](http://localhost:8080) 即可访问前端，nginx 会把 `/api/*`、`/ws/*` 透明转发到后端 `:8092`。

> `backend/data` 通过 volume 挂载持久化；DB 仍按 lifespan 在每次容器启动时重置。

---

## 主要接口

### 任务 & 数据

- `POST /api/task` — 创建分析任务
- `GET /api/task/{task_id}/status` — 任务状态
- `GET /api/tasks/history` — 最近 10 个任务
- `GET /api/result/{task_id}/summary` — 分析摘要
- `GET /api/result/{task_id}/sentiment-pie` — 情感分布饼图数据
- `GET /api/result/{task_id}/top-words` — Top 高频词
- `GET /api/result/{task_id}/wordcloud/positive` — 正向词云
- `GET /api/result/{task_id}/wordcloud/negative` — 负向词云
- `GET /api/result/{task_id}/exports` — 导出文件列表
- `GET /api/result/{task_id}/xml-context` — 本次任务的 XML 模型上下文
- `WS  /ws/task/{task_id}` — 进度推送

### LLM

- `GET  /api/llm/config` — 读取进程内存里的 LLM 配置
- `POST /api/llm/config` — 写入进程内存里的 LLM 配置
- `POST /api/llm/test` — 用最小请求 ping LLM endpoint
- `POST /api/result/{task_id}/llm-chat` — 非流式 LLM 对话
- `POST /api/result/{task_id}/llm-chat-stream` — SSE 流式 LLM 对话

---

## 技术栈

| 层 | 选型 |
|---|---|
| Web 框架 | FastAPI + Uvicorn (ASGI) + WebSocket |
| 数据库 | SQLite (aiosqlite) |
| 包管理 | 后端 [uv](https://github.com/astral-sh/uv)，前端 [pnpm](https://pnpm.io) |
| 前端 | React 18 + Vite + TypeScript + ECharts + marked + DOMPurify |
| 生产托管 | nginx（前端 SPA）+ FastAPI（后端 API） |
| 中文分词 | jieba |
| 情感打分 | SnowNLP |
| 词云 | wordcloud + Pillow |
| LLM | 任意 OpenAI 兼容 endpoint（用户自带 Base URL + Key） |

---

## FAQ

**`pnpm install` 报 `ERR_PNPM_IGNORED_BUILDS: esbuild`？**

pnpm 10+ 默认不允许依赖运行构建脚本。本项目已在 `frontend/pnpm-workspace.yaml` 里白名单了 `esbuild`，正常 `pnpm install` 即可。若仍报错，在 `frontend/` 下执行一次：

```bash
pnpm approve-builds
```

**`uv run python backend/run.py` 报 `No module named 'uvicorn'`？**

`uv` 需要在 `backend/`（`pyproject.toml` 所在目录）运行，否则找不到依赖。正确姿势：

```bash
cd backend && uv run python run.py
# 或
uv run --directory backend python run.py
```

---

## License

[MIT License](LICENSE)