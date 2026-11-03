import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { hasWebGL } from "@/lib/webgl";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { PageHeader } from "@/components/PageHeader";
import { Select } from "@/components/ui/select";
import { LinkFallback } from "@/three/LinkFallback";
import type { Packet } from "@/three/EarthScene";

const EarthScene = lazy(() => import("@/three/EarthScene").then((m) => ({ default: m.EarthScene })));

const TONE: Record<string, string> = {
  VERIFIED: "#34d399",
  SIGNED_BUT_SUSPICIOUS: "#f59e0b",
  ALTERED_AFTER_CAPTURE: "#ef4444",
  SUSPICIOUS: "#f59e0b",
  UNVERIFIED_NO_TRACES: "#94a3b8",
};

export function LiveLink() {
  const webgl = useMemo(hasWebGL, []);
  const [entries, setEntries] = useState<any[]>([]);
  const [chainValid, setChainValid] = useState<boolean | null>(null);
  const [packets, setPackets] = useState<Packet[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    let alive = true;
    async function poll() {
      try {
        const l = await api.ledger(100);
        if (!alive) return;
        setChainValid(l.chain_valid);
        setEntries(l.entries);
        for (const e of l.entries.slice(0, 6)) {
          if (!seen.current.has(e.hash)) {
            seen.current.add(e.hash);
            const tone = TONE[e.verdict] ?? "#94a3b8";
            setPackets((p) => [...p, { id: e.hash, tone, verdict: e.verdict, attack: e.content_type }]);
          }
        }
      } catch {
        /* backend may be briefly unreachable; keep last state */
      }
    }
    poll();
    const iv = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const e of entries) c[e.verdict] = (c[e.verdict] ?? 0) + 1;
    return c;
  }, [entries]);

  const rows = filter === "all" ? entries : entries.filter((e) => e.verdict === filter);

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Attack lab"
        title="Live link"
        actions={
          <Badge tone={chainValid === false ? "bad" : "ok"}>
            audit chain {chainValid === null ? "…" : chainValid ? "valid" : "BROKEN"}
          </Badge>
        }
      >
        Downlinks travel satellite → attacker → ground. Packets are coloured by the ground station's
        verdict. Data is the real audit log (polled every 3 s).
      </PageHeader>

      <Card data-tour="live-globe">
        <CardContent className="pt-4">
          {webgl ? (
            <Suspense fallback={<div className="h-72 animate-pulse rounded bg-muted" />}>
              <div className="h-72">
                <EarthScene packets={packets} onPacketDone={(id) => setPackets((p) => p.filter((q) => q.id !== id))} />
              </div>
            </Suspense>
          ) : (
            <LinkFallback counts={counts} />
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {webgl ? "3D view (WebGL)" : "2D fallback — no WebGL on this machine"} · this page only reads verdicts;
            synthetic attacks are run from the Attack lab page.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>Audit log</CardTitle>
          <Select
            aria-label="filter by verdict"
            className="h-9 text-xs"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">all verdicts</option>
            {Object.keys(TONE).map((v) => (
              <option key={v} value={v}>
                {v.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>product</TH>
                <TH>verdict</TH>
                <TH>integrity</TH>
                <TH>content</TH>
                <TH>action</TH>
              </TR>
            </THead>
            <TBody>
              {rows.map((e) => (
                <TR key={e.hash} className="cursor-pointer" onClick={() => setSelected(e)}>
                  <TD className="font-mono text-xs">{e.product_id ?? "—"}</TD>
                  <TD>
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-block h-2 w-2 rounded-full" style={{ background: TONE[e.verdict] }} aria-hidden />
                      {e.verdict?.replace(/_/g, " ")}
                    </span>
                  </TD>
                  <TD className="text-xs">{e.integrity}</TD>
                  <TD className="text-xs">{e.content_type}</TD>
                  <TD className="text-xs">{e.action}</TD>
                </TR>
              ))}
              {rows.length === 0 && (
                <TR>
                  <TD colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                    No downlinks yet. Run the satellite node (see the attack guide).
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>
        </CardContent>
      </Card>

      {selected && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Decision for {selected.product_id ?? "this message"}</CardTitle>
            <button className="text-sm text-muted-foreground hover:underline" onClick={() => setSelected(null)}>
              close
            </button>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded bg-muted p-3 text-xs">{JSON.stringify(selected, null, 2)}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
