import { useEffect, type RefObject } from "react";

/** 点击 ref 之外的区域时触发回调，用于下拉菜单点外部关闭 */
export function useClickAway(
  ref: RefObject<HTMLElement | null>,
  onClickAway: () => void,
  enabled = true
) {
  useEffect(() => {
    if (!enabled) return;
    function onPointerDown(event: PointerEvent) {
      const el = ref.current;
      if (el && !el.contains(event.target as Node)) {
        onClickAway();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [ref, onClickAway, enabled]);
}