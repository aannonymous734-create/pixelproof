import { useCallback, useRef, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { api, VERDICT_TONE, type Analysis } from "@/lib/api";
import { cn, pct } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { VerdictBadge } from "@/components/Verdict";
import { PageHeader } from "@/components/PageHeader";
import { FilePicker } from "@/components/ui/file-picker";
import { UploadCloud, Loader2, ScanSearch } from "lucide-react";

const MAX_MB = 2;

// HSL triplets matching the verdict colours in tailwind.config.js (used for the glow and animated border).
const TONE_HSL = {
  ok: "152 62% 48%",
  warn: "40 96% 56%",
  bad: "0 82% 62%",
  info: "204 94% 62%",
  mute: "240 6% 60%",
} as const;

export function Analyse() {
  const [img, setImg] = useState<File | null>(null);
  const [manifest, setManifest] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [res, setRes] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [opacity, setOpacity] = useState(0.6);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback((f: File | null) => {
    setError("");
    setRes(null);
    if (!f) return;
    if (!/\.(png|jpe?g|tif?f|webp|bmp)$/i.test(f.name)) {
      setError("Please choose an image (PNG, JPEG, TIFF, WebP or BMP).");
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`Image is larger than ${MAX_MB} MB (the backend limit).`);
      return;
    }
    setImg(f);
    setPreview(URL.createObjectURL(f));
  }, []);

  async function run() {
    if (!img) return;
    setBusy(true);
    setError("");
    try {
      setRes(await api.analyse(img, manifest ?? undefined));
    } catch (e) {
      setError(e instanceof Error ? e.message : "analysis failed");
    } finally {
      setBusy(false);
    }
  }

  const c = res?.content;
  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Ground station" title="Analyse a patch">
        Drop an image and (optionally) its signed manifest. The ground station answers two questions:
        is the provenance intact, and does the content show manipulation?
      </PageHeader>

      <Card spotlight={false} data-tour="analyse-input">
        <CardContent className="pt-5">
          <div
            role="button"
            tabIndex={0}
            aria-label="Upload an image to analyse"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              pick(e.dataTransfer.files?.[0] ?? null);
            }}
            className={cn(
              "flex cursor-pointer items-center justify-center gap-5 rounded-xl border border-dashed px-4 py-10 text-center transition-colors",
              dragging ? "border-primary bg-primary/10" : "border-white/15 hover:border-primary/60 hover:bg-white/[0.03]",
              preview && "sm:justify-start sm:text-left",
            )}
          >
            {preview ? (
              <img
                src={preview}
                alt="selected patch"
                className="h-20 w-20 rounded-lg border border-white/10 object-cover"
                style={{ imageRendering: "pixelated" }}
              />
            ) : (
              <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.04]">
                <UploadCloud className="text-primary" aria-hidden />
              </span>
            )}
            <div>
              <div className="text-sm font-medium">{img ? img.name : "Click or drag an image here"}</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                max {MAX_MB} MB · PNG, JPEG, TIFF, WebP, BMP · any size (tiled, never resized)
              </div>
            </div>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,image/*"
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
            <FilePicker
              label="Signed manifest (optional)"
              accept=".json,application/json"
              placeholder="Choose a manifest .json…"
              file={manifest}
              onChange={setManifest}
              className="sm:flex-1"
            />
            <Button variant="accent" className="h-11 sm:min-w-[150px]" onClick={run} disabled={!img || busy}>
              {busy ? <Loader2 className="animate-spin" size={16} /> : <ScanSearch size={16} aria-hidden />}
              {busy ? "Analysing…" : "Analyse"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="mt-3 text-sm text-verdict-bad">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      {res && c && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card
            spotlight={false}
            className="border-beam md:col-span-2"
            style={{ ["--beam" as string]: TONE_HSL[VERDICT_TONE[res.verdict]] }}
          >
            <div
              aria-hidden
              className="absolute inset-x-0 -top-14 mx-auto h-28 w-1/2 rounded-full opacity-25 blur-3xl"
              style={{ background: `hsl(${TONE_HSL[VERDICT_TONE[res.verdict]]})` }}
            />
            <CardContent className="relative flex flex-wrap items-center justify-between gap-3 pt-5">
              <div className="flex flex-wrap items-center gap-3">
                <VerdictBadge verdict={res.verdict} large />
                <span className="text-sm text-muted-foreground">
                  action: <span className="font-medium text-foreground">{res.action}</span>
                </span>
              </div>
              <code className="text-xs text-muted-foreground">digest {res.pixel_digest?.slice(0, 16)}…</code>
            </CardContent>
          </Card>

          {/* Axis 1: integrity */}
          <Card>
            <CardHeader>
              <CardTitle>Integrity · is provenance intact?</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Badge tone={res.integrity.ok ? "ok" : "bad"}>{res.integrity.status.replace(/_/g, " ")}</Badge>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {res.reasons
                  .filter((r) => !r.startsWith("content:") && !c.evidence.includes(r))
                  .map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
              </ul>
            </CardContent>
          </Card>

          {/* Axis 2: content */}
          <Card>
            <CardHeader>
              <CardTitle>Content · forensic analysis</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-2">
                <Badge tone={c.manipulated ? "bad" : "ok"}>
                  {c.manipulated ? c.type.replace(/_/g, " ") : "no traces found"}
                </Badge>
                {c.reencoding_probability !== undefined && c.reencoding_probability >= 0.5 && (
                  <Badge tone="info">re-encoded patch: stricter threshold</Badge>
                )}
              </div>
              <ScoreBar score={c.manipulation_score} threshold={c.threshold} />
              <div className="space-y-1">
                {Object.entries(c.probabilities).map(([k, v]) => (
                  <ProbRow key={k} label={k.replace(/_/g, " ")} value={v} />
                ))}
              </div>
              {c.evidence.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                  {c.evidence.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              )}
              {c.input_note && <p className="text-xs text-muted-foreground">{c.input_note}</p>}
            </CardContent>
          </Card>

          {/* Heatmap */}
          {res.heatmap_png_b64 && (
            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle>Where the evidence is</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-start gap-6">
                  <figure className="space-y-1">
                    <div className="relative" style={{ width: 256, height: 256 }}>
                      <img
                        src={preview}
                        alt="uploaded patch"
                        className="absolute inset-0 h-full w-full rounded"
                        style={{ imageRendering: "pixelated", objectFit: "contain" }}
                      />
                      <img
                        src={`data:image/png;base64,${res.heatmap_png_b64}`}
                        alt="evidence heatmap overlay"
                        className="absolute inset-0 h-full w-full rounded"
                        style={{ opacity, imageRendering: "pixelated", objectFit: "contain" }}
                      />
                    </div>
                    <figcaption className="text-xs text-muted-foreground">patch with heatmap overlay</figcaption>
                  </figure>
                  <div className="w-full max-w-xs space-y-2">
                    <label className="text-sm" htmlFor="op">
                      overlay opacity: {Math.round(opacity * 100)}%
                    </label>
                    <Slider
                      id="op"
                      min={0}
                      max={1}
                      step={0.05}
                      value={[opacity]}
                      onValueChange={([v]) => setOpacity(v)}
                      aria-label="heatmap opacity"
                    />
                    <p className="text-xs text-muted-foreground">
                      Red marks pixels whose noise, smoothness or block-matching evidence is furthest from
                      authentic sensor statistics.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

/** A bar that grows from 0 to `fraction` (instantly for users who prefer reduced motion). */
function GrowBar({ fraction, className, delay = 0 }: { fraction: number; className: string; delay?: number }) {
  const reduce = useReducedMotion();
  const w = `${Math.max(0, Math.min(1, fraction)) * 100}%`;
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { width: 0 }}
      animate={{ width: w }}
      transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
    />
  );
}

function ScoreBar({ score, threshold }: { score: number; threshold: number }) {
  return (
    <div>
      <div className="mb-1.5 flex justify-between text-xs text-muted-foreground">
        <span>manipulation score {score.toFixed(3)}</span>
        <span>alarm threshold {threshold.toFixed(3)}</span>
      </div>
      <div className="relative h-3 w-full rounded-full bg-white/[0.07]" role="img"
           aria-label={`score ${score.toFixed(3)} versus threshold ${threshold.toFixed(3)}`}>
        <GrowBar
          fraction={score}
          className={cn("h-full rounded-full", score >= threshold ? "bg-verdict-bad" : "bg-verdict-ok")}
        />
        <div className="absolute top-[-3px] h-[18px] w-0.5 rounded bg-foreground" style={{ left: `${threshold * 100}%` }}
             title="threshold" />
      </div>
    </div>
  );
}

function ProbRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-40 shrink-0 text-muted-foreground">{label}</span>
      <div className="h-1.5 flex-1 rounded-full bg-white/[0.07]">
        <GrowBar fraction={value} delay={0.1} className="h-full rounded-full bg-primary/80" />
      </div>
      <span className="w-12 text-right tabular-nums">{pct(value)}</span>
    </div>
  );
}
