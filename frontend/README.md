# Ground-station dashboard (frontend)

React + TypeScript (strict) + Vite, Tailwind CSS, shadcn/ui-style primitives (Radix UI +
class-variance-authority), Three.js via `@react-three/fiber` / `@react-three/drei`, and Motion.
Every value shown comes from the real FastAPI backend; nothing is mocked in the built app.

## Pages

| Page | What it shows | Backend source |
|---|---|---|
| Overview (`/`) | hero with a 3D globe of the satellite→attacker→ground link, headline figures (animated counters), the two-answers idea, how a patch travels | `GET /api/v1/results` |
| Analyse (`/#/analyse`) | verdict, integrity vs content axes, heatmap overlay (opacity slider), class probabilities, reasons, digest | `POST /api/v1/analyse` |
| Live link | 3D Earth (WebGL) with satellite→attacker→ground packets coloured by verdict, + audit-log table | `GET /api/v1/ledger` (polled) |
| Provenance | signed capture claim + processing steps as a timeline; marks where the chain breaks | `POST /api/v1/analyse` + the manifest |
| Results | detection by family (seen / held-out v1 / held-out v2), false alarms by land cover, robustness, campaign | `GET /api/v1/results` |
| Jury attack guide | endpoints, message format, attacker modes, transparent-MITM commands (read-only, copy buttons) | static |

## Run

The build is committed to `../pixelproof/static/app`, so the jury only needs Python:

```bash
# from the repo root
pip install -r requirements.txt
uvicorn pixelproof.api:app --host 0.0.0.0 --port 8000
# open http://localhost:8000   (the classic single-file dashboard stays at /classic)
```

## Rebuild (needs Node ≥ 20)

```bash
cd frontend
npm ci
npm run build          # tsc -b && vite → ../pixelproof/static/app
npm test               # Vitest: verdict rendering, upload validation, WebGL fallback, results summary
npm run test:e2e       # Playwright smoke tests (needs the ground station running on :8000)
```

Design system: dark Geist-based theme, spotlight cards, shimmer/animated-border accents and scroll reveals,
built from shadcn-style primitives in `src/components/ui/` (tokens in `src/index.css`, `tailwind.config.js`).
The Geist fonts are bundled by Vite (`@fontsource-variable/*`), so nothing is fetched from a CDN.

## Engineering notes

- **Offline**: relative asset base, no CDN, bundled fonts, procedurally generated dotted globe (no texture
  download). Works inside the isolated VMs.
- **No GPU**: the 3D scene is lazy-loaded and split into its own chunk; `hasWebGL()` falls back to a
  2D SVG link diagram. `prefers-reduced-motion` stops the animation.
- **Accessibility**: keyboard navigation, visible focus, verdicts shown by icon + text + colour (never
  colour alone), alt text on images, ARIA labels on controls.
- **Security**: a strict `Content-Security-Policy` (see `index.html`), no `dangerouslySetInnerHTML`,
  client-side type/size checks before upload (the backend still validates), configurable API base URL
  (gear icon in the top bar).
- **Anonymity**: neutral product name, empty `author` in `package.json`, no logos or team names.
