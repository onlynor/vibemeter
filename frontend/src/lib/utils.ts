import { marked } from "marked";
import DOMPurify from "dompurify";
import type { Platform } from "../api/types";

export function platformLabel(platform: Platform | string): string {
  const map: Record<string, string> = {
    auto: "聚合搜索",
    bilibili: "B站",
    weibo: "微博",
    douban: "豆瓣",
    zhihu: "知乎",
    tieba: "贴吧",
    baidu: "百度",
  };
  return map[platform] ?? platform;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

export function formatTaskNo(taskNo: number | null | undefined): string {
  const num = Number(taskNo || 0);
  if (!num) return "-";
  return "#" + String(num).padStart(4, "0");
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const normalized = String(value).replace(" ", "T");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ");
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

const ESC_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(text: unknown): string {
  return String(text ?? "")
    .replace(/[&<>"']/g, (ch) => ESC_MAP[ch] || ch);
}

/** 安全地把 Markdown 渲染为 HTML：marked + DOMPurify 双保险 */
export function renderMarkdown(text: string): string {
  const raw = String(text ?? "");
  try {
    // async: false 保证同步返回，marked 的类型签名仍是联合类型，故断言
    const html = marked.parse(raw, { breaks: true, gfm: true, async: false }) as string;
    return DOMPurify.sanitize(html);
  } catch {
    return escapeHtml(raw).replace(/\n/g, "<br>");
  }
}

