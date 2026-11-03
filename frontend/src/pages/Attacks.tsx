import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { Copy, Check } from "lucide-react";

type Tone = "bad" | "warn" | "mute";

// Same list as pixelproof/integrity_attacks.py: name, what the attacker does, status the ground station returns.
const ATTACKS: [string, string, string, Tone][] = [
  ["pixel_inpaint", "Erases a region of the image and fills it in.", "PIXELS_ALTERED", "bad"],
  ["pixel_copy_move", "Duplicates one region of the image over another.", "PIXELS_ALTERED", "bad"],
  ["pixel_resample", "Rescales or rotates the patch.", "PIXELS_ALTERED", "bad"],
  ["lsb_embed", "Hides 512 bits in least-significant bits: invisible to the eye.", "PIXELS_ALTERED", "bad"],
  ["date_replace", "Changes the capture date but keeps the original signature.", "BAD_SIGNATURE", "bad"],
  ["date_replace_resign", "Changes the date and re-signs with the attacker's own key.", "UNKNOWN_KEY", "bad"],
  ["algorithm_downgrade", "Edits pixels, then claims a weak hash (md5) and recomputes it.", "WEAK_ALGORITHM", "warn"],
  ["forged_processing", "Hides an edit behind a fake “crop” step signed by the attacker.", "CHAIN_BROKEN", "bad"],
  ["manifest_swap", "Attaches a valid manifest to a different genuine image.", "PIXELS_ALTERED", "bad"],
  ["replay", "Re-sends a genuine product that was already delivered.", "REPLAY", "warn"],
  ["strip_manifest", "Edits pixels and removes the provenance record; content analysis must decide.", "NO_PROVENANCE", "mute"],
];

const RELAY = `# on the attacker machine (inside the isolated lab; it routes between 10.56.1.0/24 and 10.56.2.0/24)
cd /opt/pixelproof
PYTHONPATH=. /home/pxp/venv/bin/python simulation/attacker.py \\
  --listen 10.56.2.1:8081 --ground http://10.56.2.30:8000 \\
  --mode random --rate 0.7 --log /home/pxp/runtime/attacker_log.jsonl`;

const TRANSPARENT = `# transparent redirect: the satellite is unaware, this machine is its router. Undo: sudo iptables -t nat -F
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A PREROUTING -p tcp -d 10.56.2.30 --dport 8000 \\
  -j DNAT --to-destination 10.56.2.1:8081`;

const FORGE = `# send a downlink straight to the ground station
curl -s http://10.56.2.30:8000/api/v1/ingest \\
  -H 'Content-Type: application/json' \\
  -d '{"image_png_b64":"<base64 PNG>","manifest":{ ... }}'`;

const READ = `# read the verdicts and the tamper-evident audit log
curl -s http://10.56.2.30:8000/api/v1/ledger | python3 -m json.tool`;

export function Attacks() {
  return (
    <div className="space-y-4">
      <PageHeader eyebrow="Adversarial validation" title="Attack guide">
        How to attack the ground station yourself from the attacker machine. This page is read-only: it never
        launches anything (the Attack lab page runs synthetic scenarios). Full lab instructions: <code>docs/VM_LAB.md</code>.
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle>1 · Message format (a downlink)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            <code>POST /api/v1/ingest</code> with a base64 PNG and the signed manifest. The ground station
            verifies the signature over the pixels and returns a verdict. Every decision, accepted or rejected,
            is appended to the hash-chained audit log, which you can read back below.
          </p>
          <CodeBlock text={FORGE} />
          <CodeBlock text={READ} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2 · Attacker modes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-muted-foreground">
            Run the relay with <code>--mode passthrough | random | &lt;one attack below&gt;</code>.{" "}
            <code>--rate</code> is the share of messages tampered with (<code>0.7</code> = 70%); the rest pass
            through untouched as a control. Each attack should produce the status shown.
          </p>
          <ul className="divide-y divide-white/[0.06] rounded-lg border border-white/[0.08]">
            {ATTACKS.map(([name, what, status, tone]) => (
              <li
                key={name}
                className="grid gap-1 px-3 py-2.5 text-sm sm:grid-cols-[minmax(0,190px)_minmax(0,1fr)_auto] sm:items-center sm:gap-4"
              >
                <code className="text-xs">{name}</code>
                <span className="text-muted-foreground">{what}</span>
                <Badge tone={tone} className="justify-self-start font-mono text-[11px]">
                  {status}
                </Badge>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">
            <code>replay</code> and <code>manifest_swap</code> reuse an earlier message; until one has been seen, the
            relay passes the message through untouched.
          </p>
          <CodeBlock text={RELAY} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3 · Transparent man-in-the-middle</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            The satellite (<code>10.56.1.10</code>) still sends to the ground station (<code>10.56.2.30</code>), but
            its only route there goes through the attacker (<code>10.56.1.1 | 10.56.2.1</code>). One NAT rule
            silently hands its traffic to the relay above. The cryptographic layer still catches every change because
            the verdict depends on the signature over the pixels, not the route.
          </p>
          <CodeBlock text={TRANSPARENT} />
          <p className="text-xs text-muted-foreground">
            No ARP spoofing is needed: it only matters on a flat network, and this lab is routed. Without VMs, the
            same setup runs in Docker (<code>docker compose -f docker-compose.mitm.yml up</code>) or with Linux
            network namespaces (<code>sudo python lab/netns_lab.py</code>).
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function CodeBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="overflow-auto rounded bg-muted p-3 pr-10 text-xs leading-relaxed">{text}</pre>
      <Button
        size="icon"
        variant="ghost"
        aria-label="copy to clipboard"
        className="absolute right-1 top-1 h-7 w-7"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          } catch {
            /* clipboard blocked; ignore */
          }
        }}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </Button>
    </div>
  );
}
