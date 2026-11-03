import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Tone = "ok" | "bad" | "info";
interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: Tone;
}

const ToastContext = createContext<(t: Omit<ToastItem, "id">) => void>(() => {});

/** `const toast = useToast(); toast({ tone: "ok", title: "Done", description: "…" })` */
export const useToast = () => useContext(ToastContext);

const ICON = { ok: CheckCircle2, bad: XCircle, info: Info } as const;
const COLOR = { ok: "text-verdict-ok", bad: "text-verdict-bad", info: "text-verdict-info" } as const;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs.slice(-3), { ...t, id }]);
      setTimeout(() => dismiss(id), 5500);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(92vw,380px)] flex-col gap-2"
      >
        <AnimatePresence>
          {items.map((t) => {
            const Icon = ICON[t.tone];
            return (
              <motion.div
                key={t.id}
                role="status"
                layout
                initial={{ opacity: 0, y: 16, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 24 }}
                transition={{ duration: 0.25 }}
                className="pointer-events-auto flex items-start gap-3 rounded-xl border border-white/10 bg-card/95 p-3.5 shadow-2xl backdrop-blur"
              >
                <Icon size={18} className={cn("mt-0.5 shrink-0", COLOR[t.tone])} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{t.title}</div>
                  {t.description && <div className="mt-0.5 break-words text-xs text-muted-foreground">{t.description}</div>}
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  aria-label="Dismiss notification"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X size={14} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
