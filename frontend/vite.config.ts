import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期：把 /api、/ws 转发到 FastAPI 后端
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8092", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8092", ws: true, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});