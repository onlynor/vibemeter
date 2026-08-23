import { useTheme, type ThemeMode } from "../state/theme";

/** 三态循环：跟随系统 → 浅色 → 深色 → 跟随系统 */
const ORDER: ThemeMode[] = ["system", "light", "dark"];

const META: Record<ThemeMode, { icon: string; label: string }> = {
  system: { icon: "bi-circle-half", label: "跟随系统" },
  light: { icon: "bi-sun", label: "浅色" },
  dark: { icon: "bi-moon-stars", label: "深色" },
};

/**
 * 顶栏主题开关。
 *
 * 做成循环按钮而不是下拉：三种状态、切换频率低，多一层菜单不值当。当前
 * 状态由图标加文字给出，`title` 里写清再点一下会变成什么，用户不用靠试
 *
 * 这是 `useTheme` 唯一的使用点——那个 hook 每次挂载都会把解析后的主题写回
 * `<html>`，多处挂载虽然结果一致，但各自持有一份 state，容易看花眼
 */
export function ThemeToggle() {
  const { mode, resolved, setMode } = useTheme();
  const next = ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length];
  const meta = META[mode];
  const now = mode === "system" ? `（现为${resolved === "dark" ? "深色" : "浅色"}）` : "";

  return (
    <button
      type="button"
      className="site-nav-link theme-toggle"
      onClick={() => setMode(next)}
      title={`当前：${meta.label}${now}，点击切换到${META[next].label}`}
      aria-label={`主题：${meta.label}，点击切换到${META[next].label}`}
    >
      <i className={"bi " + meta.icon} aria-hidden="true" />
      <span className="theme-toggle-text">{meta.label}</span>
    </button>
  );
}
