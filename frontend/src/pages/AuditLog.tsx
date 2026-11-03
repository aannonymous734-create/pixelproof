import { useEffect, useMemo, useState } from "react";
import { Search, XCircle } from "lucide-react";
import { api, type LedgerEntry, type Severity } from "@/lib/api";
import { shortHash, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/PageHeader";
import { Select } from "@/components/ui/select";

const TONE: Record<Severity, "bad" | "warn" | "mute"> = { critical: "bad", warning: "warn", info: "mute" };

export function AuditLog() {
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [chainValid, setChainValid] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [severity, setSeverity] = useState<"all" | Severity>("all");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .ledger(300)
        .then((l) => {
          if (!alive) return;
          setEntries(l.entries);
          setChainValid(l.chain_valid);
          setError("");
        })
        .catch((e) => alive && setError(e instanceof Error ? e.message : "could not reach the backend"));
    load();
    const iv = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(iv);
    };
  }, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (entries ?? []).filter(
      (e) =>
        (severity === "all" || e.severity === severity) &&
        (!q || [e.product_id, e.verdict, e.integrity, e.channel, e.content_type].some((v) => (v ?? "").toLowerCase().includes(q))),
    );
  }, [entries, severity, query]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Accountability"
        title="Audit log"
        actions={
          <Badge tone={chainValid === false ? "bad" : chainValid ? "ok" : "mute"}>
            hash chain {chainValid === null ? "…" : chainValid ? "valid" : "BROKEN"}
          </Badge>
        }
      >
        Every decision the ground station makes is appended to a tamper-evident log: each entry contains the hash of the previous
        one, so editing or deleting any past entry breaks the chain and this page says so.
      </PageHeader>

      <Card spotlight={false} data-tour="audit-log">
        <CardContent className="space-y-4 pt-5">
          <div className="flex flex-wrap items-center gap-3">
            <label className="relative min-w-0 flex-[1_1_220px]">
              <span className="sr-only">Search the log</span>
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search product, verdict, status…"
                className="h-10 w-full rounded-lg border border-white/10 bg-white/[0.03] pl-9 pr-3 text-sm transition-colors placeholder:text-muted-foreground/60 hover:border-white/20 focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </label>
            <Select
              aria-label="Filter by severity"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as "all" | Severity)}
              wrapperClassName="flex-[0_0_auto]"
            >
              <option value="all">all severities</option>
              <option value="critical">critical</option>
              <option value="warning">warning</option>
              <option value="info">info</option>
            </Select>
            <span className="w-full text-xs text-muted-foreground sm:w-auto">
              {entries ? `${rows.length} of ${entries.length} entries` : ""} · refreshes every 3 s
            </span>
          </div>

          {error ? (
            <p role="alert" className="flex items-center gap-2 text-sm text-verdict-bad">
              <XCircle size={16} aria-hidden /> {error}
            </p>
          ) : entries === null ? (
            <div className="h-40 animate-pulse rounded-lg bg-white/[0.04]" />
          ) : entries.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              The log is empty: this station has not made any decision yet. Analyse an image or start a downlink.
            </p>
          ) : rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No entry matches this filter.</p>
          ) : (
            <>
            {/* phones: one stacked block per entry */}
            <ul className="divide-y divide-white/[0.06] md:hidden">
              {rows.map((e) => (
                <li key={e.hash} className="space-y-1 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge tone={TONE[e.severity]}>{e.severity}</Badge>
                    <span className="min-w-0 flex-1 truncate font-medium">{e.verdict.replace(/_/g, " ")}</span>
                    <span className="shrink-0 text-xs text-muted-foreground" title={e.time}>
                      {timeAgo(e.time)}
                    </span>
                  </div>
                  <div className="text-xs">
                    <span className="font-mono">{e.integrity}</span>
                    <span className="text-muted-foreground"> → {e.action} · {e.channel}</span>
                  </div>
                  <div className="break-all text-xs text-muted-foreground">
                    {e.product_id ?? "no product id"} · content {e.content_type} ({e.score?.toFixed(2)}) ·{" "}
                    <span className="font-mono" title={e.hash}>
                      {shortHash(e.hash)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-4 font-medium">time</th>
                    <th className="py-2 pr-4 font-medium">event</th>
                    <th className="py-2 pr-4 font-medium">source</th>
                    <th className="py-2 pr-4 font-medium">severity</th>
                    <th className="py-2 pr-4 font-medium">result</th>
                    <th className="py-2 font-medium">details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {rows.map((e) => (
                    <tr key={e.hash}>
                      <td className="whitespace-nowrap py-2.5 pr-4 text-muted-foreground" title={e.time}>
                        {timeAgo(e.time)}
                      </td>
                      <td className="py-2.5 pr-4 font-medium">{e.verdict.replace(/_/g, " ")}</td>
                      <td className="py-2.5 pr-4 text-muted-foreground">{e.channel}</td>
                      <td className="py-2.5 pr-4">
                        <Badge tone={TONE[e.severity]}>{e.severity}</Badge>
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="font-mono text-xs">{e.integrity}</span>
                        <span className="text-muted-foreground"> → {e.action}</span>
                      </td>
                      <td className="py-2.5 text-xs text-muted-foreground">
                        {e.product_id ?? "no product id"} · content {e.content_type} ({e.score?.toFixed(2)}) ·{" "}
                        <span className="font-mono" title={e.hash}>
                          {shortHash(e.hash)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
