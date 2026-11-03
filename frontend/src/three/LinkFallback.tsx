// 2D SVG fallback for the link view when WebGL is unavailable (no-GPU VMs). Same information,
// no 3D: the three nodes, the path, and a count of recent verdicts.
export function LinkFallback({ counts }: { counts: Record<string, number> }) {
  const nodes = [
    { x: 60, y: 40, label: "satellite", color: "#7dd3fc" },
    { x: 220, y: 90, label: "attacker", color: "#f59e0b" },
    { x: 120, y: 180, label: "ground", color: "#34d399" },
  ];
  return (
    <svg viewBox="0 0 300 220" className="h-72 w-full" role="img" aria-label="satellite to attacker to ground link diagram">
      <line x1={nodes[0].x} y1={nodes[0].y} x2={nodes[1].x} y2={nodes[1].y} stroke="#475569" strokeWidth={2} />
      <line x1={nodes[1].x} y1={nodes[1].y} x2={nodes[2].x} y2={nodes[2].y} stroke="#475569" strokeWidth={2} />
      {nodes.map((n) => (
        <g key={n.label}>
          <circle cx={n.x} cy={n.y} r={10} fill={n.color} />
          <text x={n.x + 14} y={n.y + 4} fill="currentColor" fontSize={11}>
            {n.label}
          </text>
        </g>
      ))}
      <text x={10} y={210} fill="currentColor" fontSize={10}>
        recent: {Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ") || "none yet"}
      </text>
    </svg>
  );
}
