// Lazy-loaded 3D scene (three.js / React Three Fiber). Renders the BodyParts3D-derived anatomy asset and the phenotype markers it is given.
// It never decides clinical state: marker states, regions and mesh tags all come from the backend payload via props.
import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { ContactShadows, Html, Line, OrbitControls, useGLTF, useProgress } from '@react-three/drei';
import * as THREE from 'three';
import { LAYER_COLORS, MESH_REGION_SYSTEM, REGION_COLORS, STATE_STYLE, SYSTEM_COLORS } from './twinTheme';
import { ASSET_URL, MESH_TAG_TO_REGION, layoutCallouts, parseNodeName, regionAnchors } from './twinModel';

const PRESET_ANGLE = { front: 0, back: Math.PI, left: Math.PI / 2, right: -Math.PI / 2 };
const ZOOM = {
  body: { pos: [0, 0.95, 3.5], target: [0, 0.86, 0] },
  torso: { pos: [0, 1.12, 1.75], target: [0, 1.08, 0] },
  head: { pos: [0, 1.56, 0.85], target: [0, 1.55, 0] },
};
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const _v = new THREE.Vector3();

function Loader() {
  const { progress } = useProgress();
  return (
    <Html center>
      <div className="text-cyan-100 text-xs font-mono whitespace-nowrap bg-slate-900/80 border border-cyan-500/30 rounded px-3 py-2" role="status">
        Loading anatomy model… {progress.toFixed(0)}%
      </div>
    </Html>
  );
}

function baseLook(info, viewMode) {
  const { layer, tag } = info;
  if (layer === 'skin') {
    if (viewMode === 'skeleton') return { visible: false };
    return { color: '#5ec8e0', opacity: viewMode === 'systems' ? 0.07 : 0.14, emissive: '#0891b2', emissiveIntensity: 0.35, transparent: true };
  }
  if (viewMode === 'systems') return { color: SYSTEM_COLORS[MESH_REGION_SYSTEM[tag]] || '#94a3b8', opacity: 1, emissive: '#000000', emissiveIntensity: 0 };
  const color = layer === 'skeleton' ? LAYER_COLORS.skeleton : REGION_COLORS[tag] || LAYER_COLORS[layer] || '#cbd5e1';
  const dim = viewMode === 'skeleton' && layer !== 'skeleton';
  return { color, opacity: dim ? 0.3 : 1, transparent: dim, emissive: '#000000', emissiveIntensity: 0 };
}

function Body({ viewMode, layers, tintByTag, selectedTags, onSelectRegion, interactive }) {
  const gltf = useGLTF(ASSET_URL);
  const [hoverTag, setHoverTag] = useState(null);
  const root = useMemo(() => {
    const r = gltf.scene.clone(true);
    const meshes = [];
    r.traverse((o) => {
      if (!o.isMesh) return;
      const info = parseNodeName(o.name) || parseNodeName(o.parent && o.parent.name);
      if (!info) return;
      o.userData.twin = info;
      // the asset stores positions only (smaller download); smooth normals are computed once and cached with the shared geometry
      if (!o.geometry.attributes.normal) o.geometry.computeVertexNormals();
      o.material = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.05 });
      if (info.layer === 'skin') {
        o.raycast = () => null;      // translucent skin must not swallow clicks meant for the organs beneath it
        o.renderOrder = 2;
      }
      meshes.push(o);
    });
    r.userData.meshes = meshes;
    return r;
  }, [gltf]);

  useEffect(() => () => root.userData.meshes.forEach((m) => m.material.dispose()), [root]);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    for (const m of root.userData.meshes) {
      const info = m.userData.twin;
      const look = baseLook(info, viewMode);
      const mat = m.material;
      m.visible = look.visible !== false && layers[info.layer] !== false;
      if (!m.visible) continue;
      mat.color.set(look.color);
      mat.emissive.set(look.emissive);
      mat.emissiveIntensity = look.emissiveIntensity;
      mat.transparent = !!look.transparent || look.opacity < 1;
      mat.opacity = look.opacity;
      mat.depthWrite = info.layer !== 'skin';
      const tint = info.layer !== 'skin' ? tintByTag[info.tag] : null;
      if (tint) {
        const c = new THREE.Color(STATE_STYLE[tint].color);
        mat.color.lerp(c, 0.6);
        mat.emissive.copy(c);
        mat.emissiveIntensity = 0.45;
      }
      if (info.layer !== 'skin' && selectedTags.includes(info.tag)) {
        if (!tint) mat.emissive.set('#22d3ee');
        mat.emissiveIntensity = tint ? 0.95 : 0.5;
      }
      if (hoverTag && info.tag === hoverTag && info.layer !== 'skin') {
        if (!tint) mat.emissive.set('#67e8f9');
        mat.emissiveIntensity = Math.max(mat.emissiveIntensity, 0.3);
      }
      mat.needsUpdate = true;
    }
    invalidate();
  }, [root, viewMode, layers, tintByTag, selectedTags, hoverTag, invalidate]);

  const handlers = interactive ? {
    onClick: (e) => {
      e.stopPropagation();
      const info = e.object.userData.twin;
      if (info && onSelectRegion) onSelectRegion(MESH_TAG_TO_REGION[info.tag] || null);
    },
    onPointerOver: (e) => { e.stopPropagation(); const i = e.object.userData.twin; setHoverTag(i ? i.tag : null); document.body.style.cursor = 'pointer'; },
    onPointerOut: () => { setHoverTag(null); document.body.style.cursor = ''; },
  } : {};
  useEffect(() => () => { document.body.style.cursor = ''; }, []);
  return <primitive object={root} {...handlers} />;
}

function Marker({ m, selected, animate, onSelect }) {
  const halo = useRef();
  const root = useRef();
  const st = STATE_STYLE[m.state] || STATE_STYLE.pending;
  const pulse = animate && (m.state === 'confirmed' || m.state === 'hypothetical');
  useFrame(({ clock, camera }) => {
    // keep a roughly constant on-screen size, so close-up views (head, torso) are not covered by markers
    if (root.current && m.region !== 'systemic') {
      root.current.getWorldPosition(_v);
      root.current.scale.setScalar(Math.min(1, Math.max(0.25, camera.position.distanceTo(_v) / 3.4)));
    }
    if (!halo.current) return;
    const k = pulse ? 1 + 0.45 * (0.5 + 0.5 * Math.sin(clock.elapsedTime * 2.6)) : 1.25;
    halo.current.scale.setScalar(k);
    halo.current.material.opacity = pulse ? 0.55 - 0.3 * (k - 1) : 0.25;
  });
  const r = m.region === 'systemic' ? 0.03 : 0.022;
  const click = (e) => { e.stopPropagation(); onSelect && onSelect(m.region); };
  if (m.region === 'systemic') {
    return (
      <group position={m.anchor} onClick={click}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} renderOrder={10}>
          <ringGeometry args={[0.36, 0.385, 64]} />
          <meshBasicMaterial color={st.color} transparent opacity={0.9} depthTest={false} />
        </mesh>
        <mesh ref={halo} rotation={[-Math.PI / 2, 0, 0]} renderOrder={9}>
          <ringGeometry args={[0.39, 0.42, 64]} />
          <meshBasicMaterial color={st.color} transparent opacity={0.3} depthTest={false} />
        </mesh>
      </group>
    );
  }
  return (
    <group ref={root} position={m.anchor} onClick={click}>
      {m.onlyNegated ? (
        <mesh renderOrder={10}>
          <torusGeometry args={[r, r * 0.22, 8, 32]} />
          <meshBasicMaterial color={st.color} transparent opacity={0.95} depthTest={false} />
        </mesh>
      ) : (
        <mesh renderOrder={10}>
          <sphereGeometry args={[selected ? r * 1.35 : r, 20, 20]} />
          <meshBasicMaterial color={st.color} transparent opacity={0.95} depthTest={false} />
        </mesh>
      )}
      {!m.onlyNegated && (
        <mesh ref={halo} renderOrder={9}>
          <sphereGeometry args={[r * 1.9, 20, 20]} />
          <meshBasicMaterial color={st.color} transparent opacity={0.25} depthTest={false} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

// Leader line from a fixed callout to its (possibly rotating) marker; endpoints recomputed every frame from the spin angle.
function Leader({ from, anchor, angleRef, color }) {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    _v.set(anchor[0], anchor[1], anchor[2]).applyAxisAngle(THREE.Object3D.DEFAULT_UP, angleRef.current);
    ref.current.geometry.setPositions([from[0], from[1], from[2], _v.x, _v.y, _v.z]);
  });
  return <Line ref={ref} points={[from, anchor]} color={color} lineWidth={1.2} transparent opacity={0.75} depthTest={false} renderOrder={8} />;
}

function Callout({ m, selected, onSelect }) {
  const st = STATE_STYLE[m.state] || STATE_STYLE.pending;
  const shown = m.items.slice(0, 3);
  return (
    <Html position={m.labelPos} center zIndexRange={[30, 0]} style={{ pointerEvents: 'auto' }}>
      <button type="button" onClick={() => onSelect && onSelect(m.region)}
        className={`text-left w-44 rounded-md border bg-slate-950/80 backdrop-blur px-2 py-1.5 shadow-lg transition-colors ${selected ? 'border-cyan-300' : 'border-cyan-500/25 hover:border-cyan-400/60'}`}
        aria-label={`${m.label}: ${m.items.length} finding(s)`}>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ background: st.color }} />
          <span className="text-[11px] font-semibold text-cyan-50 truncate">{m.label}</span>
        </div>
        {shown.map((i) => (
          <div key={i.id} className="text-[10px] text-slate-300 truncate pl-3.5" title={`${i.text} → ${i.hpo_label || ''} ${i.hpo_id || ''}`}>
            <span style={{ color: (STATE_STYLE[i.state] || {}).color }}>●</span> {i.state === 'hypothetical' ? `${i.op === 'removed' ? '−' : '+'} ` : ''}{i.hpo_label || i.text}
            {i.state === 'negated' ? ' (absent)' : ''}
          </div>
        ))}
        {m.items.length > 3 && <div className="text-[10px] text-slate-400 pl-3.5">+{m.items.length - 3} more</div>}
      </button>
    </Html>
  );
}

function Rig({ preset, zoom, resetToken, autoRotate, reduced, angleRef, spinRef, controlsRef }) {
  const { camera, invalidate } = useThree();
  const goal = useRef({ angle: 0, pos: new THREE.Vector3(...ZOOM.body.pos), target: new THREE.Vector3(...ZOOM.body.target), active: true });
  useEffect(() => {
    goal.current.angle = PRESET_ANGLE[preset] ?? 0;
    const z = ZOOM[zoom] || ZOOM.body;
    goal.current.pos.set(...z.pos);
    goal.current.target.set(...z.target);
    goal.current.active = true;
    invalidate();
  }, [preset, zoom, resetToken, invalidate]);
  useFrame((_, dt) => {
    const g = goal.current;
    const c = controlsRef.current;
    if (autoRotate && !reduced) {
      angleRef.current = wrap(angleRef.current + dt * 0.3);
      g.angle = angleRef.current;
    }
    if (g.active) {
      const k = reduced ? 1 : 1 - Math.pow(0.002, dt);
      angleRef.current = wrap(angleRef.current + wrap(g.angle - angleRef.current) * k);
      camera.position.lerp(g.pos, k);
      if (c) c.target.lerp(g.target, k);
      const done = Math.abs(wrap(g.angle - angleRef.current)) < 1e-3 && camera.position.distanceTo(g.pos) < 1e-3;
      if (done) g.active = false;
      else invalidate();
      if (c) c.update();
    }
    if (spinRef.current) spinRef.current.rotation.y = angleRef.current;
  });
  return null;
}

function Platform({ lowPower }) {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]}>
        <ringGeometry args={[0.44, 0.47, 96]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.55} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.0005, 0]}>
        <circleGeometry args={[0.6, 96]} />
        <meshBasicMaterial color="#0e7490" transparent opacity={0.18} />
      </mesh>
      {!lowPower && <ContactShadows position={[0, 0.002, 0]} scale={2.2} blur={2.4} opacity={0.55} far={1.2} frames={1} />}
    </group>
  );
}

export function TwinCanvas({
  manifest, catalogue, markers, viewMode = 'anatomy', layers = {}, selectedRegion = null, onSelectRegion, autoRotate = false,
  reducedMotion = false, lowPower = false, preset = 'front', zoom = 'body', resetToken = 0, compact = false, paused = false,
}) {
  const angleRef = useRef(0);
  const spinRef = useRef();
  const controlsRef = useRef();
  const anchors = useMemo(() => regionAnchors(manifest), [manifest]);
  const placed = useMemo(() => layoutCallouts(markers || [], anchors), [markers, anchors]);
  const tintByTag = useMemo(() => {
    const out = {};
    const rank = (s) => ['negated', 'relative_finding', 'pending', 'uncertain', 'unverified', 'confirmed', 'hypothetical'].indexOf(s);
    for (const m of markers || []) {
      if (!m.tint) continue;
      for (const tag of ((catalogue || {})[m.region] || {}).mesh_regions || []) {
        if (!out[tag] || rank(m.tint) > rank(out[tag])) out[tag] = m.tint;
      }
    }
    return out;
  }, [markers, catalogue]);
  const selectedTags = useMemo(() => ((catalogue || {})[selectedRegion] || {}).mesh_regions || [], [catalogue, selectedRegion]);
  const animate = !reducedMotion && !paused;
  return (
    <Canvas
      frameloop={animate ? 'always' : 'demand'}
      dpr={lowPower ? 1 : [1, 1.75]}
      camera={{ position: ZOOM.body.pos, fov: compact ? 30 : 34, near: 0.05, far: 30 }}
      gl={{ antialias: !lowPower, powerPreference: lowPower ? 'low-power' : 'high-performance', alpha: true }}
      onPointerMissed={() => onSelectRegion && onSelectRegion(null)}
      aria-label="3D anatomical model with phenotype markers"
    >
      <ambientLight intensity={0.55} />
      <hemisphereLight args={['#bae6fd', '#0f172a', 0.6]} />
      <directionalLight position={[2.5, 4, 3]} intensity={1.4} />
      <directionalLight position={[-3, 2, -2]} intensity={0.5} color="#67e8f9" />
      <Rig preset={preset} zoom={zoom} resetToken={resetToken} autoRotate={autoRotate && animate} reduced={reducedMotion}
        angleRef={angleRef} spinRef={spinRef} controlsRef={controlsRef} />
      <Suspense fallback={<Loader />}>
        <group ref={spinRef}>
          <Body viewMode={viewMode} layers={layers} tintByTag={tintByTag} selectedTags={selectedTags} onSelectRegion={onSelectRegion} interactive={!compact} />
          {placed.map((m) => (
            <Marker key={m.region} m={m} selected={m.region === selectedRegion} animate={animate} onSelect={onSelectRegion} />
          ))}
        </group>
        {!compact && placed.map((m) => (
          <React.Fragment key={`c-${m.region}`}>
            <Leader from={m.labelPos} anchor={m.anchor} angleRef={angleRef} color={(STATE_STYLE[m.state] || {}).color || '#22d3ee'} />
            <Callout m={m} selected={m.region === selectedRegion} onSelect={onSelectRegion} />
          </React.Fragment>
        ))}
        <Platform lowPower={lowPower || compact} />
      </Suspense>
      <OrbitControls ref={controlsRef} makeDefault enablePan={!compact} enableZoom={!compact} minDistance={0.5} maxDistance={6}
        target={ZOOM.body.target} enableDamping={!reducedMotion} />
    </Canvas>
  );
}

export default TwinCanvas;
