import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  FlaskConical,
  Loader2,
  Lock,
  Play,
  Satellite,
  Server,
  Skull,
  XCircle,
} from "lucide-react";
import { api, type LabResult, type LabRunSummary, type LabScenario } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/PageHeader";

const GROUPS: Record<string, string> = {
  A: "Image tampering",
  B: "Manifest and identity forgery",
  C: "Replacement and algorithm substitution",
  D: "Replay",
  E: "Visual manipulation without a signature",
  F: "Compromised source",
};

const ACTOR = {
  satellite: { icon: Satellite, color: "text-[#7dd3fc]", label: "satellite" },
  attacker: { icon: Skull, color: "text-[#fbbf24]", label: "attacker" },
  ground: { icon: Server, color: "text-[#34d399]", label: "ground" },
} as const;

export function AttackLab() {
  const toast = useToast();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [scenarios, setScenarios] = useState<LabScenario[]>([]);
  const [loadError, setLoadError] = useState("");
  const [trials, setTrials] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<LabResult | null>(null);
  const [runs, setRuns] = useState<LabRunSummary[]>([]);
  const resultRef = useRef<HTMLDivElement>(null);

  const refreshRuns = useCallback(() => {
    api.labRuns().then(setRuns).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .labScenarios()
      .then((r) => {
        setEnabled(r.enabled);
        setScenarios(r.scenarios);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : "could not reach the backend"));
    refreshRuns();
  }, [refreshRuns]);

  const groups = useMemo(() => {
    const g = new Map<string, LabScenario[]>();
    for (const s of scenarios) g.set(s.id[0], [...(g.get(s.id[0]) ?? []), s]);
    return [...g.entries()];
  }, [scenarios]);

  async function run(s: LabScenario) {
    setBusy(s.name);
    try {
      const r = await api.labRun(s.name, trials);
      setResult(r);
      refreshRuns();
      const ok = r.kind === "content" ? true : r.matches_expected === r.n;
      toast({
        tone: ok ? "ok" : "bad",
        title: `${r.id} · ${r.title}`,
        description:
          r.kind === "content"
            ? `Flagged ${r.matches_expected} of ${r.n} manipulated patches.`
            : `${r.matches_expected} of ${r.n} gave the expected result (${r.expected}).`,
      });
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e) {
      toast({ tone: "bad", title: "The run failed", description: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Adversarial validation" title="Attack lab">
        Run real attacks against this ground station's verification pipeline. The traffic is synthetic and local to this
        server, signed with temporary keys: your real audit log and trust registry are never touched.
      </PageHeader>

      {loadError ? (
        <Card spotlight={false}>
          <CardContent className="flex items-center gap-3 pt-5 text-sm text-verdict-bad" role="alert">
            <XCircle size={18} aria-hidden /> {loadError}
          </CardContent>
        </Card>
      ) : enabled === null ? (
        <Card spotlight={false} className="h-24 animate-pulse" />
      ) : (
        <Card spotlight={false} className={cn(!enabled && "border-verdict-warn/30")} data-tour="lab-controls">
          <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-center">
            {enabled ? (
              <>
                <div className="flex min-w-0 flex-1 items-start gap-3 text-sm sm:items-center">
                  <FlaskConical className="mt-0.5 shrink-0 text-verdict-ok sm:mt-0" size={20} aria-hidden />
                  <p className="min-w-0">
                    <span className="font-medium">Lab mode is on.</span>{" "}
                    <span className="text-muted-foreground">
                      Each run signs genuine products, attacks them in transit and feeds them to the real verifier.
                    </span>
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 text-sm" role="group" aria-label="Number of trials">
                  <span className="text-muted-foreground">trials per run</span>
                  {[1, 20].map((n) => (
                    <Button key={n} size="sm" variant={trials === n ? "default" : "outline"} onClick={() => setTrials(n)}>
                      {n}
                    </Button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <Lock className="shrink-0 self-start text-verdict-warn" size={20} aria-hidden />
                <div className="min-w-0 flex-1 text-sm">
                  <span className="font-medium">Lab mode is off on this server</span>{" "}
                  <span className="text-muted-foreground">
                    (the safe default: a production ground station must never run attacks). The scenarios below are read-only. To
                    run them, restart the backend with the lab enabled:
                  </span>
                  <pre className="mt-2 overflow-x-auto rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-xs">
                    {`# PowerShell                                  # Linux / macOS\n$env:PIXELPROOF_LAB_MODE = "1"                 PIXELPROOF_LAB_MODE=1 \\\nuvicorn pixelproof.api:app --port 8000          uvicorn pixelproof.api:app --port 8000`}
                  </pre>
                  <p className="mt-2 text-xs text-muted-foreground">
                    You can also run them without the dashboard:{" "}
                    <code>python -m simulation.run_attack --scenario image_tampering</code>
                  </p>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {groups.map(([letter, items], gi) => (
        <section key={letter} aria-labelledby={`g-${letter}`}>
          <Reveal delay={gi * 0.03}>
            <h2 id={`g-${letter}`} className="mb-3 text-sm font-medium text-muted-foreground">
              <span className="mr-2 font-mono text-primary">{letter}</span>
              {GROUPS[letter] ?? "Other"}
            </h2>
            <div className="grid gap-3 md:grid-cols-2">
              {items.map((s) => (
                <ScenarioCard key={s.name} s={s} enabled={!!enabled} busy={busy} onRun={() => run(s)} />
              ))}
            </div>
          </Reveal>
        </section>
      ))}

      <div ref={resultRef} className="scroll-mt-24">
        {result && <ResultPanel r={result} />}
      </div>

      <Card spotlight={false}>
        <CardHeader>
          <CardTitle>Recent runs (this server session)</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No runs yet. Pick a scenario above and press Run.</p>
          ) : (
            <ul className="divide-y divide-white/[0.06] text-sm">
              {runs.map((r, i) => (
                <li key={i} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2">
                  <span className="font-mono text-xs text-primary">{r.id}</span>
                  <span className="min-w-0 flex-1">{r.title}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {r.matches_expected}/{r.n}
                  </span>
                  <span className="text-xs text-muted-foreground">{timeAgo(r.time)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Attacking the ground station over the network from another machine (the jury's way) is explained in the{" "}
            <Link className="text-primary underline-offset-2 hover:underline" to="/attacks">
              jury attack guide
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function ScenarioCard({ s, enabled, busy, onRun }: { s: LabScenario; enabled: boolean; busy: string | null; onRun: () => void }) {
  const running = busy === s.name;
  return (
    <Card className="flex h-full flex-col p-5">
      <div className="flex items-center gap-2">
        <Badge tone={s.kind === "content" ? "warn" : s.kind === "compromised_source" ? "bad" : "info"} className="font-mono">
          {s.id}
        </Badge>
        <h3 className="text-base font-semibold tracking-tight">{s.title}</h3>
      </div>
      <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">{s.attacker_action}</p>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          expected:{" "}
          <code className="text-foreground">{s.expected === "CONTENT_FLAGGED" ? "detector flags it (not guaranteed)" : s.expected}</code>
        </span>
        <Button size="sm" variant="accent" onClick={onRun} disabled={!enabled || busy !== null} aria-label={`Run ${s.title}`}>
          {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} aria-hidden />}
          {running ? "Running…" : "Run"}
        </Button>
      </div>
    </Card>
  );
}

function tally(xs: string[]): [string, number][] {
  const m = new Map<string, number>();
  for (const x of xs) m.set(x, (m.get(x) ?? 0) + 1);
  return [...m.entries()];
}

function ResultPanel({ r }: { r: LabResult }) {
  const t = r.trials[0];
  const flagged = r.trials.filter((x) => x.content.flagged).length;
  const integrityKind = r.kind === "integrity" || r.kind === "replay";
  const allOk = r.matches_expected === r.n;

  return (
    <Reveal>
      <Card spotlight={false} className="border-beam" style={{ ["--beam" as string]: integrityKind && !allOk ? "0 82% 62%" : "152 62% 48%" }}>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>
            Result · {r.id} · {r.title}
          </CardTitle>
          <span className="text-xs text-muted-foreground">
            {r.n} trial{r.n > 1 ? "s" : ""} · {r.duration_s}s · detector {r.environment.model_mode}
          </span>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* headline */}
          {integrityKind && (
            <div className={cn("flex items-center gap-3 rounded-xl border p-4", allOk ? "border-verdict-ok/30 bg-verdict-ok/10" : "border-verdict-bad/30 bg-verdict-bad/10")}>
              {allOk ? <CheckCircle2 className="text-verdict-ok" aria-hidden /> : <XCircle className="text-verdict-bad" aria-hidden />}
              <div className="text-sm">
                <div className="font-medium">
                  {allOk ? "The attack was stopped" : "Unexpected result"}: {r.matches_expected} of {r.n} produced{" "}
                  <code>{r.expected}</code>
                </div>
                <div className="text-muted-foreground">
                  Ground station answered: {tally(r.trials.map((x) => x.integrity_status)).map(([k, v]) => `${k} ×${v}`).join(", ")} → action{" "}
                  {tally(r.trials.map((x) => x.action)).map(([k, v]) => `${k} ×${v}`).join(", ")}
                </div>
              </div>
            </div>
          )}
          {r.kind === "content" && (
            <div className="flex items-start gap-3 rounded-xl border border-verdict-warn/30 bg-verdict-warn/10 p-4 text-sm">
              <AlertTriangle className="mt-0.5 text-verdict-warn" aria-hidden />
              <div>
                <div className="font-medium">
                  The content detector flagged {flagged} of {r.n} manipulated patches
                </div>
                <div className="text-muted-foreground">
                  With no signature there is nothing to verify, so only statistics can notice. This is a measured detection rate on {r.n}{" "}
                  patches, not a guarantee. On the {r.control.n} untouched originals it raised {r.control.false_alarms} false alarm
                  {r.control.false_alarms === 1 ? "" : "s"}.
                </div>
              </div>
            </div>
          )}
          {r.kind === "compromised_source" && (
            <div className="flex items-start gap-3 rounded-xl border border-verdict-bad/30 bg-verdict-bad/10 p-4 text-sm">
              <AlertTriangle className="mt-0.5 text-verdict-bad" aria-hidden />
              <div>
                <div className="font-medium">
                  All {r.n} fakes had a VALID signature. The content detector flagged {flagged} of {r.n}.
                </div>
                <div className="text-muted-foreground">
                  Verdicts: {tally(r.trials.map((x) => x.verdict)).map(([k, v]) => `${k.replace(/_/g, " ")} ×${v}`).join(", ")}. A signature proves who
                  signed and that nothing changed afterwards. It does not prove the picture is true.
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-3 text-sm">
              <Row k="Attacker action" v={r.attacker_action} />
              <Row k="Why this happens" v={r.why_it_fails} />
              <Row
                k="Control"
                v={
                  r.kind === "content"
                    ? `${r.control.false_alarms}/${r.control.n} untouched originals wrongly flagged`
                    : `${r.control.verified}/${r.control.n} untouched products were VERIFIED`
                }
              />
              <Row
                k="Audit log"
                v={`${r.audit_log.entries} entries, hash chain ${r.audit_log.chain_valid ? "valid" : "BROKEN"}`}
              />
              {(t.signed_digest || t.received_digest) && (
                <div>
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Evidence (trial 1, SHA-256)</div>
                  <div className="mt-1 space-y-1 font-mono text-xs">
                    {t.signed_digest && <div>signed&nbsp;&nbsp;&nbsp;{t.signed_digest}</div>}
                    {t.received_digest && <div>received&nbsp;{t.received_digest}</div>}
                  </div>
                </div>
              )}
              {t.reasons.map((x, i) => (
                <p key={i} className="text-xs text-muted-foreground">
                  ground station: {x}
                </p>
              ))}
            </div>

            <div>
              <div className="text-xs uppercase tracking-wider text-muted-foreground">Timeline (trial 1)</div>
              <ol className="mt-2 space-y-2">
                {t.timeline.map((e, i) => {
                  const a = ACTOR[e.actor];
                  const Icon = a.icon;
                  const detail = [e.integrity, e.verdict, e.action].filter(Boolean).join(" · ");
                  return (
                    <li key={i} className="flex items-start gap-2.5 text-sm">
                      <Icon size={15} className={cn("mt-0.5 shrink-0", a.color)} aria-hidden />
                      <div className="min-w-0 flex-1">
                        <span className={a.color}>{a.label}</span> {e.event}
                        {detail && <div className="font-mono text-xs text-muted-foreground">{detail}</div>}
                      </div>
                      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{e.t_ms.toFixed(0)} ms</span>
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>
        </CardContent>
      </Card>
    </Reveal>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{k}</div>
      <div className="mt-0.5">{v}</div>
    </div>
  );
}
