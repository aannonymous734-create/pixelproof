import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  CircleUserRound,
  FlaskConical,
  GitBranch,
  Globe2,
  LayoutDashboard,
  PartyPopper,
  RadioTower,
  ScanSearch,
  ScrollText,
  Sparkles,
  BarChart3,
  Wifi,
} from "lucide-react";

export interface TourStep {
  id: string;
  /** page to open before showing the step (hash route) */
  route?: string;
  /** [data-tour] names tried in order; the first visible match is highlighted. None → centred card. */
  targets?: string[];
  icon: LucideIcon;
  title: string;
  body: string;
}

// Each step opens the real page and highlights the real panel, so the tour doubles as a demo of the app.
export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    icon: Sparkles,
    title: "Welcome to PixelProof",
    body: "A quick tour of the ground station: what each section does and where to find it. Use the buttons or the ← → keys, and skip whenever you like.",
  },
  {
    id: "nav",
    targets: ["nav"],
    icon: LayoutDashboard,
    title: "Your sections",
    body: "Sections are grouped by job: Monitor what is arriving, Verify a single patch, and Validate the defences with attacks and measured results.",
  },
  {
    id: "status",
    targets: ["status"],
    icon: Wifi,
    title: "Backend status",
    body: "Shows whether the dashboard can reach the ground-station API and which detector is loaded. Red means live figures can't refresh.",
  },
  {
    id: "overview",
    route: "/",
    targets: ["home-live", "page"],
    icon: Activity,
    title: "Overview · live activity",
    body: "Counters and the latest security events, read straight from the hash-chained audit log and refreshed every 5 seconds.",
  },
  {
    id: "analyse",
    route: "/analyse",
    targets: ["analyse-input", "page"],
    icon: ScanSearch,
    title: "Analyse a patch",
    body: "Drop any image, optionally with its signed manifest. You get two separate answers: is the provenance intact, and does the content show manipulation, with a heatmap of where.",
  },
  {
    id: "provenance",
    route: "/provenance",
    targets: ["provenance-input", "page"],
    icon: GitBranch,
    title: "Provenance timeline",
    body: "Give an image and its manifest to see the signed capture claim and every processing step. A tampered product shows exactly where the chain breaks.",
  },
  {
    id: "live",
    route: "/live",
    targets: ["live-globe", "page"],
    icon: Globe2,
    title: "Live link",
    body: "Watch downlinks travel satellite → attacker → ground, each packet coloured by the verdict it received.",
  },
  {
    id: "audit",
    route: "/audit",
    targets: ["audit-log", "page"],
    icon: ScrollText,
    title: "Audit log",
    body: "Every decision, append-only. Each entry hashes the previous one, so rewriting history breaks the chain and this page says so. Search and filter by severity.",
  },
  {
    id: "station",
    route: "/station",
    targets: ["page"],
    icon: RadioTower,
    title: "Station · trust anchor",
    body: "Which public keys this station trusts, the enforced trust policy, the detector model and the last product received. Private keys never reach this page.",
  },
  {
    id: "lab",
    route: "/lab",
    targets: ["lab-controls", "page"],
    icon: FlaskConical,
    title: "Attack lab",
    body: "Run real attack scenarios against the verifier (tampering, replay, forged signatures) and check each one is caught. Runs use temporary keys, so the real audit log is untouched.",
  },
  {
    id: "attacks",
    route: "/attacks",
    targets: ["page"],
    icon: BookOpen,
    title: "Attack guide",
    body: "Step-by-step instructions for attacking the station yourself from the attacker machine. Read-only: nothing is launched from this page.",
  },
  {
    id: "results",
    route: "/results",
    targets: ["results-headline", "page"],
    icon: BarChart3,
    title: "Measured results",
    body: "Detection rates, false alarms and robustness, read live from the reproduced result files. Nothing here is typed by hand.",
  },
  {
    id: "account",
    targets: ["account"],
    icon: CircleUserRound,
    title: "Your account",
    body: "Your profile and sign-out live here. You can replay this tour any time with “Product tour” in the menu.",
  },
  {
    id: "done",
    route: "/",
    icon: PartyPopper,
    title: "You're all set",
    body: "Start by analysing a patch, or open the attack lab and try to fool the station.",
  },
];
