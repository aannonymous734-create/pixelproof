/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        verdict: {
          ok: "hsl(152 62% 48%)", warn: "hsl(40 96% 56%)",
          bad: "hsl(0 82% 62%)", info: "hsl(204 94% 62%)", mute: "hsl(240 6% 60%)",
        },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontFamily: {
        sans: ['"Geist Variable"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono Variable"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(12px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 hsl(var(--ring-color) / 0.45)" },
          "100%": { boxShadow: "0 0 0 10px hsl(var(--ring-color) / 0)" },
        },
        "flow-x": { from: { backgroundPosition: "0 0" }, to: { backgroundPosition: "24px 0" } },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both",
        shimmer: "shimmer 3.2s linear infinite",
        float: "float 5s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.8s ease-out infinite",
        "flow-x": "flow-x 0.9s linear infinite",
      },
    },
  },
  plugins: [],
};
