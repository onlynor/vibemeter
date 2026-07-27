import { useCallback, useEffect, useRef, useState } from "react";

const COLLAPSED_KEY = "vibe.llm.sidebar.collapsed";
const WIDTH_KEY = "vibe.llm.sidebar.width";
const MIN_W = 280;
const MAX_W = 720;
const DEFAULT_W = 440;

function clampWidth(width: number): number {
  const dynamicMax = Math.min(window.innerWidth * 0.5, MAX_W);
  return Math.max(MIN_W, Math.min(width, dynamicMax < MIN_W ? MIN_W : dynamicMax));
}

export function useLlmSidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [width, setWidth] = useState<number>(() => {
    try {
      const saved = parseFloat(localStorage.getItem(WIDTH_KEY) || "");
      return !isNaN(saved) && saved > 0 ? saved : DEFAULT_W;
    } catch {
      return DEFAULT_W;
    }
  });
  const sidebarRef = useRef<HTMLElement | null>(null);
  const draggingRef = useRef(false);

  // 窗口缩小时重新约束宽度
  useEffect(() => {
    function onResize() {
      setWidth((w) => {
        const clamped = clampWidth(w);
        return clamped;
      });
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // 持久化
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch { /* ignore */ }
  }, [collapsed]);

  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch { /* ignore */ }
  }, [width]);

  const startResize = useCallback((event: React.PointerEvent) => {
    if (event.button !== 0) return;
    const sidebar = sidebarRef.current;
    if (!sidebar) return;
    const startX = event.clientX;
    const startW = sidebar.getBoundingClientRect().width;
    draggingRef.current = true;
    let captured = false;
    try {
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      captured = true;
    } catch { /* ignore */ }

    function onMove(ev: PointerEvent) {
      if (!draggingRef.current) return;
      setWidth(clampWidth(startW + (ev.clientX - startX)));
    }
    function onUp(ev: PointerEvent) {
      draggingRef.current = false;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      try {
        if (captured) (event.currentTarget as HTMLElement).releasePointerCapture(ev.pointerId);
      } catch { /* ignore */ }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    event.preventDefault();
  }, []);

  const resetWidth = useCallback(() => {
    setWidth(DEFAULT_W);
  }, []);

  return { collapsed, setCollapsed, width, sidebarRef, startResize, resetWidth };
}