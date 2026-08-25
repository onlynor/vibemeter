# vibemeter frontend

React 18 + Vite + TypeScript 实现，由 [bun](https://bun.com) 管理依赖并执行脚本（构建仍是 Vite）。前端与后端（`backend/`）独立。

## 与后端的关系

- `/api/*`、`/ws/*` 由 `backend/`（FastAPI）提供
- **开发期**：通过 `vite.config.ts` 的 proxy 把 `/api`、`/ws` 转发到 `http://127.0.0.1:8092`
- **生产期**：构建产物 `dist/` 由 `nginx:alpine` 容器托管（见 `nginx.conf`），nginx 把 `/api`、`/ws` 反代到 backend 容器 `:8092`

## 目录

```text
frontend/
├── src/
│   ├── api/          # 类型 + 客户端 + SSE 流式封装
│   ├── components/
│   │   ├── AnalysisForm/   # 首页表单：KeywordInput / SourceSelector /
│   │   │                   #   RetrievalSettings / AnalysisOptions
│   │   ├── Dashboard/      # 首页监测组件：HotTopics / RecentTasks
│   │   ├── Charts/         # ECharts 封装
│   │   └── ...             # LlmSidebar / ChatPanel / LlmConfigForm / ...
│   ├── lib/          # 工具与 markdown 渲染
│   ├── pages/        # HomePage / ResultPage / NotFoundPage
│   ├── state/        # llmConfig / sidebar / analysisForm 状态
│   ├── App.tsx
│   └── main.tsx
├── nginx.conf        # 生产容器 nginx 配置（反代 /api、/ws + SPA fallback）
├── package.json          # trustedDependencies 白名单安装脚本（esbuild）
├── bun.lock              # 文本锁文件，需入库
├── vite.config.ts
└── tsconfig.json
```

## 视觉体系

`src/styles.css` 是一套 token 驱动的设计系统，取向参考 apple.com：`#fbfbfd` 页面底色、
纯白卡片、`rgba(0,0,0,.09)` 发丝分隔线、胶囊按钮、`#0071e3` 强调色、标题收紧字距、
毛玻璃顶栏。Bootstrap 5.3 仍从 CDN 引入，**只覆盖观感、不改组件类名与结构**，
因此改动标记结构是安全的。新 UI 请引用 `--*` 变量而不是写死颜色。

ECharts 在 canvas 里绘制，读不到 CSS 变量，`components/Charts/echarts.ts` 的
`chartPalette()` 在每次渲染时从 `:root` 上读令牌的计算值——样式表仍是唯一的配色来源，
主题切换只需重新 `setOption`（图表组件把 `useThemeTick()` 放进了依赖）。

**深色主题**：深色是一张替换用的令牌表，挂在 `:root[data-theme="dark"]` 上，组件规则一条都不复制。
`<html data-theme>` 由 `index.html` 的内联脚本在首帧前写好（晚一步就会闪一帧白底），
之后由 `state/theme.ts` 维护：三态偏好（跟随系统 / 浅色 / 深色）存在 `vibe.theme.v1`，
「跟随系统」时监听 `prefers-color-scheme` 变化。**样式表里没有 `prefers-color-scheme` 块是有意的**——
系统偏好在 JS 里解析成具体值，手动选择与系统默认因此共用一条路径。
新写 UI 时：颜色一律用 `--*` 令牌，实在不是令牌的（毛玻璃、代码块、骨架高光、强调色上的文字）
就补一个令牌，别写字面量。词云是后端渲染的白底 PNG，深色下保留浅色底板（`.wordcloud-frame`），
把它当一张图，而不是去反相。

首页骨架在 `styles.css` 的「首页布局」一节：`.home-layout` 竖排，`.home-hero`
在 ≥992px 时把标题与「执行计划」磁贴分成两列，`.home-grid` 在 ≥1200px 时分成
配置列 + `.home-rail` 监测列。`.home-grid` 必须保留 `align-items: start`——
grid 子项默认拉伸到整行高度，一拉伸 `.home-rail` 的 `position: sticky` 就失效。
窄屏两处都塌成单列，吸顶与列表内滚动一并关闭。

## 功能要点

- 首页监测台：关键词 + 检索模式卡片、数据源多选（采集平台 / 检索增强分组）、可折叠的高级检索与分析选项、数据源可用性检测；实时热搜支持来源筛选、定时刷新与趋势标记；最近任务卡片可回看或本地隐藏
- 首页布局：左右两栏工作台——标题右侧是随表单实时变化的「执行计划」磁贴，左列配置卡、右列吸顶监测栏（实时热搜 + 数据源可用性），最近任务整行铺在下方
- 结果页：进度条 + WebSocket 推送、统计卡片、**平台内容来源**（B 站/贴吧/微博原帖，首条视频默认展开播放器）、样本构成、**事件背景**（百度/必应，默认展开，带摘要的结果优先）、LLM 解读、ECharts 饼图/柱状图、词云、最正/最负评论、导出归档、XML 上下文复制
- 主题：顶栏三态开关（跟随系统 / 浅色 / 深色），首帧前由内联脚本定色，图表与原生控件跟着换

> **表单选项与后端契约**：`POST /api/task` 接受
> `keyword / platform / count / platforms[] / search_providers[] / llm_*`。
> `state/analysisForm.ts` 为每个选项标注 `backed`：`true` 表示真实映射到请求字段
> （检索模式→采集量、采集平台→`platform` + `platforms[]`、检索源→`search_providers[]`、
> LLM 分析类型→提问模板），`false` 表示仅保存前端偏好，界面上显示「前端预设」徽标，
> 代码里带 `TODO(backend)` 注明后端需要补什么。
> 热搜趋势由前端跨刷新对比排名得出，任务「删除」只在本机隐藏（后端无删除接口）。
>
> **结果页的顺序是有意的**：平台内容（评论的出处）在前，搜索引擎结果作为事件背景紧随其后，
> 默认展开、带摘要的排前面。两个极端都被反馈过：搜索结果抢在最前会显得"这工具只是去搜了一下"，
> 折叠到页面底部又会让人以为检索层根本没跑。首条可内嵌内容默认展开播放器，B 站播放器会自动播放——
> 这是因为它落在首屏；若哪天这张卡被挪到折叠线以下，请同时给 `embed_url` 补
> `&autoplay=0`，别让声音从看不见的地方传出来。
- LLM 侧栏：拖拽调宽 + 双击重置 + 折叠态 + 宽度持久化（首页/结果页共享 `LlmSidebar` 外壳）
- LLM 配置：服务端进程内存持久化、测试连接（首页/结果页共享 `LlmConfigForm`）
- LLM 对话：流式 SSE + AbortController + 半成品回滚 + sessionStorage 历史（`ChatPanel` + `api/chat.ts`）

## 文案约定

界面上的中文单句**不加句末的「。」**——标签、提示、卡片说明、空状态、一行的提醒都算。
多句文案保留句中的「。」，只去掉最后一个。这条只管界面显示：
`LLM_ANALYSIS_TYPES[].template` 这类发给模型的提问模板属于载荷，标点是指令的一部分，原样保留。

## 开发

```bash
cd frontend
bun install
bun run dev       # http://127.0.0.1:5173，自动反代 /api、/ws 到 FastAPI :8092
bun run build     # 产物输出到 dist/，供 nginx 容器托管
bun run typecheck
```

> bun 与 pnpm 一样默认禁止依赖执行安装脚本，白名单改由 `package.json` 的
> `trustedDependencies` 声明（当前只有 `esbuild`，它需要落地平台二进制）。
> 查看被拦下的包：`bun pm untrusted`。
>
> 仍然可以用 npm/pnpm 装依赖——`package.json` 没有任何 bun 专属字段，
> 只是 CI 与 Dockerfile 认 `bun.lock`，混用会让锁文件失去意义。

需先在另一终端起后端：

```bash
cd backend
uv run python run.py
```

## 生产部署

由项目根 `Dockerfile` 的 `frontend` target 构建：

1. `oven/bun:1` 阶段 `bun install --frozen-lockfile` 后 `bun run build`
   （用 Debian 版而非 alpine：该层构建完即丢弃，glibc 与本地一致，少一类只在容器里复现的原生二进制问题；
   镜像默认 `USER bun`，构建阶段显式切回 root，否则装依赖会写不进 `node_modules`）
2. 产物拷进 `nginx:alpine` 镜像，配置来自 `nginx.conf`

详见根目录 `docker-compose.yml` 与 [README](../README.md#docker-部署)。

## 已知限制

- 产物整体 ~1.2MB（echarts 内联）。换 `echarts/core` 按需引入可压到 ~400KB
- 仅一个 SPA 入口；没有路由级懒加载；ECharts 两个组件可后续 `lazy()` 拆