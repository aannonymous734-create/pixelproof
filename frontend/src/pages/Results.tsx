import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "@/lib/api";
import { pct } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/PageHeader";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Results {
  metrics: any;
  heldout_v2: any;
  heldout_v2_v1: any;
  robustness: any;
  campaign: any;
}

const FAMILIES = ["resample", "splice", "copy_move", "inpaint"];

export function Results() {
  const [data, setData] = useState<Results | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/results`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setErr("could not load results from the backend"));
  }, []);

  // the metrics file keys the fused model "fused (w=0.4)"; the held-out v2 file keys it "fused".
  const fusedKeyOf = (models: Record<string, unknown> | undefined) =>
    Object.keys(models ?? {}).find((k) => k.toLowerCase().includes("fused")) ?? Object.keys(models ?? {})[0];
  const fusedKey = useMemo(() => fusedKeyOf(data?.metrics?.models), [data]);
  const v2Key = useMemo(() => fusedKeyOf(data?.heldout_v2?.models), [data]);

  if (err) return <p className="text-sm text-verdict-bad">{err}</p>;
  if (!data?.metrics) return <div className="h-40 animate-pulse rounded bg-muted" />;

  const fused = data.metrics.models[fusedKey];
  const v2fam = data.heldout_v2?.models?.[v2Key]?.detection_by_family;
  const familyData = FAMILIES.map((f) => ({
    family: f.replace("_", "-"),
    seen: 100 * (fused.test_dev.detection_by_family[f] ?? 0),
    heldout: 100 * (fused.test_heldout.detection_by_family[f] ?? 0),
    heldout_v2: v2fam ? 100 * (v2fam[f] ?? 0) : NaN,
  }));
  const faDev = data.metrics.false_alarm_by_landcover?.test_dev ?? {};
  const faData = Object.entries(faDev).map(([k, v]) => ({ landcover: k, fa: 100 * (v as number) }));

  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Evidence" title="Results">
        Every number is read live from the reproduced result files in <code>results/</code> via{" "}
        <code>/api/v1/results</code>. Nothing here is typed by hand.
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-3" data-tour="results-headline">
        <Stat label="Detection, variants seen in training" value={pct(fused.test_dev.detection_rate)}
              sub={`at ${pct(fused.test_dev.false_alarm_rate)} false alarms · AUC ${fused.test_dev.auc_roc.toFixed(3)}`} />
        <Stat label="Detection, held-out (v1) variants" value={pct(fused.test_heldout.detection_rate)}
              sub={`at ${pct(fused.test_heldout.false_alarm_rate)} false alarms · AUC ${fused.test_heldout.auc_roc.toFixed(3)}`} />
        <Stat label="Trust layer attack campaign"
              value={pct(campaignCaught(data.campaign), 0)}
              sub={`${data.campaign?.n_products ?? "?"} products · every attack type`} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Detection by manipulation family</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={familyData} margin={{ left: -10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="family" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
              <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip
                formatter={(v: number) => (Number.isNaN(v) ? "n/a" : `${v.toFixed(1)}%`)}
                contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="seen" name="seen variants" fill="hsl(214 90% 60%)" />
              <Bar dataKey="heldout" name="held-out v1" fill="hsl(42 95% 55%)" />
              <Bar dataKey="heldout_v2" name="held-out v2 (frozen)" fill="hsl(152 55% 48%)" />
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-muted-foreground">
            Source: <code>results/metrics.json</code> and <code>results/heldout_v2_v2model.json</code>. Held-out
            v2 uses manipulation methods frozen before any detector change.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>False-alarm rate by land cover (seen test, target 5%)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={faData} margin={{ left: -10, bottom: 40 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="landcover" angle={-35} textAnchor="end" interval={0}
                     tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} height={60} />
              <YAxis unit="%" tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`}
                       contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
              <Bar dataKey="fa" name="false alarms">
                {faData.map((d, i) => (
                  <Cell key={i} fill={d.fa > 5 ? "hsl(42 95% 55%)" : "hsl(214 90% 60%)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-xs text-muted-foreground">Source: <code>results/metrics.json</code> → false_alarm_by_landcover.</p>
        </CardContent>
      </Card>

      {data.robustness?.rows && (
        <Card>
          <CardHeader>
            <CardTitle>Robustness sweep (one operation applied to every patch)</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <TR>
                  <TH>condition</TH>
                  <TH>seen?</TH>
                  <TH>false alarms</TH>
                  <TH>detection</TH>
                </TR>
              </THead>
              <TBody>
                {data.robustness.rows.map((r: any) => (
                  <TR key={r.condition}>
                    <TD>{r.condition}</TD>
                    <TD className="text-xs">{r.seen_in_training ? "yes" : "no"}</TD>
                    <TD className={r.false_alarm_rate > 0.1 ? "text-verdict-bad" : ""}>{pct(r.false_alarm_rate)}</TD>
                    <TD>{pct(r.detection_rate)}</TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <p className="mt-1 text-xs text-muted-foreground">Source: <code>results/robustness.json</code>.</p>
          </CardContent>
        </Card>
      )}

      {data.campaign?.attacks && (
        <Card>
          <CardHeader>
            <CardTitle>Integrity attack campaign</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <THead>
                <TR>
                  <TH>attack</TH>
                  <TH>expected status</TH>
                  <TH>caught</TH>
                </TR>
              </THead>
              <TBody>
                {data.campaign.attacks.map((a: any) => (
                  <TR key={a.attack}>
                    <TD className="font-mono text-xs">{a.attack}</TD>
                    <TD className="text-xs">{a.expected}</TD>
                    <TD>
                      <Badge tone={a.caught_as_expected >= 1 ? "ok" : "warn"}>{pct(a.caught_as_expected, 0)}</Badge>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
            <p className="mt-1 text-xs text-muted-foreground">Source: <code>results/integrity_campaign.json</code>.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function campaignCaught(c: any): number {
  if (!c?.attacks?.length) return NaN;
  const vals = c.attacks.map((a: any) => a.caught_as_expected);
  return vals.reduce((s: number, v: number) => s + v, 0) / vals.length;
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
        <div className="text-xs text-muted-foreground">{sub}</div>
      </CardContent>
    </Card>
  );
}
