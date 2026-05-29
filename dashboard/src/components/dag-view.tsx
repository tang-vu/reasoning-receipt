"use client";

/**
 * Three.js Canvas wrapper for the rr-trace/3 reasoning DAG.
 *
 * Lifted out as a client-only module because Three.js touches `window` and
 * static export ('output: export') chokes on SSR. The parent imports this via
 * `dynamic(() => import(...), { ssr: false })`.
 */

import { Suspense, useEffect, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Html, OrbitControls, Stars } from "@react-three/drei";
import type * as THREE from "three";

import {
  type DagGraph,
  type GraphEdge,
  type GraphNode,
  nodeColor,
} from "@/lib/trace-to-graph";
import { useDagStore } from "@/lib/dag-store";

const SCENE_SCALE = 1.8;

function scaledPos(n: GraphNode): [number, number, number] {
  return [n.position.x * SCENE_SCALE, n.position.y * SCENE_SCALE, n.position.z * SCENE_SCALE];
}

function NodeSphere({ node, visible }: { node: GraphNode; visible: boolean }) {
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const select = useDagStore((s) => s.select);
  const ref = useRef<THREE.Mesh>(null);
  const isSelected = selectedNodeId === node.id;
  const color = nodeColor(node);

  // Gentle bobbing motion. Selected node bobs faster + glows brighter.
  useFrame((state) => {
    if (!ref.current) return;
    const t = state.clock.getElapsedTime();
    const base = node.position.y * SCENE_SCALE;
    ref.current.position.y = base + Math.sin(t * (isSelected ? 2.5 : 0.8) + node.position.x) * 0.05;
  });

  const radius =
    node.kind === "claim"
      ? 0.22
      : node.kind === "supervisor" || node.kind === "critic_audit"
        ? 0.18
        : node.kind === "stance"
          ? 0.16
          : 0.1;

  if (!visible) return null;

  return (
    <group>
      <mesh
        ref={ref}
        position={scaledPos(node)}
        onClick={(e) => {
          e.stopPropagation();
          select(isSelected ? null : node.id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          document.body.style.cursor = "pointer";
        }}
        onPointerOut={() => {
          document.body.style.cursor = "default";
        }}
      >
        <sphereGeometry args={[radius, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isSelected ? 1.2 : 0.4}
          roughness={0.4}
          metalness={0.3}
        />
      </mesh>
      <Html
        position={[
          node.position.x * SCENE_SCALE,
          node.position.y * SCENE_SCALE + radius + 0.18,
          node.position.z * SCENE_SCALE,
        ]}
        center
        distanceFactor={8}
        style={{ pointerEvents: "none" }}
      >
        <div
          className="whitespace-nowrap rounded-md border border-white/10 bg-black/70 px-2 py-0.5 text-[10px] font-mono text-white/90 backdrop-blur"
          style={{ opacity: isSelected ? 1 : 0.7 }}
        >
          {node.label}
        </div>
      </Html>
    </group>
  );
}

function EdgeLine({
  edge,
  byId,
  visible,
}: {
  edge: GraphEdge;
  byId: Map<string, GraphNode>;
  visible: boolean;
}) {
  const from = byId.get(edge.from);
  const to = byId.get(edge.to);
  const ref = useRef<THREE.BufferGeometry>(null);
  const points = useMemo(() => {
    if (!from || !to) return new Float32Array();
    const a = scaledPos(from);
    const b = scaledPos(to);
    return new Float32Array([a[0], a[1], a[2], b[0], b[1], b[2]]);
  }, [from, to]);

  useEffect(() => {
    if (ref.current) ref.current.setDrawRange(0, 2);
  }, []);

  if (!from || !to || !visible) return null;
  const opacity = Math.max(0.18, Math.min(1, edge.weight));
  const color = nodeColor(to);

  return (
    <line>
      <bufferGeometry ref={ref}>
        <bufferAttribute
          attach="attributes-position"
          args={[points, 3]}
        />
      </bufferGeometry>
      <lineBasicMaterial color={color} transparent opacity={opacity} />
    </line>
  );
}

function ReplayDriver({ totalSteps }: { totalSteps: number }) {
  const isPlaying = useDagStore((s) => s.isPlaying);
  const setStep = useDagStore((s) => s.setStep);
  const step = useDagStore((s) => s.step);

  useFrame((_, delta) => {
    if (!isPlaying) return;
    const next = step + delta * 4; // ~4 nodes/sec
    if (next >= totalSteps) {
      setStep(totalSteps);
      useDagStore.setState({ isPlaying: false });
    } else {
      setStep(next);
    }
  });
  return null;
}

export function DagView({ graph }: { graph: DagGraph }) {
  const setTotalSteps = useDagStore((s) => s.setTotalSteps);

  // Order nodes for replay: claim first, then supervisor + audit, then stances,
  // then leaves. Same order edges follow (we lazy-cheat: edge visible iff both
  // endpoints visible).
  const orderedNodes = useMemo(() => {
    const order: Record<string, number> = {
      claim: 0,
      supervisor: 1,
      critic_audit: 1,
      stance: 2,
      critic_dim: 3,
      evidence: 4,
      counter_argument: 4,
      sensitivity: 4,
      falsifiable: 4,
      prior_context: 4,
    };
    return [...graph.nodes].sort(
      (a, b) => (order[a.kind] ?? 9) - (order[b.kind] ?? 9),
    );
  }, [graph.nodes]);

  useEffect(() => {
    setTotalSteps(orderedNodes.length);
  }, [orderedNodes.length, setTotalSteps]);

  const visibleStep = useDagStore((s) => s.step);
  const visibleIds = useMemo(() => {
    const n = visibleStep === 0 ? orderedNodes.length : Math.ceil(visibleStep);
    return new Set(orderedNodes.slice(0, n).map((node) => node.id));
  }, [orderedNodes, visibleStep]);

  const byId = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph.nodes]);

  return (
    <Canvas
      camera={{ position: [0, 1.5, 7], fov: 50 }}
      style={{ background: "radial-gradient(ellipse at center, #0b1424 0%, #050912 70%)" }}
    >
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1.2} />
      <pointLight position={[-10, -5, -5]} intensity={0.6} color="#a78bfa" />
      <Suspense fallback={null}>
        <Stars radius={50} depth={20} count={1500} factor={2} fade speed={0.5} />
        {graph.nodes.map((n) => (
          <NodeSphere key={n.id} node={n} visible={visibleIds.has(n.id)} />
        ))}
        {graph.edges.map((e, i) => (
          <EdgeLine
            key={`${e.from}->${e.to}-${i}`}
            edge={e}
            byId={byId}
            visible={visibleIds.has(e.from) && visibleIds.has(e.to)}
          />
        ))}
      </Suspense>
      <ReplayDriver totalSteps={orderedNodes.length} />
      <OrbitControls
        enablePan={false}
        minDistance={3}
        maxDistance={14}
        autoRotate
        autoRotateSpeed={0.4}
      />
    </Canvas>
  );
}
