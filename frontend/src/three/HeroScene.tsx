import { useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { prefersReducedMotion } from "@/lib/webgl";
import { DotGlobe, latLon } from "./DotGlobe";

const R = 1.5;
const SAT = new THREE.Vector3(...latLon(38, 52, 2.55)); // satellite, above the limb
const ATK = new THREE.Vector3(...latLon(22, -38, R)); // attacker relay on the surface
const GND = new THREE.Vector3(...latLon(-12, 24, R)); // ground station

// Arc that bows away from the globe: control point is the chord midpoint pushed outwards.
function arc(a: THREE.Vector3, b: THREE.Vector3, lift: number) {
  const mid = a.clone().add(b).multiplyScalar(0.5);
  const ctrl = mid.clone().normalize().multiplyScalar(mid.length() + lift);
  return new THREE.QuadraticBezierCurve3(a, ctrl, b);
}

function ArcLine({ curve, color }: { curve: THREE.Curve<THREE.Vector3>; color: string }) {
  const line = useMemo(
    () =>
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints(curve.getPoints(64)),
        new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 }),
      ),
    [curve, color],
  );
  return <primitive object={line} />;
}

function Marker({ pos, color, pulse }: { pos: THREE.Vector3; color: string; pulse?: boolean }) {
  const halo = useRef<THREE.Mesh>(null);
  const reduce = prefersReducedMotion();
  useFrame(({ clock }) => {
    if (!halo.current || !pulse || reduce) return;
    const k = (clock.elapsedTime % 1.6) / 1.6;
    halo.current.scale.setScalar(1 + k * 3);
    (halo.current.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - k);
  });
  return (
    <group position={pos}>
      <mesh>
        <sphereGeometry args={[0.055, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh ref={halo}>
        <sphereGeometry args={[0.055, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={pulse ? 0.5 : 0.18} depthWrite={false} />
      </mesh>
    </group>
  );
}

// A downlink packet: satellite -> attacker (hostile hop, amber) -> ground (verified, green).
function Packet({ offset, up, down }: { offset: number; up: THREE.Curve<THREE.Vector3>; down: THREE.Curve<THREE.Vector3> }) {
  const ref = useRef<THREE.Mesh>(null);
  const reduce = prefersReducedMotion();
  const cyan = useMemo(() => new THREE.Color("#7dd3fc"), []);
  const amber = useMemo(() => new THREE.Color("#fbbf24"), []);
  const green = useMemo(() => new THREE.Color("#34d399"), []);
  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    const t = reduce ? 0.3 : ((clock.elapsedTime / 5 + offset) % 1);
    const first = t < 0.5;
    m.position.copy((first ? up : down).getPoint(first ? t * 2 : (t - 0.5) * 2));
    (m.material as THREE.MeshBasicMaterial).color.copy(first ? (t > 0.4 ? amber : cyan) : green);
  });
  return (
    <mesh ref={ref}>
      <sphereGeometry args={[0.04, 12, 12]} />
      <meshBasicMaterial color="#7dd3fc" />
    </mesh>
  );
}

function Rig() {
  const g = useRef<THREE.Group>(null);
  const reduce = prefersReducedMotion();
  const up = useMemo(() => arc(SAT, ATK, 0.5), []);
  const down = useMemo(() => arc(ATK, GND, 0.35), []);
  useFrame(({ clock, pointer }) => {
    if (!g.current || reduce) return;
    // gentle sway + pointer parallax; the nodes stay on the visible hemisphere
    g.current.rotation.y += (Math.sin(clock.elapsedTime * 0.18) * 0.28 + pointer.x * 0.22 - g.current.rotation.y) * 0.04;
    g.current.rotation.x += (-0.12 + pointer.y * -0.12 - g.current.rotation.x) * 0.04;
  });
  return (
    <group ref={g} rotation={[-0.12, 0, 0]}>
      <DotGlobe radius={R} />
      <mesh rotation={[Math.PI / 2.35, 0.35, 0]}>
        <torusGeometry args={[2.55, 0.004, 8, 160]} />
        <meshBasicMaterial color="#7dd3fc" transparent opacity={0.22} />
      </mesh>
      <ArcLine curve={up} color="#7dd3fc" />
      <ArcLine curve={down} color="#34d399" />
      <Marker pos={SAT} color="#7dd3fc" />
      <Marker pos={ATK} color="#fbbf24" pulse />
      <Marker pos={GND} color="#34d399" />
      <Packet offset={0} up={up} down={down} />
      <Packet offset={0.5} up={up} down={down} />
    </group>
  );
}

export default function HeroScene({ active = true }: { active?: boolean }) {
  const reduce = prefersReducedMotion();
  return (
    <Canvas
      camera={{ position: [0, 0, 6.2], fov: 40 }}
      frameloop={reduce ? "demand" : active ? "always" : "never"}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: true }}
      aria-label="Rotating globe: a satellite downlink crossing an attacker relay to the ground station"
    >
      <Rig />
    </Canvas>
  );
}
