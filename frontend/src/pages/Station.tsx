import { useCallback, useEffect, useState } from "react";
import { Check, Copy, KeyRound, RadioTower, ShieldCheck, XCircle } from "lucide-react";
import { api, type Identity, type Station as StationInfo } from "@/lib/api";
import { cn, shortHash, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { PageHeader } from "@/components/PageHeader";
import { VerdictBadge } from "@/components/Verdict";
import type { Verdict } from "@/lib/api";

const ROLE_LABEL: Record<string, string> = { source: "satellite (signs captures)", processor: "ground processor (signs processing steps)" };

export function Station() {
  const [st, setSt] = useState<StationInfo | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .station()
      .then((s) => {
        setSt(s);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "could not reach the backend"));
  }, []);

  useEffect(() => {
    load();
    const iv = setInterval(load, 5000);
    return () => clearInterval(iv);
  }, [load]);

  const last = st?.last_downlink ?? null;
  const ageSeconds = last && st ? (new Date(st.server_time).getTime() - new Date(last.time).getTime()) / 1000 : null;
  const link: { label: string; tone: "ok" | "warn" | "mute" } =
    ageSeconds === null ? { label: "no downlink received yet", tone: "mute" } : ageSeconds < 120 ? { label: "receiving", tone: "ok" } : { label: "idle", tone: "warn" };

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Trust anchor" title="Satellite and ground station">
        Who this ground station trusts, and what it last received. This page shows public information only: private keys live
        on the satellite machine and never reach the ground station, the attacker or the browser.
      </PageHeader>

      {error && (
        <Card spotlight={false}>
          <CardContent className="flex items-center gap-3 pt-5 text-sm text-verdict-bad" role="alert">
            <XCircle size={18} aria-hidden /> {error}
          </CardContent>
        </Card>
      )}
      {!st && !error && (
        <div className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} spotlight={false} className="h-32 animate-pulse" />
          ))}
        </div>
      )}

      {st && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <Card className="p-5">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                <RadioTower size={14} aria-hidden /> Transmission
              </div>
              <div className="mt-3 flex items-center gap-2">
                <Badge tone={link.tone}>{link.label}</Badge>
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                {last ? `last downlink ${timeAgo(last.time, st.server_time)}` : "Start a downlink (the satellite node) or run the demo."}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">{st.downlinks_received} downlink(s) received in total</div>
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                <ShieldCheck size={14} aria-hidden /> Last received product
              </div>
              {last ? (
                <div className="mt-3 space-y-2 text-sm">
                  <VerdictBadge verdict={last.verdict as Verdict} />
                  <div className="font-mono text-xs text-muted-foreground">{last.product_id}</div>
                  <div className="text-xs text-muted-foreground">
                    integrity {last.integrity} · action {last.action}
                  </div>
                </div>
              ) : (
                <p className="mt-3 text-sm text-muted-foreground">Nothing received yet.</p>
              )}
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
                <KeyRound size={14} aria-hidden /> Audit log
              </div>
              <div className="mt-3">
                <Badge tone={st.audit_chain_valid ? "ok" : "bad"}>hash chain {st.audit_chain_valid ? "valid" : "BROKEN"}</Badge>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Replay memory: {st.replay_memory.products} product(s) from {st.replay_memory.sources} source(s), rebuilt from this log if
                the station restarts.
              </p>
            </Card>
          </div>

          <Card spotlight={false}>
            <CardHeader>
              <CardTitle>Trusted identities (public keys)</CardTitle>
            </CardHeader>
            <CardContent>
              {st.identities.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  The registry is empty, so every signed message will be rejected as UNKNOWN_KEY. Create the demo keys with{" "}
                  <code>python -m pixelproof.cli keys-init</code>.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-muted-foreground">
                      <tr>
                        <th className="py-2 pr-4 font-medium">key id</th>
                        <th className="py-2 pr-4 font-medium">role</th>
                        <th className="py-2 pr-4 font-medium">status</th>
                        <th className="py-2 font-medium">SHA-256 fingerprint of the public key</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.06]">
                      {st.identities.map((i) => (
                        <IdentityRow key={i.key_id} i={i} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Compare this fingerprint with the one printed on the satellite machine to confirm that the ground station trusts the right
                key. A key that arrives inside a message is never trusted.
              </p>
            </CardContent>
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            <Card spotlight={false}>
              <CardHeader>
                <CardTitle>Trust policy (enforced)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <Line k="hash" v={st.trust_policy.hash} />
                <Line k="signature" v={st.trust_policy.signature} />
                <Line k="algorithms pinned" v={st.trust_policy.pinned ? "yes (anything else is rejected)" : "no"} />
                <Line k="future-dated captures" v={`rejected beyond ${st.trust_policy.max_future_minutes} min`} />
                <Line k="replay protection" v={st.trust_policy.replay_protection} />
              </CardContent>
            </Card>
            <Card spotlight={false}>
              <CardHeader>
                <CardTitle>Content detector</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5 text-sm">
                <Line k="model version" v={st.detector.version ?? "—"} />
                <Line k="mode" v={st.detector.mode} />
                <Line k="model file SHA-256" v={shortHash(st.detector.model_sha256)} mono />
                <Line
                  k="matches the model card"
                  v={st.detector.model_card_match === null ? "no model card found" : st.detector.model_card_match ? "yes" : "NO: the model file changed"}
                />
                <Line k="attack lab" v={st.lab_mode ? "enabled (demo server)" : "disabled (safe default)"} />
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function Line({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground">{k}</span>
      <span className={cn("text-right", mono && "font-mono text-xs")}>{v}</span>
    </div>
  );
}

function IdentityRow({ i }: { i: Identity }) {
  const toast = useToast();
  const [copied, setCopied] = useState(false);
  const grouped = i.fingerprint_sha256.match(/.{1,8}/g)?.join(" ") ?? i.fingerprint_sha256;
  return (
    <tr>
      <td className="py-2.5 pr-4 font-mono text-xs">{i.key_id}</td>
      <td className="py-2.5 pr-4 text-muted-foreground">{ROLE_LABEL[i.role] ?? i.role}</td>
      <td className="py-2.5 pr-4">
        <Badge tone={i.revoked ? "bad" : "ok"}>{i.revoked ? "revoked" : "trusted"}</Badge>
      </td>
      <td className="py-2.5">
        <div className="flex items-center gap-2">
          <code className="break-all text-xs" title={i.fingerprint_sha256}>
            {grouped.slice(0, 35)}…
          </code>
          <Button
            size="icon"
            variant="ghost"
            aria-label={`Copy fingerprint of ${i.key_id}`}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(i.fingerprint_sha256);
                setCopied(true);
                toast({ tone: "ok", title: "Fingerprint copied", description: i.key_id });
                setTimeout(() => setCopied(false), 1500);
              } catch {
                toast({ tone: "bad", title: "Could not copy", description: "Select the text and copy it manually." });
              }
            }}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </Button>
        </div>
      </td>
    </tr>
  );
}
