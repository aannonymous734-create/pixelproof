import { lazy, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion, useInView, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  BadgeCheck,
  Cpu,
  FileSearch,
  Fingerprint,
  Network,
  ScrollText,
  ShieldCheck,
  Satellite,
  Skull,
  Server,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Counter } from "@/components/ui/counter";
import { Reveal } from "@/components/ui/reveal";
import { hasWebGL } from "@/lib/webgl";
import { useHeadline, type Headline } from "@/lib/results";
import { api, type LedgerEntry, type Stats } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

const HeroScene = lazy(() => import("@/three/HeroScene"));

const STATUSES = [
  ["VERIFIED", "ok"],
  ["PIXELS_ALTERED", "bad"],
  ["BAD_SIGNATURE", "bad"],
  ["UNKNOWN_KEY", "bad"],
  ["WEAK_ALGORITHM", "warn"],
  ["CHAIN_BROKEN", "bad"],
  ["REPLAY", "warn"],
] as const;

export function Home() {
  const state = useHeadline();
  const h = state.status === "ok" ? state.data : null;

  return (
    <div className="space-y-24 md:space-y-32">
      <Hero />
      <StatStrip h={h} failed={state.status === "error"} />
      <LiveActivity />
      <TwoAnswers h={h} />
      <HowItTravels />
      <Cta />
    </div>
  );
}

/* ───────────────────────── hero ───────────────────────── */

function Hero() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref);
  const webgl = useMemo(hasWebGL, []);
  const reduce = useReducedMotion();
  const rise = (i: number) =>
    reduce ? {} : { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.6, delay: 0.08 * i, ease: [0.16, 1, 0.3, 1] as const } };

  return (
    <section className="grid grid-cols-1 items-center gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
      <div className="min-w-0">
        <motion.div {...rise(0)}>
          <Badge tone="info" className="gap-2 px-3 py-1">
            <span className="h-1.5 w-1.5 rounded-full bg-verdict-info" aria-hidden /> TSYP14 · Track 3 · Trust the Pixel
          </Badge>
        </motion.div>
        <motion.h1
          {...rise(1)}
          className="text-gradient mt-5 text-balance text-5xl font-semibold leading-[1.06] tracking-tight sm:text-6xl"
        >
          Prove where every pixel came from.
        </motion.h1>
        <motion.p {...rise(2)} className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
          PixelProof binds each satellite patch to a <span className="text-foreground">signed origin</span> and exposes
          post-capture manipulation. Two independent answers — <span className="text-foreground">integrity</span> and{" "}
          <span className="text-foreground">content</span> — become one verdict an analyst can act on.
        </motion.p>
        <motion.div {...rise(3)} className="mt-8 flex flex-wrap gap-3">
          <Button asChild variant="accent" size="lg">
            <Link to="/analyse">
              Analyse a patch <ArrowRight size={18} aria-hidden />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link to="/results">See the measured results</Link>
          </Button>
        </motion.div>
        <motion.ul {...rise(4)} className="mt-8 flex flex-wrap gap-2 text-xs text-muted-foreground" aria-label="Key properties">
          {["Ed25519 + SHA-256", "Hash-chained audit log", "CPU only · no hardware", "Open data: EuroSAT"].map((t) => (
            <li key={t} className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1">
              <BadgeCheck size={13} className="text-primary" aria-hidden /> {t}
            </li>
          ))}
        </motion.ul>
      </div>

      <div ref={ref} className="relative mx-auto aspect-square w-full max-w-[580px]">
        <div aria-hidden className="absolute inset-[10%] rounded-full bg-primary/[0.14] blur-3xl" />
        {webgl ? (
          <Suspense fallback={<Orb />}>
            <HeroScene active={inView} />
          </Suspense>
        ) : (
          <Orb />
        )}
        <ul className="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-3 text-[11px] text-muted-foreground" aria-label="Legend">
          <Legend color="bg-[#7dd3fc]" label="satellite signs" />
          <Legend color="bg-[#fbbf24]" label="attacker tampers" />
          <Legend color="bg-[#34d399]" label="ground verifies" />
        </ul>
      </div>
    </section>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <li className="flex items-center gap-1.5 rounded-full border border-white/10 bg-background/60 px-2.5 py-1 backdrop-blur">
      <span className={cn("h-2 w-2 rounded-full", color)} aria-hidden /> {label}
    </li>
  );
}

/** No-WebGL fallback (VMs often have no GPU): a static dotted orb, same footprint. */
function Orb() {
  return (
    <div
      aria-hidden
      className="absolute inset-[12%] rounded-full border border-white/10"
      style={{
        background:
          "radial-gradient(circle at 35% 30%, hsl(199 95% 62% / 0.35), transparent 55%), radial-gradient(circle, hsl(0 0% 100% / 0.12) 1px, transparent 1.5px) 0 0 / 14px 14px, hsl(240 10% 5%)",
      }}
    />
  );
}

/* ───────────────────────── live numbers ───────────────────────── */

function StatStrip({ h, failed }: { h: Headline | null; failed: boolean }) {
  const p1 = (n: number) => `${(100 * n).toFixed(1)}%`;
  const items = h
    ? [
        { v: 100 * h.seenDetection, f: (n: number) => `${n.toFixed(1)}%`, label: "detected · variants seen in training", sub: `at ${p1(h.seenFalseAlarm)} false alarms` },
        { v: 100 * h.heldoutV2Detection, f: (n: number) => `${n.toFixed(1)}%`, label: "detected · frozen held-out set", sub: `unseen methods, at ${p1(h.heldoutV2FalseAlarm)} false alarms` },
        { v: h.attackTypesCaught, f: (n: number) => `${Math.round(n)}/${h.attackTypes}`, label: "trust-layer attack types caught", sub: `${h.products} signed products each` },
        { v: h.analyseMs, f: (n: number) => `${n.toFixed(0)} ms`, label: "per patch on one CPU core", sub: `${h.peakMb.toFixed(0)} MB peak · no GPU` },
      ]
    : null;

  return (
    <section aria-labelledby="stats-h">
      <h2 id="stats-h" className="sr-only">
        Measured results
      </h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {items
          ? items.map((s, i) => (
              <Reveal key={s.label} delay={i * 0.07}>
                <Card className="h-full p-5">
                  <div className="text-3xl font-semibold tabular-nums tracking-tight sm:text-4xl">
                    <Counter value={s.v} format={s.f} />
                  </div>
                  <div className="mt-2 text-sm text-foreground/90">{s.label}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{s.sub}</div>
                </Card>
              </Reveal>
            ))
          : Array.from({ length: 4 }, (_, i) => (
              <Card key={i} spotlight={false} className="h-[118px] animate-pulse p-5">
                <span className="sr-only">{failed ? "results unavailable" : "loading results"}</span>
              </Card>
            ))}
      </div>
      <p className="mt-3 text-center text-xs text-muted-foreground">
        {failed
          ? "The backend is not reachable, so no figures are shown (nothing here is typed by hand)."
          : "Read live from the reproduced result files in results/ — nothing here is typed by hand."}
      </p>
    </section>
  );
}

/* ───────────────────────── live activity (from the audit log) ───────────────────────── */

const SEVERITY_TONE = { critical: "bad", warning: "warn", info: "mute" } as const;

function LiveActivity() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<LedgerEntry[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      Promise.all([api.stats(), api.ledger(5)])
        .then(([s, l]) => {
          if (!alive) return;
          setStats(s);
          setRecent(l.entries);
          setFailed(false);
        })
        .catch(() => alive && setFailed(true));
    load();
    const iv = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  const cards = stats
    ? [
        { label: "Products analysed", v: stats.total, tone: "text-foreground" },
        { label: "Verified (valid provenance)", v: stats.verified, tone: "text-verdict-ok" },
        { label: "Suspicious", v: stats.suspicious, tone: "text-verdict-warn" },
        { label: "Rejected (altered)", v: stats.rejected, tone: "text-verdict-bad" },
        { label: "Invalid signatures", v: stats.invalid_signatures, tone: "text-verdict-bad" },
        { label: "Manipulation alerts", v: stats.manipulation_alerts, tone: "text-verdict-warn" },
      ]
    : null;

  return (
    <section aria-labelledby="live-h" data-tour="home-live">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="text-xs font-medium uppercase tracking-[0.18em] text-primary">This ground station</div>
          <h2 id="live-h" className="text-gradient mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
            Live activity
          </h2>
        </div>
        {stats && (
          <Badge tone={stats.audit_chain_valid ? "ok" : "bad"}>audit chain {stats.audit_chain_valid ? "valid" : "BROKEN"}</Badge>
        )}
      </div>

      {failed ? (
        <Card spotlight={false} className="p-5 text-sm text-muted-foreground">
          The backend is not reachable, so no activity is shown.
        </Card>
      ) : !cards ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          {Array.from({ length: 6 }, (_, i) => (
            <Card key={i} spotlight={false} className="h-24 animate-pulse" />
          ))}
        </div>
      ) : stats!.total === 0 ? (
        <Card spotlight={false} className="p-6 text-sm text-muted-foreground">
          <div className="font-medium text-foreground">Nothing has been analysed yet.</div>
          <p className="mt-1">
            These counters come from the audit log, so a fresh station shows zeros. Analyse an image, start the satellite node, or run an
            attack in the lab to fill them.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link to="/analyse">Analyse an image</Link>
            </Button>
            <Button asChild size="sm" variant="outline">
              <Link to="/lab">Open the attack lab</Link>
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            {cards.map((c) => (
              <Card key={c.label} className="p-4">
                <div className={cn("text-3xl font-semibold tabular-nums tracking-tight", c.tone)}>{c.v}</div>
                <div className="mt-1 text-xs text-muted-foreground">{c.label}</div>
              </Card>
            ))}
          </div>
          <Card spotlight={false} className="mt-3">
            <div className="flex items-center justify-between px-5 pt-4">
              <h3 className="text-xs font-medium uppercase tracking-[0.12em] text-muted-foreground">Recent security events</h3>
              <Button asChild size="sm" variant="ghost">
                <Link to="/audit">
                  Open the audit log <ArrowRight size={14} aria-hidden />
                </Link>
              </Button>
            </div>
            <ul className="divide-y divide-white/[0.06] px-5 pb-3 text-sm">
              {recent.map((e) => (
                <li key={e.hash} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
                  <Badge tone={SEVERITY_TONE[e.severity]}>{e.severity}</Badge>
                  <span className="font-medium">{e.verdict.replace(/_/g, " ")}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                    {e.integrity} · {e.product_id ?? "no product id"}
                  </span>
                  <span className="text-xs text-muted-foreground">{timeAgo(e.time)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </section>
  );
}

/* ───────────────────────── bento ───────────────────────── */

function Bento({
  icon,
  title,
  eyebrow,
  className,
  children,
}: {
  icon: ReactNode;
  title: string;
  eyebrow: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={cn("flex h-full flex-col p-6", className)}>
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-primary">
        {icon}
      </div>
      <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-primary">{eyebrow}</div>
      <h3 className="mt-1 text-lg font-semibold tracking-tight">{title}</h3>
      <div className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </Card>
  );
}

function TwoAnswers({ h }: { h: Headline | null }) {
  return (
    <section aria-labelledby="two-h">
      <Reveal className="mx-auto max-w-2xl text-center">
        <div className="text-xs font-medium uppercase tracking-[0.18em] text-primary">The idea</div>
        <h2 id="two-h" className="text-gradient mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Two answers, never mixed up.
        </h2>
        <p className="mt-3 text-muted-foreground">
          A perfectly signed image can still have been faked before signing. So proof of origin and evidence about the
          content are kept apart — and both reach the analyst.
        </p>
      </Reveal>

      <div className="mt-10 grid gap-3 md:grid-cols-3">
        <Reveal className="md:col-span-2">
          <Bento icon={<Fingerprint size={20} />} eyebrow="Integrity · proof" title="Signed origin, checked pixel by pixel">
            An Ed25519 signature over a SHA-256 digest of the pixels, bound to source, sensor and capture date, plus a
            signed chain of every processing step. Only registered keys and pinned algorithms are trusted.
            <div className="mt-4 flex flex-wrap gap-1.5">
              {STATUSES.map(([s, tone]) => (
                <Badge key={s} tone={tone} className="font-mono text-[11px]">
                  {s}
                </Badge>
              ))}
            </div>
          </Bento>
        </Reveal>
        <Reveal delay={0.07}>
          <Bento icon={<FileSearch size={20} />} eyebrow="Content · evidence" title="Forensics, not guesses">
            48 explainable features (resampling, noise, colour, copy-move) fused with a small forensic CNN, calibrated
            to a {h ? `${Math.round(100 * h.targetFpr)}%` : "fixed"} false-alarm budget. Every alarm says why.
          </Bento>
        </Reveal>
        <Reveal delay={0.05}>
          <Bento icon={<ScrollText size={20} />} eyebrow="Accountability" title="Tamper-evident audit log">
            Every decision is appended to a hash-chained log. Editing any past entry breaks the chain, and the
            dashboard says so.
          </Bento>
        </Reveal>
        <Reveal delay={0.1}>
          <Bento icon={<Network size={20} />} eyebrow="Attack lab" title="Isolated satellite → attacker → ground">
            Three isolated machines, including a transparent man-in-the-middle the satellite never knew about. Jury
            attacks welcome — see the guide.
          </Bento>
        </Reveal>
        <Reveal delay={0.15}>
          <Bento icon={<Cpu size={20} />} eyebrow="Feasibility" title="Runs on a laptop">
            CPU only, open data, no hardware, no cloud.{" "}
            {h && (
              <span className="text-foreground">
                {h.analyseMs.toFixed(0)} ms per patch, {h.peakMb.toFixed(0)} MB peak.
              </span>
            )}
          </Bento>
        </Reveal>
      </div>

      <Reveal className="mt-3">
        <Card className="flex flex-wrap items-center gap-3 px-6 py-4 text-sm text-muted-foreground">
          <ShieldCheck size={18} className="text-verdict-ok" aria-hidden />
          <span>
            <span className="text-foreground">Honest by design:</span> we never call a patch “authentic” — only “no traces
            found” — and the known weak spots are reported, not hidden.
          </span>
          <Button asChild variant="ghost" size="sm" className="ml-auto">
            <Link to="/results">
              Read the numbers <ArrowRight size={14} aria-hidden />
            </Link>
          </Button>
        </Card>
      </Reveal>
    </section>
  );
}

/* ───────────────────────── how a patch travels ───────────────────────── */

const STEPS = [
  { icon: Satellite, tone: "text-[#7dd3fc]", title: "Sign at the source", body: "The payload hashes the pixels and signs a claim with a key that never leaves it." },
  { icon: Skull, tone: "text-[#fbbf24]", title: "Cross a hostile link", body: "An attacker may modify, replay, strip or swap the data — explicitly or as a hidden relay." },
  { icon: Server, tone: "text-[#34d399]", title: "Verify and analyse", body: "The ground station checks the proof, inspects the content, decides and logs." },
];

function HowItTravels() {
  return (
    <section aria-labelledby="how-h">
      <Reveal className="mx-auto max-w-2xl text-center">
        <div className="text-xs font-medium uppercase tracking-[0.18em] text-primary">How it works</div>
        <h2 id="how-h" className="text-gradient mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          One patch, three machines.
        </h2>
      </Reveal>
      <ol className="relative mt-10 grid gap-3 md:grid-cols-3">
        {STEPS.map(({ icon: Icon, tone, title, body }, i) => (
          <Reveal key={title} delay={i * 0.1}>
            <li className="list-none">
              <Card className="h-full p-6">
                <div className="flex items-center justify-between">
                  <Icon size={22} className={tone} aria-hidden />
                  <span className="font-mono text-xs text-muted-foreground">0{i + 1}</span>
                </div>
                <h3 className="mt-4 text-base font-semibold tracking-tight">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </Card>
            </li>
          </Reveal>
        ))}
      </ol>
    </section>
  );
}

/* ───────────────────────── call to action ───────────────────────── */

function Cta() {
  return (
    <Reveal>
      <Card spotlight={false} className="border-beam px-6 py-14 text-center sm:px-12">
        <div aria-hidden className="absolute inset-x-0 -top-24 mx-auto h-48 w-2/3 rounded-full bg-primary/20 blur-3xl" />
        <h2 className="text-gradient relative text-3xl font-semibold tracking-tight sm:text-4xl">Try it on your own patch.</h2>
        <p className="relative mx-auto mt-3 max-w-xl text-muted-foreground">
          Drop any image — with or without a signed manifest — and watch the two answers appear.
        </p>
        <div className="relative mt-7 flex flex-wrap justify-center gap-3">
          <Button asChild variant="accent" size="lg">
            <Link to="/analyse">
              Open the analyser <ArrowRight size={18} aria-hidden />
            </Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link to="/attacks">Attack it yourself</Link>
          </Button>
        </div>
      </Card>
    </Reveal>
  );
}
