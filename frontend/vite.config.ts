import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

// Built files go to pixelproof/static/app, served by FastAPI (StaticFiles mount at /app, and the
// index is also served at "/"). base "/app/" makes asset URLs resolve to /app/assets/... at BOTH
// paths. It stays same-origin, so it still works offline inside the VMs.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  resolve: { alias: { "@": resolve(__dirname, "src") } },
  build: {
    outDir: resolve(__dirname, "../pixelproof/static/app"),
    emptyOutDir: true,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // split the heavy 3D libs so the rest of the app loads fast and the scene lazy-loads
        manualChunks: { three: ["three", "@react-three/fiber", "@react-three/drei"] },
      },
    },
  },
  // Development server (npm run dev): the page is served by Vite on :5173 and every /api call is forwarded to the
  // ground station, so no CORS setting is needed. Point it elsewhere with PXP_API=http://host:port.
  // /auth-api/* goes to the Laravel auth backend's /api/* (php artisan serve --port=8001); override with PXP_AUTH_API.
  // The built app (npm run build → served by FastAPI on :8000) calls Laravel on :8001 directly instead.
  server: {
    host: "localhost",
    proxy: {
      "/api": process.env.PXP_API ?? "http://127.0.0.1:8000",
      "/auth-api": {
        target: process.env.PXP_AUTH_API ?? "http://127.0.0.1:8001",
        rewrite: (p) => p.replace(/^\/auth-api/, "/api"),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"], exclude: ["tests/e2e/**", "node_modules/**"],
  },
});
