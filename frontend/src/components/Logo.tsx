/** Abstract product mark: a 3×3 pixel grid with one verified pixel. Neutral — no team or school identity. */
export function Logo({ size = 28 }: { size?: number }) {
  const cells = Array.from({ length: 9 }, (_, i) => ({ x: (i % 3) * 9 + 1, y: Math.floor(i / 3) * 9 + 1, hot: i === 4 }));
  return (
    <svg width={size} height={size} viewBox="0 0 29 29" role="img" aria-label="PixelProof">
      <defs>
        <linearGradient id="pxp-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="hsl(199 95% 62%)" />
          <stop offset="1" stopColor="hsl(252 90% 70%)" />
        </linearGradient>
      </defs>
      {cells.map((c, i) => (
        <rect
          key={i}
          x={c.x}
          y={c.y}
          width="8"
          height="8"
          rx="2"
          fill={c.hot ? "url(#pxp-g)" : "hsl(0 0% 100% / 0.16)"}
        />
      ))}
    </svg>
  );
}
