import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from "motion/react";
import { api, API_BASE, setApiBase } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/Logo";
import { ToastProvider } from "@/components/ui/toast";
import { TourProvider, useTour } from "@/components/tour/Tour";
import {
  BarChart3,
  BookOpen,
  Compass,
  FlaskConical,
  GitBranch,
  Globe2,
  Home,
  Info,
  LogOut,
  Menu,
  RadioTower,
  ScanSearch,
  ScrollText,
  Settings,
  X,
  type LucideIcon,
} from "lucide-react";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Monitor",
    items: [
      { to: "/", label: "Overview", icon: Home, end: true },
      { to: "/live", label: "Live link", icon: Globe2 },
      { to: "/audit", label: "Audit log", icon: ScrollText },
      { to: "/station", label: "Station", icon: RadioTower },
    ],
  },
  {
    group: "Verify",
    items: [
      { to: "/analyse", label: "Analyse", icon: ScanSearch },
      { to: "/provenance", label: "Provenance", icon: GitBranch },
    ],
  },
  {
    group: "Validate",
    items: [
      { to: "/lab", label: "Attack lab", icon: FlaskConical },
      { to: "/attacks", label: "Attack guide", icon: BookOpen },
      { to: "/results", label: "Results", icon: BarChart3 },
    ],
  },
  { group: "Docs", items: [{ to: "/about", label: "About", icon: Info }] },
];

type Health = Record<string, unknown> | null;

/** Polls the ground-station API so the status dot stays truthful while the dashboard is open. */
function useHealth() {
  const [health, setHealth] = useState<Health>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((h) => {
          if (!alive) return;
          setHealth(h);
          setErr(false);
        })
        .catch(() => alive && setErr(true));
    load();
    const iv = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);
  return { health, err };
}

export function Layout() {
  return (
    <ToastProvider>
      <TourProvider>
        <Shell />
      </TourProvider>
    </ToastProvider>
  );
}

function Shell() {
  const { pathname } = useLocation();
  const reduce = useReducedMotion();
  const { health, err } = useHealth();
  const [drawer, setDrawer] = useState(false);
  const { user } = useAuth();

  // close the drawer on navigation and with Esc; lock page scroll behind it
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [drawer]);

  return (
    <div className="relative min-h-screen">
      {/* backdrop: engineering grid + two soft colour glows */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="bg-grid absolute inset-x-0 top-0 h-[640px]" />
        <div className="absolute -top-40 left-1/2 h-[520px] w-[900px] -translate-x-1/2 rounded-full bg-primary/[0.12] blur-[120px]" />
        <div className="absolute right-[-10%] top-[30%] h-[420px] w-[520px] rounded-full bg-accent/[0.08] blur-[130px]" />
      </div>

      {/* desktop sidebar */}
      <aside
        data-tour-fixed
        className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-white/[0.06] bg-background/70 backdrop-blur-xl lg:flex"
        aria-label="Main"
      >
        <SidebarContent id="desk" health={health} err={err} />
      </aside>

      {/* mobile / tablet top bar */}
      <header
        data-tour-fixed
        className="glass sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-white/[0.06] px-3 sm:px-4 lg:hidden"
      >
        <Button
          variant="ghost"
          size="icon"
          aria-label="Open menu"
          aria-expanded={drawer}
          aria-controls="mobile-drawer"
          onClick={() => setDrawer(true)}
          data-tour="nav"
        >
          <Menu size={18} />
        </Button>
        <NavLink to="/" className="flex items-center gap-2" aria-label="PixelProof home">
          <Logo size={24} />
          <span className="text-sm font-semibold tracking-tight">PixelProof</span>
        </NavLink>
        <div className="ml-auto flex items-center gap-1.5">
          <span data-tour="status" className="flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-muted-foreground">
            <StatusDot health={health} err={err} />
            <span className="hidden sm:inline">{statusText(health, err)}</span>
          </span>
          {user && (
            <button
              type="button"
              onClick={() => setDrawer(true)}
              aria-label={`Account: ${user.name}`}
              data-tour="account"
              className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Avatar name={user.name} />
            </button>
          )}
        </div>
      </header>

      {/* mobile drawer */}
      <AnimatePresence>
        {drawer && (
          <div className="fixed inset-0 z-50 lg:hidden" id="mobile-drawer">
            <motion.button
              aria-label="Close menu"
              className="absolute inset-0 cursor-default bg-black/60 backdrop-blur-sm"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDrawer(false)}
            />
            <motion.aside
              role="dialog"
              aria-modal="true"
              aria-label="Menu"
              className="absolute inset-y-0 left-0 flex w-[min(18rem,86vw)] border-r border-white/10 bg-background shadow-2xl"
              initial={reduce ? { opacity: 0 } : { x: "-100%" }}
              animate={reduce ? { opacity: 1 } : { x: 0 }}
              exit={reduce ? { opacity: 0 } : { x: "-100%" }}
              transition={{ type: "tween", duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            >
              <SidebarContent id="mob" health={health} err={err} onClose={() => setDrawer(false)} />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>

      <div className="lg:pl-64">
        <motion.main
          key={pathname}
          initial={reduce ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="mx-auto w-full max-w-6xl px-4 pb-20 pt-6 sm:px-6 sm:pt-8 lg:px-10 lg:pt-12"
        >
          <Outlet />
        </motion.main>

        <footer className="border-t border-white/[0.06] px-4 py-6 text-center text-xs leading-relaxed text-muted-foreground">
          PixelProof · TSYP14 Track 3 “Trust the Pixel” · Phase 1 (anonymous) · every figure is read from{" "}
          <code>results/</code>
        </footer>
      </div>
    </div>
  );
}

/* ───────────────────────── sidebar (shared by desktop and drawer) ───────────────────────── */

function SidebarContent({
  id,
  health,
  err,
  onClose,
}: {
  id: string;
  health: Health;
  err: boolean;
  onClose?: () => void;
}) {
  const reduce = useReducedMotion();
  const { user, logout } = useAuth();
  const { start } = useTour();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);

  const signOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-0 w-full flex-col">
      <div className="flex h-16 shrink-0 items-center gap-2.5 px-5">
        <NavLink to="/" className="flex items-center gap-2.5" aria-label="PixelProof home">
          <Logo />
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">PixelProof</div>
            <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">ground station</div>
          </div>
        </NavLink>
        {onClose && (
          <Button variant="ghost" size="icon" className="ml-auto" aria-label="Close menu" onClick={onClose}>
            <X size={18} />
          </Button>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-3 pb-4" aria-label="Sections" data-tour={id === "desk" ? "nav" : undefined}>
        <LayoutGroup id={id}>
          {NAV.map(({ group, items }) => (
            <div key={group} className="mt-4 first:mt-1">
              <div className="mb-1 px-3 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground/70">{group}</div>
              <ul className="space-y-0.5">
                {items.map(({ to, label, icon: Icon, end }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={end}
                      className={({ isActive }) =>
                        cn(
                          "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                          isActive ? "text-foreground" : "text-muted-foreground hover:bg-white/[0.04] hover:text-foreground",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <motion.span
                              layoutId={`nav-pill-${id}`}
                              className="absolute inset-0 rounded-lg border border-white/10 bg-white/[0.07]"
                              transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 34 }}
                            >
                              <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />
                            </motion.span>
                          )}
                          <Icon size={16} aria-hidden className={cn("relative", isActive && "text-primary")} />
                          <span className="relative">{label}</span>
                        </>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </LayoutGroup>
      </nav>

      <div className="shrink-0 space-y-2 border-t border-white/[0.06] p-3">
        <div className="relative" data-tour={id === "desk" ? "status" : undefined}>
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] py-1.5 pl-3 pr-1 text-xs text-muted-foreground">
            <StatusDot health={health} err={err} />
            <span className="min-w-0 flex-1 truncate">
              {statusText(health, err)}
              {health && <span className="text-foreground/70"> · {String(health.model_mode)}</span>}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              aria-label="API settings"
              aria-expanded={editing}
              onClick={() => setEditing((v) => !v)}
            >
              <Settings size={14} />
            </Button>
          </div>
          {editing && (
            <form
              className="mt-2 flex flex-col gap-2 rounded-lg border border-white/10 bg-card p-3"
              onSubmit={(e) => {
                e.preventDefault();
                const v = new FormData(e.currentTarget).get("base") as string;
                setApiBase(v);
                location.reload();
              }}
            >
              <label htmlFor={`api-base-${id}`} className="text-xs text-muted-foreground">
                API base URL (current: {API_BASE || "same origin"})
              </label>
              <input
                id={`api-base-${id}`}
                name="base"
                defaultValue={API_BASE}
                placeholder="http://10.56.0.30:8000"
                className="h-9 rounded-md border border-white/10 bg-background px-2 font-mono text-xs text-foreground"
              />
              <Button size="sm" type="submit">
                Save and reload
              </Button>
            </form>
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-3 px-3"
          onClick={() => {
            onClose?.();
            start();
          }}
        >
          <Compass size={16} aria-hidden /> Product tour
        </Button>

        {user && (
          <div className="flex items-center gap-3 rounded-lg px-2 py-1.5" data-tour={id === "desk" ? "account" : undefined}>
            <Avatar name={user.name} />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-sm font-medium">{user.name}</div>
              <div className="truncate text-xs text-muted-foreground">{user.email}</div>
            </div>
            <Button variant="ghost" size="icon" aria-label="Sign out" title="Sign out" onClick={signOut}>
              <LogOut size={16} />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────── small pieces ───────────────────────── */

function statusText(health: Health, err: boolean) {
  return err ? "backend unreachable" : health ? "backend online" : "connecting…";
}

function StatusDot({ health, err }: { health: Health; err: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        err ? "bg-verdict-bad" : health ? "bg-verdict-ok animate-pulse-ring [--ring-color:152_62%_48%]" : "bg-verdict-mute",
      )}
      aria-hidden
    />
  );
}

function Avatar({ name }: { name: string }) {
  const initials =
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]!.toUpperCase())
      .join("") || "?";
  return (
    <span
      aria-hidden
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/10 bg-gradient-to-br from-primary/30 to-accent/30 text-xs font-semibold text-foreground"
    >
      {initials}
    </span>
  );
}
