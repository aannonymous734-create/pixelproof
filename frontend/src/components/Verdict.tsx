import { Badge } from "@/components/ui/badge";
import { VERDICT_TONE, type Verdict as V } from "@/lib/api";
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle, ShieldQuestion } from "lucide-react";

const ICON: Record<V, typeof CheckCircle2> = {
  VERIFIED: CheckCircle2,
  SIGNED_BUT_SUSPICIOUS: AlertTriangle,
  ALTERED_AFTER_CAPTURE: XCircle,
  SUSPICIOUS: HelpCircle,
  UNVERIFIED_NO_TRACES: ShieldQuestion,
};

// Verdicts are shown by icon + text + colour, never colour alone (accessibility).
export function VerdictBadge({ verdict, large = false }: { verdict: V; large?: boolean }) {
  const tone = VERDICT_TONE[verdict];
  const Icon = ICON[verdict];
  return (
    <Badge tone={tone} className={large ? "gap-2 px-3 py-1.5 text-sm" : "gap-1.5"}>
      <Icon size={large ? 18 : 14} aria-hidden />
      {verdict.replace(/_/g, " ")}
    </Badge>
  );
}
