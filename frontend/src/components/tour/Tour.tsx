import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { TOUR_STEPS } from "./steps";

/* Guided product tour. Starts automatically after every sign-in (Login queues it) and can be replayed
   from the menu. Each step opens its page and spotlights an element marked with data-tour="<name>". */

const PENDING_KEY = "pxp_tour_pending";

/** Ask the dashboard to start the tour the next time it mounts (called right after signing in). */
export function queueTour() {
  try {
    sessionStorage.setItem(PENDING_KEY, "1");
  } catch {
    /* storage disabled: no tour, nothing else breaks */
  }
}

function takePendingTour(): boolean {
  try {
    const pending = sessionStorage.getItem(PENDING_KEY) === "1";
    sessionStorage.removeItem(PENDING_KEY);
    return pending;
  } catch {
    return false;
  }
}

const TourContext = createContext<{ start: () => void; active: boolean }>({ start: () => {}, active: false });
export const useTour = () => useContext(TourContext);

export function TourProvider({ children }: { children: ReactNode }) {
  const [index, setIndex] = useState<number | null>(null);
  const start = useCallback(() => setIndex(0), []);
  // a ref, not state: survives StrictMode's double effect run so the queued tour is not lost
  const pending = useRef<boolean | null>(null);

  useEffect(() => {
    if (pending.current === null) pending.current = takePendingTour();
    if (!pending.current) return;
    const t = setTimeout(() => {
      pending.current = false;
      setIndex(0);
    }, 700);
    return () => clearTimeout(t);
  }, []);

  return (
    <TourContext.Provider value={{ start, active: index !== null }}>
      {children}
      {index !== null && <TourOverlay index={index} setIndex={setIndex} />}
    </TourContext.Provider>
  );
}

/* ───────────────────────── overlay ───────────────────────── */

interface Box {
  top: number;
  left: number;
  width: number;
  height: number;
}

const SPOT_PAD = 8; // breathing room around the highlighted element
const GAP = 14; // between spotlight and card
const MARGIN = 12; // from the viewport edge
const DIM = "hsl(240 10% 2% / 0.74)";

/** First element with a matching data-tour name that is actually rendered (desktop and mobile variants share names). */
function findTarget(names: string[]): HTMLElement | null {
  for (const name of names) {
    for (const el of document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`)) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
  }
  return null;
}

/** Scroll the target into the part of the screen the card and sticky header leave free. */
function scrollToTarget(el: HTMLElement, smooth: boolean) {
  if (el.closest("[data-tour-fixed]")) return; // sidebar / top bar never scroll
  const r = el.getBoundingClientRect();
  const top = window.innerWidth < 1024 ? 72 : 24;
  const bottom = window.innerWidth < 640 ? 280 : 24;
  const avail = window.innerHeight - top - bottom;
  const offset = r.height < avail ? top + (avail - r.height) / 2 : top;
  window.scrollTo({ top: Math.max(0, window.scrollY + r.top - offset), behavior: smooth ? "smooth" : "auto" });
}

const sameBox = (a: Box | null, b: Box) =>
  !!a &&
  Math.abs(a.top - b.top) < 0.5 &&
  Math.abs(a.left - b.left) < 0.5 &&
  Math.abs(a.width - b.width) < 0.5 &&
  Math.abs(a.height - b.height) < 0.5;

function TourOverlay({ index, setIndex }: { index: number; setIndex: (i: number | null) => void }) {
  const step = TOUR_STEPS[index];
  const total = TOUR_STEPS.length;
  const last = index === total - 1;
  const Icon = step.icon;

  const navigate = useNavigate();
  const { pathname } = useLocation();
  const reduce = useReducedMotion();

  const [rect, setRect] = useState<Box | null>(null);
  const [searching, setSearching] = useState(true);
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  const [card, setCard] = useState({ w: 360, h: 230 });
  const cardRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(document.activeElement);

  const close = useCallback(() => {
    setIndex(null);
    (opener.current as HTMLElement | null)?.focus?.({ preventScroll: true });
  }, [setIndex]);
  const go = useCallback(
    (i: number) => {
      if (i < 0) return;
      if (i >= total) close();
      else setIndex(i);
    },
    [close, setIndex, total],
  );

  // 1. open the page this step is about
  useEffect(() => {
    if (step.route && step.route !== pathname) navigate(step.route);
  }, [step, pathname, navigate]);

  // 2. find the target (it may render a moment after navigation), scroll to it, then follow it every frame
  useEffect(() => {
    setRect(null);
    setSearching(!!step.targets);
    if (!step.targets || (step.route && step.route !== pathname)) return;

    const t0 = performance.now();
    let el: HTMLElement | null = null;
    let scrolled = false;
    let raf = 0;
    const loop = () => {
      if (!el || !el.isConnected) {
        el = findTarget(step.targets!);
        if (!el) {
          if (performance.now() - t0 > 4000) {
            setSearching(false); // give up: show the card centred
            return;
          }
          raf = requestAnimationFrame(loop);
          return;
        }
      }
      if (!scrolled) {
        scrollToTarget(el, !reduce);
        scrolled = true;
      }
      const r = el.getBoundingClientRect();
      const box = { top: r.top, left: r.left, width: r.width, height: r.height };
      setRect((prev) => (sameBox(prev, box) ? prev : box));
      setSearching(false);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [step, pathname, reduce]);

  useEffect(() => {
    const onResize = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useLayoutEffect(() => {
    const el = cardRef.current;
    if (el && (el.offsetWidth !== card.w || el.offsetHeight !== card.h)) setCard({ w: el.offsetWidth, h: el.offsetHeight });
  });

  // keyboard: ← → to move, Esc to close, Tab stays inside the card
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") go(index + 1);
      else if (e.key === "ArrowLeft") go(index - 1);
      else if (e.key === "Tab" && cardRef.current) {
        const f = cardRef.current.querySelectorAll<HTMLElement>("button");
        if (!f.length) return;
        const first = f[0];
        const lastEl = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          lastEl.focus();
        } else if (!e.shiftKey && document.activeElement === lastEl) {
          e.preventDefault();
          first.focus();
        } else if (!cardRef.current.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, go, close]);

  useEffect(() => {
    if (!searching) nextRef.current?.focus({ preventScroll: true });
  }, [index, searching]);

  // spotlight, clamped to the viewport (tall panels are cut at the screen edge)
  const spot = rect && {
    left: Math.max(4, rect.left - SPOT_PAD),
    top: Math.max(4, rect.top - SPOT_PAD),
    right: Math.min(vp.w - 4, rect.left + rect.width + SPOT_PAD),
    bottom: Math.min(vp.h - 4, rect.top + rect.height + SPOT_PAD),
  };
  const docked = vp.w < 640; // phones: the card is a bottom sheet
  const pos = docked ? null : placeCard(spot, card, vp);

  return createPortal(
    <div className="fixed inset-0 z-[300]" role="presentation">
      {spot ? (
        <motion.div
          key={`spot-${step.id}`}
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25 }}
          className="pointer-events-none absolute rounded-xl ring-2 ring-primary/80"
          style={{
            left: spot.left,
            top: spot.top,
            width: spot.right - spot.left,
            height: spot.bottom - spot.top,
            boxShadow: `0 0 0 9999px ${DIM}, 0 0 36px hsl(var(--primary) / 0.35)`,
          }}
        />
      ) : (
        <div className="absolute inset-0 backdrop-blur-[2px]" style={{ background: DIM }} />
      )}

      {!searching && (
        <motion.div
          key={`card-${step.id}`}
          ref={cardRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby="tour-title"
          aria-describedby="tour-body"
          initial={reduce ? false : { opacity: 0, y: 8, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
          className={cn(
            "absolute rounded-2xl border border-white/10 bg-card/95 p-5 text-card-foreground shadow-[0_24px_80px_-12px_rgba(0,0,0,0.75)] backdrop-blur-xl",
            docked ? "inset-x-3 bottom-3" : "w-[360px]",
          )}
          style={pos ?? undefined}
        >
          <div className="flex items-start gap-3">
            <span
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary"
              aria-hidden
            >
              <Icon size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-primary" aria-live="polite">
                Step {index + 1} of {total}
              </div>
              <h2 id="tour-title" className="mt-0.5 text-base font-semibold tracking-tight">
                {step.title}
              </h2>
            </div>
            <button
              type="button"
              aria-label="Close tour"
              onClick={close}
              className="-mr-1.5 -mt-1.5 rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-white/[0.08] hover:text-foreground"
            >
              <X size={16} />
            </button>
          </div>

          <p id="tour-body" className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {step.body}
          </p>

          <div
            className="mt-4 h-1 overflow-hidden rounded-full bg-white/[0.06]"
            role="progressbar"
            aria-label="Tour progress"
            aria-valuemin={1}
            aria-valuemax={total}
            aria-valuenow={index + 1}
          >
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
              initial={false}
              animate={{ width: `${((index + 1) / total) * 100}%` }}
              transition={{ duration: reduce ? 0 : 0.35 }}
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {index === 0 ? (
              <Button variant="ghost" size="sm" onClick={close}>
                Skip tour
              </Button>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => go(index - 1)}>
                <ArrowLeft size={14} aria-hidden /> Back
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              {last && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    close();
                    navigate("/analyse");
                  }}
                >
                  Analyse a patch
                </Button>
              )}
              <Button ref={nextRef} variant="accent" size="sm" onClick={() => go(index + 1)}>
                {index === 0 ? "Start tour" : last ? "Finish" : "Next"}
                {!last && <ArrowRight size={14} aria-hidden />}
              </Button>
            </div>
          </div>
          {!docked && (
            <p className="mt-3 text-[11px] text-muted-foreground/70">
              <kbd className="font-mono">←</kbd> <kbd className="font-mono">→</kbd> to move · <kbd className="font-mono">Esc</kbd> to close
            </p>
          )}
        </motion.div>
      )}
    </div>,
    document.body,
  );
}

/** Put the card beside a narrow target (sidebar), else below, above or left of it; centred without a target. */
function placeCard(
  spot: { left: number; top: number; right: number; bottom: number } | null,
  card: { w: number; h: number },
  vp: { w: number; h: number },
): { left: number; top: number } {
  const clampX = (x: number) => Math.min(Math.max(x, MARGIN), vp.w - card.w - MARGIN);
  const clampY = (y: number) => Math.min(Math.max(y, MARGIN), vp.h - card.h - MARGIN);
  if (!spot) return { left: (vp.w - card.w) / 2, top: (vp.h - card.h) / 2 };

  const width = spot.right - spot.left;
  if (width < vp.w * 0.35 && vp.w - spot.right >= card.w + GAP + MARGIN)
    return { left: spot.right + GAP, top: clampY(spot.top) };
  if (vp.h - spot.bottom >= card.h + GAP + MARGIN) return { left: clampX(spot.left), top: spot.bottom + GAP };
  if (spot.top >= card.h + GAP + MARGIN) return { left: clampX(spot.left), top: spot.top - GAP - card.h };
  if (spot.left >= card.w + GAP + MARGIN) return { left: spot.left - GAP - card.w, top: clampY(spot.top) };
  return { left: vp.w - card.w - MARGIN, top: vp.h - card.h - MARGIN };
}
