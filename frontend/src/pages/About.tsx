import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { PageHeader } from "@/components/PageHeader";

const QUESTIONS = [
  {
    t: "Provenance",
    q: "Who produced this image, and when?",
    a: "A signed claim names the source, sensor and capture date. We can verify that the claim was signed by a key we trust.",
    limit: "It says nothing about whether the source itself was honest.",
  },
  {
    t: "Integrity",
    q: "Has it changed since it was signed?",
    a: "The signature covers a SHA-256 digest of the pixels. Change one pixel, the date or any other field and verification fails.",
    limit: "It proves “unchanged since signing”, not “true”.",
  },
  {
    t: "Visual authenticity",
    q: "Does the picture show what really happened?",
    a: "Only statistical forensics can say anything: traces of resampling, copy-move, splicing or inpainting. The answer is evidence, never proof.",
    limit: "A manipulation can be missed, and unusual but genuine images can be flagged.",
  },
];

const LIMITS = [
  "A signature does not prove an image is true. If the source is compromised and signs a fake, only the content detector can notice, and it misses some (see the Attack lab, scenario F1).",
  "Splicing and copy-move are the hardest families on manipulation methods the detector has never seen; the Results page shows the exact numbers.",
  "Smoothing (blur, JPEG 2000) of a genuine image can cause false alarms. There is no separate “inconclusive” outcome yet: such images are flagged and quarantined for review.",
  "The heatmap is an evidence map, not a precise segmentation. Localisation is weak except for copy-move.",
  "Only the official 8-bit EuroSAT RGB patches were evaluated. Multispectral and 16-bit inputs are converted but their false-alarm rate is not measured.",
  "The VirtualBox lab is provided as scripts; it has not been booted by the authors. The Docker and network-namespace labs were run.",
];

export function About() {
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Documentation" title="About PixelProof">
        A software-only platform that tells an analyst two independent things about a satellite image patch: was it produced by a
        trusted source and left untouched, and does its content show signs of manipulation.
      </PageHeader>

      <section aria-labelledby="three-h">
        <h2 id="three-h" className="mb-3 text-sm font-medium text-muted-foreground">
          Three different questions
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {QUESTIONS.map((x, i) => (
            <Reveal key={x.t} delay={i * 0.07}>
              <Card className="h-full p-5">
                <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-primary">{x.t}</div>
                <h3 className="mt-1 text-lg font-semibold tracking-tight">{x.q}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{x.a}</p>
                <p className="mt-3 text-xs text-verdict-warn">Limit: {x.limit}</p>
              </Card>
            </Reveal>
          ))}
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-2">
        <Card spotlight={false}>
          <CardHeader>
            <CardTitle>How a patch travels</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
              <li>
                <span className="text-foreground">Satellite node</span> hashes the pixels, builds a canonical manifest and signs it with
                Ed25519. The private key never leaves this node.
              </li>
              <li>
                <span className="text-foreground">Untrusted link.</span> An attacker may modify, replay, strip or swap the message.
              </li>
              <li>
                <span className="text-foreground">Ground station</span> loads its own trusted public keys, verifies the signature, recomputes
                the hash, checks freshness, runs the content detector, decides, and appends the decision to the audit log.
              </li>
            </ol>
          </CardContent>
        </Card>
        <Card spotlight={false}>
          <CardHeader>
            <CardTitle>Method and data</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm leading-relaxed text-muted-foreground">
            <p>
              Data: the official EuroSAT RGB release (Sentinel-2, 64×64 patches). Each source patch belongs to exactly one of train,
              validation, seen-test or held-out-test by a hash of its id, so a patch and its manipulated copy never cross splits.
            </p>
            <p>
              The alarm threshold is calibrated on clean validation patches for a fixed false-alarm budget; test sets are never used to tune
              it. Every number on the <Link className="text-primary hover:underline" to="/results">Results</Link> page is read from a
              reproducible result file.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card spotlight={false}>
        <CardHeader>
          <CardTitle>Limitations, stated openly</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-muted-foreground">
            {LIMITS.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card spotlight={false}>
        <CardHeader>
          <CardTitle>Reproduce it</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <pre className="overflow-x-auto rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-xs text-foreground">
            {`python -m pytest -q                                  # automated tests\npython -m simulation.run_attack --all --n 20        # every attack scenario, with evidence\npython scripts/check_numbers.py docs/REPORT.md      # every report number resolves to a result file\ndocker compose up --build                            # satellite -> attacker -> ground`}
          </pre>
          <p>
            Other tools: <Link className="text-primary hover:underline" to="/provenance">provenance timeline</Link>,{" "}
            <Link className="text-primary hover:underline" to="/live">live link</Link>,{" "}
            <Link className="text-primary hover:underline" to="/attacks">jury attack guide</Link>. Full documentation is in the <code>docs/</code>{" "}
            folder of the repository.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
