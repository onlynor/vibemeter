# 单一 Dockerfile，用 build target 区分后端/前端镜像，配合 docker-compose.yml 编排。
#
#   docker build --target backend -t vibemeter-backend .
#   docker build --target frontend -t vibemeter-frontend .
#
# 或直接：
#   docker compose up --build

# ===== Stage 0: 公共基础 =====
FROM scratch AS base
# 占位 stage，便于把后续 target 平铺在同一文件里。

# ============================================================================
# target: backend
# FastAPI + uvicorn，纯 API/WS，不 serve 前端
# ============================================================================
FROM python:3.11-slim AS backend

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SENTIMENT_FONT_PATH=/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/

WORKDIR /app/backend
RUN mkdir -p data

EXPOSE 8092

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8092"]


# ============================================================================
# target: frontend
# 构建 Vite 静态产物后用 nginx 托管，并反代 /api、/ws 到 backend 容器
# ============================================================================
# 依赖与构建都交给 bun：镜像自带运行时，不需要 Node + corepack 两层引导。
# 构建仍是 Vite（bun 只当包管理器与脚本执行器），产物与本地 bun run build 一致。
#
# 用 Debian 版而不是 -alpine：这一层构建完就被丢掉，最终镜像是 nginx:alpine，
# 所以体积在这里没有意义；glibc 则与本地开发、与锁文件里解析出的原生二进制
# （rollup 的 linux-x64-gnu）一致，少一类只在容器里复现的问题。
FROM oven/bun:1 AS frontend-build
# oven/bun 镜像默认 USER bun，而 WORKDIR / COPY 建出来的目录属 root，
# 直接装依赖会写不进 node_modules。构建阶段用 root，不影响最终镜像。
USER root
WORKDIR /build
# 先拷清单文件 + .npmrc（registry 配置），让依赖层可被 Docker 缓存复用
COPY .npmrc ./
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
# 再拷源码，仅源码变更才触发后续 build 层
COPY frontend/ ./
RUN bun run build

# 复制一份纯静态产物到独立 layer，方便前端 target 复用
FROM alpine:3 AS frontend-static
COPY --from=frontend-build /build/dist /dist

FROM nginx:alpine AS frontend
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /build/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]