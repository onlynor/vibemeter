# vibemeter frontend

React 18 + Vite + TypeScript 实现，由 [pnpm](https://pnpm.io) 管理依赖。前端与后端（`backend/`）独立。

## 与后端的关系

- `/api/*`、`/ws/*` 由 `backend/`（FastAPI）提供
- **开发期**：通过 `vite.config.ts` 的 proxy 把 `/api`、`/ws` 转发到 `http://127.0.0.1:8092`
- **生产期**：构建产物 `dist/` 由 `nginx:alpine` 容器托管（见 `nginx.conf`），nginx 把 `/api`、`/ws` 反代到 backend 容器 `:8092`

## 目录

```text
frontend/
├── src/
│   ├── api/          # 类型 + 客户端 + SSE 流式封装
│   ├── components/   # 共享组件（LlmSidebar / ChatPanel / Charts / ...）
│   ├── lib/          # 工具与 markdown 渲染
│   ├── pages/        # HomePage / ResultPage / NotFoundPage
│   ├── state/        # llmConfig / sidebar 状态
│   ├── App.tsx
│   └── main.tsx
├── nginx.conf        # 生产容器 nginx 配置（反代 /api、/ws + SPA fallback）
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml   # 构建脚本白名单（esbuild）
├── vite.config.ts
└── tsconfig.json
```

## 功能要点

- 首页：关键词表单、平台/数量选择、实时热搜、最近任务
- 结果页：进度条 + WebSocket 推送、统计卡片、ECharts 饼图/柱状图、词云、最正/最负评论、原帖列表（含 B 站视频内嵌）、导出归档、XML 上下文复制
- LLM 侧栏：拖拽调宽 + 双击重置 + 折叠态 + 宽度持久化（首页/结果页共享 `LlmSidebar` 外壳）
- LLM 配置：服务端进程内存持久化、测试连接（首页/结果页共享 `LlmConfigForm`）
- LLM 对话：流式 SSE + AbortController + 半成品回滚 + sessionStorage 历史（`ChatPanel` + `api/chat.ts`）

## 开发

```bash
cd frontend
pnpm install
pnpm dev       # http://127.0.0.1:5173，自动反代 /api、/ws 到 FastAPI :8092
pnpm build     # 产物输出到 dist/，供 nginx 容器托管
pnpm typecheck
```

> pnpm 10+ 默认禁止依赖运行构建脚本。`pnpm-workspace.yaml` 已白名单 `esbuild`；若仍报 `ERR_PNPM_IGNORED_BUILDS`，执行一次 `pnpm approve-builds`。

需先在另一终端起后端：

```bash
cd backend
uv run python run.py
```

## 生产部署

由项目根 `Dockerfile` 的 `frontend` target 构建：

1. `node:22-slim` 阶段用 pnpm 安装依赖并 `pnpm build`
2. 产物拷进 `nginx:alpine` 镜像，配置来自 `nginx.conf`

详见根目录 `docker-compose.yml` 与 [README](../README.md#docker-部署)。

## 已知限制

- 产物整体 ~1.2MB（echarts 内联）。换 `echarts/core` 按需引入可压到 ~400KB
- 仅一个 SPA 入口；没有路由级懒加载；ECharts 两个组件可后续 `lazy()` 拆