# VibeMeter · 舆情洞察员

[![GitHub](https://img.shields.io/badge/GitHub-onlynor%2Fvibemeter-181717?logo=github)](https://github.com/onlynor/vibemeter)

> 基于 **FastAPI + 原生前端** 的中文舆情情感分析小工具。
> 输入关键词，抓取 B 站 / 微博公开评论，完成清洗、分词、`SnowNLP` 情感打分，并在仪表板里展示情感分布、词云和代表性评论；可选挂上 LLM 做对话式解读。

---

## 功能

### 采集 & 分析

- **多源采集**：B 站 / 微博公开接口；`auto` 模式会按 B 站 → 微博 顺序聚合，单源首批 12 s 超时就跳下一个，不会无限等待
- **首页实时热搜**：聚合百度 / 微博，点一下"实时热搜"刷新缓存（5 分钟）
- **文本分析**：`jieba` 分词 + 自定义停用词 + `SnowNLP` 情感得分
- **结果展示**：情感分布饼图、全量高频词 Top 15 柱状图、正/负向词云、最正面/最负面代表评论原文、原帖列表（B 站视频可在页面内嵌播放）
- **任务进度**：WebSocket 实时推送采集与分析进度，状态条 + 当前阶段文字
- **导出**：自动产出 CSV / 词云图等归档文件，可在结果页直接下载

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

```text
.
├── src/
│   ├── app/                       # FastAPI 业务代码
│   │   ├── main.py                # ASGI app 实例
│   │   ├── config.py              # 路径常量、字体查找
│   │   ├── database.py            # SQLite schema + init
│   │   ├── schemas.py             # Pydantic 请求/响应模型
│   │   ├── llm_config_store.py    # 进程内 LLM 配置（替代 .env）
│   │   ├── analysis/              # 情感、词频、LLM 上下文/对话/SSE
│   │   ├── crawlers/              # auto / bilibili / weibo + hot fallback
│   │   ├── hotspots/              # 首页实时热搜聚合
│   │   ├── tasks/                 # 任务管理 + 进度调度
│   │   └── routers/               # api / pages / websocket 路由
│   ├── frontend/                  # 前端（模板 + 静态资源）
│   │   ├── templates/             # base / index / result 三个页面
│   │   └── static/css|js/         # style.css + dashboard/index/result_chat/common
│   ├── data/                      # SQLite、停用词、自定义词典、导出
│   ├── scripts/                   # 离线 smoke test
│   └── run.py                     # 本地开发入口
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── requirements.txt
```

---

## 本地运行

任选其一（推荐用 `uv`）：

```powershell
# 1. 最简，用项目自带入口
uv run python src/run.py

# 2. 直接 uvicorn
uv run uvicorn --app-dir src app.main:app --host 127.0.0.1 --port 8092 --reload

# 3. 传统 venv + pip
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python src/run.py
```

打开 [http://127.0.0.1:8092](http://127.0.0.1:8092)。

> **每次启动会重置任务历史**：[main.py](src/app/main.py) 的 lifespan 会清空 `data/sentiment.db` 和 `exports/`，保证从干净状态开始。

### Docker

```powershell
docker compose up --build
```

---


## 主要接口

### 页面

- `GET /` — 首页（关键词表单 + 实时热搜 + 最近任务）
- `GET /result/{task_id}` — 分析结果仪表板

### 任务 & 数据

- `POST /api/task` — 创建分析任务
- `GET /api/task/{task_id}/status` — 任务状态
- `GET /api/tasks/history` — 最近 10 个任务
- `GET /api/hotspots` — 首页实时热搜（5 分钟缓存）
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
| 模板 | Jinja2 |
| 前端 | 原生 HTML/CSS/JS + Bootstrap 5 + ECharts + marked.js |
| 中文分词 | jieba |
| 情感打分 | SnowNLP |
| 词云 | wordcloud + Pillow |
| LLM | 任意 OpenAI 兼容 endpoint（用户自带 Base URL + Key） |

---

## License

MIT
