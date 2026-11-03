import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function pct(x: number | null | undefined, digits = 1) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return `${(100 * x).toFixed(digits)}%`;
}

/** "12 s ago", "3 min ago", "2 h ago", "4 d ago" between an ISO time and a reference ISO time (default: now). */
export function timeAgo(iso: string | null | undefined, now?: string | number | Date): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const ref = now === undefined ? Date.now() : new Date(now).getTime();
  if (Number.isNaN(t) || Number.isNaN(ref)) return "—";
  const s = Math.max(0, Math.round((ref - t) / 1000));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

/** First 8 + last 6 characters of a long hash, for tables. */
export function shortHash(h: string | null | undefined): string {
  if (!h) return "—";
  return h.length <= 18 ? h : `${h.slice(0, 8)}…${h.slice(-6)}`;
}
