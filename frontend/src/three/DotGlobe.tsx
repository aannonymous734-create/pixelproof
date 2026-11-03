import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { prefersReducedMotion } from "@/lib/webgl";

/** Point on a sphere from latitude/longitude in degrees (y up, +z faces the camera at lon 0). */
export function latLon(lat: number, lon: number, r: number): [number, number, number] {
  const la = (lat * Math.PI) / 180;
  const lo = (lon * Math.PI) / 180;
  return [r * Math.cos(la) * Math.sin(lo), r * Math.sin(la), r * Math.cos(la) * Math.cos(lo)];
}

// Cheap smooth "continent" field from a few sines: no texture download, fully offline, tiny bundle.
function land(x: number, y: number, z: number): number {
  return (
    Math.sin(2.1 * x + 0.7) * Math.cos(1.9 * y - 0.4) +
    Math.sin(2.7 * z + 1.3) * Math.cos(2.3 * x + y) +
    0.6 * Math.sin(5.1 * y + z) +
    0.35 * Math.sin(7.3 * x - 3.1 * z)
  );
}

/** A dotted globe: bright "land" dots, a sparse dim ocean, a dark core and a soft atmosphere. */
export function DotGlobe({ radius = 1.4, count = 9000, spin = 0 }: { radius?: number; count?: number; spin?: number }) {
  const group = useRef<THREE.Group>(null);
  const reduce = prefersReducedMotion();

  const { positions, colors } = useMemo(() => {
    const pos: number[] = [];
    const col: number[] = [];
    const land_c = new THREE.Color("#7dd3fc");
    const sea_c = new THREE.Color("#2f6190");
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i++) {
      const y = 1 - (i / (count - 1)) * 2;
      const rr = Math.sqrt(1 - y * y);
      const th = golden * i;
      const x = Math.cos(th) * rr;
      const z = Math.sin(th) * rr;
      const isLand = land(x, y, z) > 0.1;
      if (!isLand && i % 3 !== 0) continue; // keep every 3rd ocean dot so the sphere still reads as round
      const c = isLand ? land_c : sea_c;
      pos.push(x * radius, y * radius, z * radius);
      col.push(c.r, c.g, c.b);
    }
    return { positions: new Float32Array(pos), colors: new Float32Array(col) };
  }, [count, radius]);

  useFrame((_, dt) => {
    if (group.current && spin && !reduce) group.current.rotation.y += dt * spin;
  });

  return (
    <group ref={group}>
      <mesh>
        <sphereGeometry args={[radius * 0.985, 48, 48]} />
        <meshBasicMaterial color="#04060c" />
      </mesh>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" array={positions} count={positions.length / 3} itemSize={3} />
          <bufferAttribute attach="attributes-color" array={colors} count={colors.length / 3} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial size={0.028} vertexColors transparent opacity={0.95} depthWrite={false} sizeAttenuation />
      </points>
      <mesh>
        <sphereGeometry args={[radius * 1.1, 48, 48]} />
        <meshBasicMaterial color="#38bdf8" transparent opacity={0.045} side={THREE.BackSide} />
      </mesh>
    </group>
  );
}
