import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { prefersReducedMotion } from "@/lib/webgl";
import { DotGlobe } from "./DotGlobe";

export interface Node3D {
  id: "satellite" | "attacker" | "ground";
  label: string;
  pos: [number, number, number];
  color: string;
}

export interface Packet {
  id: string;
  tone: string; // hex colour by verdict
  verdict: string;
  attack?: string;
}

const NODES: Node3D[] = [
  { id: "satellite", label: "satellite", pos: [2.2, 1.5, 0.4], color: "#7dd3fc" },
  { id: "attacker", label: "attacker", pos: [0.2, 1.95, 1.6], color: "#f59e0b" },
  { id: "ground", label: "ground", pos: [-2.0, -1.3, 0.8], color: "#34d399" },
];


function NodeDot({ node }: { node: Node3D }) {
  return (
    <mesh position={node.pos}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshStandardMaterial color={node.color} emissive={node.color} emissiveIntensity={0.6} />
    </mesh>
  );
}

function Link({ a, b }: { a: [number, number, number]; b: [number, number, number] }) {
  const geo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setFromPoints([new THREE.Vector3(...a), new THREE.Vector3(...b)]);
    return g;
  }, [a, b]);
  return (
    <primitive object={new THREE.Line(geo, new THREE.LineBasicMaterial({ color: "#475569" }))} />
  );
}

function FlyingPacket({ packet, onDone }: { packet: Packet; onDone: (id: string) => void }) {
  const ref = useRef<THREE.Mesh>(null);
  const t = useRef(0);
  const reduce = prefersReducedMotion();
  const sat = NODES[0].pos;
  const atk = NODES[1].pos;
  const grd = NODES[2].pos;
  useFrame((_, dt) => {
    t.current += reduce ? 0.5 : dt * 0.5;
    const p = Math.min(1, t.current);
    // satellite -> attacker -> ground
    const seg = p < 0.5 ? [sat, atk] : [atk, grd];
    const local = (p < 0.5 ? p : p - 0.5) * 2;
    if (ref.current) {
      ref.current.position.lerpVectors(
        new THREE.Vector3(...seg[0]),
        new THREE.Vector3(...seg[1]),
        local,
      );
    }
    if (p >= 1) onDone(packet.id);
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.07, 12, 12]} />
      <meshStandardMaterial color={packet.tone} emissive={packet.tone} emissiveIntensity={0.9} />
    </mesh>
  );
}

export function EarthScene({ packets, onPacketDone }: { packets: Packet[]; onPacketDone: (id: string) => void }) {
  const [frameloop] = useState<"always" | "demand">(prefersReducedMotion() ? "demand" : "always");
  return (
    <Canvas camera={{ position: [0, 0, 5.2], fov: 45 }} frameloop={frameloop} dpr={[1, 1.5]} aria-label="3D link view">
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 3, 5]} intensity={1.1} />
      <DotGlobe radius={1.4} spin={0.08} />
      {NODES.map((n) => (
        <NodeDot key={n.id} node={n} />
      ))}
      <Link a={NODES[0].pos} b={NODES[1].pos} />
      <Link a={NODES[1].pos} b={NODES[2].pos} />
      {packets.map((p) => (
        <FlyingPacket key={p.id} packet={p} onDone={onPacketDone} />
      ))}
    </Canvas>
  );
}
