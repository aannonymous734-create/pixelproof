import { useState } from "react";
import { api, type Analysis } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/PageHeader";
import { FilePicker } from "@/components/ui/file-picker";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, FileSignature, Cog, ShieldCheck, Image as ImageIcon } from "lucide-react";

// Shows the signed capture claim and each processing step as a timeline, and marks where the chain
// breaks for a tampered product. The manifest is parsed in the browser; the verdict comes from the
// backend (image + manifest), so the two always agree.
export function Provenance() {
  const [img, setImg] = useState<File | null>(null);
  const [manifest, setManifest] = useState<File | null>(null);
  const [claim, setClaim] = useState<any | null>(null);
  const [res, setRes] = useState<Analysis | null>(null);
  const [err, setErr] = useState("");

  async function run() {
    setErr("");
    setRes(null);
    if (!img || !manifest) {
      setErr("Provide both the image and its manifest JSON.");
      return;
    }
    try {
      setClaim(JSON.parse(await manifest.text()));
    } catch {
      setErr("manifest is not valid JSON");
      return;
    }
    try {
      setRes(await api.analyse(img, manifest));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "verification failed");
    }
  }

  const steps = claim?.processing ?? [];
  const chainOk = res?.integrity.ok;
  const status = res?.integrity.status ?? "";
  // The verifier checks in order: claim → each processing step → received pixels, and stops at the first failure.
  // Find where it stopped: a step (the backend names it: "processing step N (op) is ..."), the pixels, or the claim.
  const brokenStepNo = Number(res?.reasons.map((r) => /processing step (\d+)/.exec(r)?.[1]).find(Boolean) ?? 0);
  const breakAt = !res || chainOk ? -1 : brokenStepNo ? brokenStepNo : status === "PIXELS_ALTERED" ? steps.length + 1 : 0;
  // position 0 = claim, 1..n = steps, n+1 = received pixels
  const stateAt = (pos: number): NodeState => (breakAt < 0 || pos < breakAt ? "ok" : pos === breakAt ? "broken" : "unchecked");

  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Integrity" title="Provenance timeline">
        The signed capture claim, then every processing step. A tampered product breaks the chain at a
        specific point (replaced date, forged step, wrong key, weak algorithm).
      </PageHeader>

      <Card spotlight={false} data-tour="provenance-input">
        <CardContent className="pt-5">
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <FilePicker label="Image" accept="image/*,.tif,.tiff" placeholder="Choose an image…" file={img} onChange={setImg} />
            <FilePicker label="Manifest" accept=".json" placeholder="Choose a manifest .json…" file={manifest} onChange={setManifest} />
            <Button variant="accent" className="h-11" onClick={run} disabled={!img || !manifest}>
              <ShieldCheck size={16} aria-hidden /> Verify chain
            </Button>
          </div>
          {err && (
            <p role="alert" className="mt-3 text-sm text-verdict-bad">
              {err}
            </p>
          )}
        </CardContent>
      </Card>

      {res && claim && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Chain</CardTitle>
            <Badge tone={chainOk ? "ok" : "bad"}>{res.integrity.status.replace(/_/g, " ")}</Badge>
          </CardHeader>
          <CardContent>
            <ol className="relative space-y-4 border-l border-border pl-6">
              <TimelineItem state={stateAt(0)} icon={FileSignature} title="Capture claim (signed at source)">
                <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-0.5 text-xs text-muted-foreground sm:grid-cols-[auto_minmax(0,1fr)_auto_minmax(0,1fr)]">
                  <Field k="product_id" v={claim.product_id} />
                  <Field k="source" v={claim.source} />
                  <Field k="sensor" v={claim.sensor} />
                  <Field k="capture_time" v={claim.capture_time} />
                  <Field k="key_id" v={claim.key_id} />
                  <Field k="seq" v={claim.seq} />
                  <Field k="pixel_digest" v={claim.pixel_digest?.slice(0, 20) + "…"} />
                  <Field k="algorithms" v={`${claim.hash_alg} · ${claim.sig_alg}`} />
                </dl>
              </TimelineItem>
              {steps.map((s: any, i: number) => (
                <TimelineItem key={i} state={stateAt(i + 1)} icon={Cog} title={`Processing step ${i + 1}: ${s.op}`}>
                  <div className="break-all text-xs text-muted-foreground">
                    by {s.key_id} · params {JSON.stringify(s.params ?? {})}
                  </div>
                </TimelineItem>
              ))}
              <TimelineItem state={stateAt(steps.length + 1)} icon={ImageIcon} title="Pixels received by the ground station">
                <div className="break-all text-xs text-muted-foreground">
                  digest <span className="font-mono">{res.pixel_digest.slice(0, 20)}…</span>{" "}
                  {stateAt(steps.length + 1) === "ok"
                    ? "matches the last signed digest"
                    : stateAt(steps.length + 1) === "broken"
                      ? "differs from the last signed digest"
                      : ""}
                </div>
              </TimelineItem>
            </ol>
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {res.reasons.filter((r) => !r.startsWith("content:")).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

type NodeState = "ok" | "broken" | "unchecked";

function TimelineItem({
  state,
  icon: Icon,
  title,
  children,
}: {
  state: NodeState;
  icon: typeof CheckCircle2;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <li className={cn("relative", state === "unchecked" && "opacity-50")}>
      <span className="absolute -left-[34px] flex h-5 w-5 items-center justify-center rounded-full bg-background">
        {state === "broken" ? (
          <XCircle size={18} className="text-verdict-bad" />
        ) : state === "ok" ? (
          <Icon size={16} className="text-verdict-ok" />
        ) : (
          <Icon size={16} className="text-muted-foreground" />
        )}
      </span>
      <div className="font-medium">{title}</div>
      {children}
      {state === "broken" && <div className="mt-1 text-xs font-medium text-verdict-bad">chain breaks here</div>}
      {state === "unchecked" && (
        <div className="mt-1 text-xs text-muted-foreground">not checked: verification stopped at the break above</div>
      )}
    </li>
  );
}

function Field({ k, v }: { k: string; v: unknown }) {
  return (
    <>
      <dt className="font-mono">{k}</dt>
      <dd className="truncate">{String(v ?? "—")}</dd>
    </>
  );
}
