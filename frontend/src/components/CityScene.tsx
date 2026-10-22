import { Canvas } from "@react-three/fiber";
import { ContactShadows, OrbitControls, Sky, Text } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import type { Building, TwinState } from "../types";

function BuildingModel({ building, selected, onSelect }: {
  building: Building; selected: boolean; onSelect: (id: string) => void;
}) {
  const height = building.kind === "clinic" ? 2.6 : building.kind === "office" ? 3.3 : 1.8;
  const color = selected ? "#60a5fa" : building.kind === "clinic" ? "#d7e6ed" : building.kind === "office" ? "#91a7bb" : "#b8c8b7";
  const hasShed = building.appliances.some(a => a.tier === 3 && a.status === "off");
  return (
    <group position={[building.x, 0, building.z]} onClick={(e) => { e.stopPropagation(); onSelect(building.id); }}>
      <mesh position={[0, height / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.1, height, 1.8]} />
        <meshStandardMaterial color={color} roughness={0.82} />
      </mesh>
      <mesh position={[0, height + 0.06, 0]} castShadow>
        <boxGeometry args={[2.25, 0.12, 1.95]} />
        <meshStandardMaterial color="#34495e" />
      </mesh>
      {Array.from({ length: 2 }).map((_, i) => (
        <mesh key={`solar-${i}`} position={[-0.48 + i * 0.72, height + 0.14, 0]} rotation={[-0.12, 0, 0]}>
          <boxGeometry args={[0.58, 0.035, 0.8]} />
          <meshStandardMaterial color="#153e70" metalness={0.25} roughness={0.3} />
        </mesh>
      ))}
      {Array.from({ length: 2 }).map((_, i) => (
        <mesh key={`window-${i}`} position={[-0.48 + i * 0.96, height * 0.55, 0.916]}>
          <boxGeometry args={[0.36, 0.42, 0.025]} />
          <meshStandardMaterial color={hasShed ? "#e05252" : "#79d6d0"} emissive={hasShed ? "#9c2020" : "#174f55"} emissiveIntensity={0.35} />
        </mesh>
      ))}
      <mesh position={[0, 0.035, 0]}>
        <boxGeometry args={[2.35, 0.07, 2.05]} />
        <meshStandardMaterial color={selected ? "#3b82f6" : "#52616b"} />
      </mesh>
      <Text position={[0, height + 0.62, 0]} fontSize={0.25} color="#eaf2f8" anchorX="center" outlineWidth={0.015} outlineColor="#0a111b">
        {building.name}
      </Text>
      {hasShed && <Text position={[0, height + 0.35, 0]} fontSize={0.19} color="#ff7474" anchorX="center">LOAD SHED</Text>}
    </group>
  );
}

function PowerLine({ start, end, active }: { start: [number, number, number]; end: [number, number, number]; active: boolean }) {
  const points = useMemo(() => [new THREE.Vector3(...start), new THREE.Vector3(...end)], [start, end]);
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);
  return <line geometry={geometry}>
    <lineBasicMaterial color={active ? "#4de0b2" : "#e45c68"} linewidth={2} />
  </line>;
}

function SceneContents({ state, selectedId, onSelect }: {
  state: TwinState; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return <>
    <color attach="background" args={["#0a111b"]} />
    <fog attach="fog" args={["#0a111b", 17, 34]} />
    <Sky sunPosition={[4, 8, 3]} turbidity={8} rayleigh={0.4} />
    <ambientLight intensity={1.1} />
    <directionalLight position={[5, 10, 5]} intensity={2} castShadow />
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.08, 0]} receiveShadow>
      <planeGeometry args={[30, 24]} />
      <meshStandardMaterial color="#16232d" roughness={1} />
    </mesh>
    {Array.from({ length: 8 }).map((_, i) => (
      <mesh key={`road-h-${i}`} position={[0, -0.045, -9 + i * 2.5]}>
        <boxGeometry args={[30, 0.025, 0.55]} />
        <meshStandardMaterial color="#29343d" />
      </mesh>
    ))}
    {Array.from({ length: 10 }).map((_, i) => (
      <mesh key={`road-v-${i}`} position={[-13.5 + i * 3, -0.04, 0]}>
        <boxGeometry args={[0.55, 0.025, 24]} />
        <meshStandardMaterial color="#29343d" />
      </mesh>
    ))}
    {/* Main virtual grid connection and feeders */}
    <mesh position={[0, 1.2, 5.8]}>
      <boxGeometry args={[1.4, 2.4, 0.8]} />
      <meshStandardMaterial color="#73869a" metalness={0.4} />
    </mesh>
    <Text position={[0, 2.8, 5.8]} fontSize={0.3} color="#f2f7fb" anchorX="center">GRID SUBSTATION</Text>
    {state.buildings.map(b => (
      <PowerLine key={`line-${b.id}`} start={[0, 0.1, 5.4]} end={[b.x, 0.1, b.z]} active={state.frequencyHz > state.shedThresholdHz} />
    ))}
    {state.buildings.map(b => <BuildingModel key={b.id} building={b} selected={selectedId === b.id} onSelect={onSelect} />)}
    <ContactShadows position={[0, -0.02, 0]} opacity={0.35} scale={30} blur={2.2} far={10} />
    <OrbitControls makeDefault minDistance={9} maxDistance={27} maxPolarAngle={Math.PI / 2.05} />
  </>;
}

export default function CityScene({ state, selectedId, onSelect }: {
  state: TwinState; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return <Canvas shadows camera={{ position: [11, 11, 15], fov: 45 }} dpr={[1, 1.5]}>
    <SceneContents state={state} selectedId={selectedId} onSelect={onSelect} />
  </Canvas>;
}