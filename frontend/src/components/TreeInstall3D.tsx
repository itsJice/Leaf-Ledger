import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { ConePoint, TreeInstallLayout } from "utils/treeInstallLayout";
import { ENHANCER_WIDTH_IN } from "utils/treeInstallLayout";

// The Tree Install mockup: the tree, every ornament at its true size hanging
// straight down, every enhancer as an ~11" bow hanging diagonally down its swirl
// line, and the spray-and-bow topper, all set into the branches and all in inches
// (scene units are inches). Ported from the training
// prototype (tree-design-map/oneway/3d-body.html).

export type TreeView = "front" | "side" | "back" | "top";

export interface TreeInstall3DProps {
  layout: TreeInstallLayout;
  /** Ornament colors, by color number (index 0 = color 1). */
  colors: string[];
  ribbonA: string;
  ribbonB: string;
  topper: string;
  showLabels: boolean;
  showLines: boolean;
  /** Rows shown, top down; `layout.rows` shows them all, 0 = topper only. */
  rowsShown: number;
  spin: boolean;
  onSpinChange: (spin: boolean) => void;
  /** Change `nonce` to jump to a view again. */
  view: { name: TreeView; nonce: number } | null;
}

interface SceneState {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  tree: THREE.Group;
  mats: Record<string, THREE.MeshStandardMaterial>;
  rowItems: { row: number; obj: THREE.Object3D }[];
  labels: THREE.Sprite[];
  lines: THREE.Object3D[];
  topper: THREE.Group | null;
  height: number;
  dispose: () => void;
}

const sphereGeo = new THREE.SphereGeometry(1, 28, 20);
const leafGeo = new THREE.SphereGeometry(1, 12, 8);
const capGeo = new THREE.CylinderGeometry(1, 1, 1, 12);
const loopGeo = new THREE.TorusGeometry(1, 0.28, 10, 24);
const boxGeo = new THREE.BoxGeometry(1, 1, 1);

/** Where a cone point sits in the scene, and which way is "out" from the tree there. */
function surface(p: ConePoint, H: number, R: number) {
  const r = p.t * R;
  const y = H * (1 - p.t);
  const alpha = Math.atan2(R, H); // the cone's half-angle: the surface tilts up by this much
  const out = new THREE.Vector3(Math.sin(p.ang), 0, Math.cos(p.ang));
  const normal = out.clone().multiplyScalar(Math.cos(alpha)).add(new THREE.Vector3(0, Math.sin(alpha), 0)).normalize();
  return { pos: new THREE.Vector3(out.x * r, y, out.z * r), normal };
}

function labelSprite(text: string): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d");
  if (x) {
    x.fillStyle = "rgba(255,255,255,0.94)";
    x.beginPath();
    x.arc(64, 64, 48, 0, Math.PI * 2);
    x.fill();
    x.strokeStyle = "rgba(23,36,28,0.35)";
    x.lineWidth = 4;
    x.stroke();
    x.fillStyle = "#17241c";
    x.font = '800 66px "Nunito Sans", Arial, sans-serif';
    x.textAlign = "center";
    x.textBaseline = "middle";
    x.fillText(text, 64, 69);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: true }));
  s.scale.set(3.4, 3.4, 1);
  return s;
}

function mesh(geo: THREE.BufferGeometry, mat: THREE.Material): THREE.Mesh {
  return new THREE.Mesh(geo, mat);
}

/**
 * An ~11" round enhancer bow: ribbon loops around a center ball, tails and a pick
 * of leaves, hanging diagonally down its swirl line. Built in a local frame: x
 * across, y up the line (tails hang toward -y), z out of the tree.
 */
function buildBow(
  center: THREE.Vector3,
  normal: THREE.Vector3,
  down: THREE.Vector3,
  size: number,
  ribbon: THREE.Material,
  trim: THREE.Material,
  leaf: THREE.Material,
  ball: THREE.Material,
  inside: { size: number; mat: THREE.Material }[]
): THREE.Group {
  const g = new THREE.Group();
  // up the line, perpendicular to the surface's normal
  const up = down.clone().negate().addScaledVector(normal, down.dot(normal)).normalize();
  const across = new THREE.Vector3().crossVectors(up, normal).normalize();
  g.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(across, up, normal));
  g.position.copy(center);
  const add = (geo: THREE.BufferGeometry, mat: THREE.Material, pos: [number, number, number], scale: [number, number, number], rotZ = 0) => {
    const m = mesh(geo, mat);
    m.position.set(...pos);
    m.scale.set(...scale);
    m.rotation.z = rotZ;
    g.add(m);
    return m;
  };
  // the pick of leaves fanning out behind, up the line
  for (let k = 0; k < 7; k++) {
    const a = (k - 3) * 0.42;
    add(leafGeo, leaf, [Math.sin(a) * 3.2, Math.cos(a) * 3.2 + 0.4, -0.6], [0.9, 2.6, 0.25], -a);
  }
  // tails hanging down the line
  for (const sgn of [-1, 1]) {
    add(boxGeo, ribbon, [sgn * 1.3, -3.6, 0.6], [1.7, 5.6, 0.18], sgn * 0.3);
    add(boxGeo, trim, [sgn * 0.6, -3.2, 0.8], [0.7, 4.6, 0.18], sgn * 0.15);
  }
  // four loops around the knot, a trim loop inside each
  for (const [x, y, rot] of [
    [-2.4, 1, 0.35],
    [2.4, 1, -0.35],
    [-2.2, -1, -0.3],
    [2.2, -1, 0.3],
  ] as const) {
    add(loopGeo, ribbon, [x, y, 1.4], [2.4, 1.4, 0.9], rot);
    add(loopGeo, trim, [x * 0.9, y * 0.9, 1.8], [1.4, 0.75, 0.6], rot);
  }
  add(sphereGeo, ball, [0, 0, 2.4], [1.5, 1.5, 1.5]);
  // the small ornaments tucked into the bow
  const spots = [
    [-1.9, 2.1],
    [1.9, -2],
    [1.9, 2.1],
    [-1.9, -2],
    [0, 3],
    [0, -3],
  ];
  inside.forEach((p, i) => {
    const [x, y] = spots[i % spots.length];
    add(sphereGeo, p.mat, [x, y, p.size / 2], [p.size / 2, p.size / 2, p.size / 2]);
  });
  g.scale.setScalar(size / 11);
  return g;
}

function buildTopper(mats: SceneState["mats"], H: number, size: number): THREE.Group {
  const g = new THREE.Group();
  const scale = size / 12; // the model is drawn for a 12" topper
  for (let k = 0; k < 11; k++) {
    const a = (k - 5) * 0.24;
    const len = k === 5 ? 9 : 7 - Math.abs(k - 5) * 0.5;
    const l = mesh(leafGeo, mats.T);
    l.scale.set(1.1, len, 0.4);
    l.position.set(Math.sin(a) * len * 0.9, Math.cos(a) * len * 0.9 - 1, (k % 2) * 0.6 - 0.3);
    l.rotation.z = -a;
    g.add(l);
  }
  for (const s of [-1, 1]) {
    for (const tilt of [0.35, -0.35]) {
      const loop = mesh(loopGeo, mats.A);
      loop.scale.set(3, 1.7, 1.2);
      loop.position.set(s * 3, tilt * 3, 1.5);
      loop.rotation.z = s * tilt;
      g.add(loop);
    }
    const tail = mesh(boxGeo, mats.A);
    tail.scale.set(1.4, 7, 0.2);
    tail.position.set(s * 1.6, -4.5, 1.4);
    tail.rotation.z = s * 0.3;
    g.add(tail);
  }
  const ball = mesh(sphereGeo, mats.T);
  ball.scale.setScalar(1.8);
  ball.position.set(0, 0, 2.6);
  g.add(ball);
  g.scale.setScalar(scale);
  g.position.set(0, H - size * 0.15, 0);
  return g;
}

export default function TreeInstall3D(props: TreeInstall3DProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<SceneState | null>(null);
  const onSpinRef = useRef(props.onSpinChange);
  onSpinRef.current = props.onSpinChange;
  const propsRef = useRef(props);
  propsRef.current = props;

  // 1. the renderer, camera, lights and controls: once
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch {
      return; // no WebGL: the page shows its counts without the mockup
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x334433, 1.25));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(200, 400, 300);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xfff1d6, 1.0);
    rim.position.set(-300, 150, -200);
    scene.add(rim);
    const std = (o: THREE.MeshStandardMaterialParameters) => new THREE.MeshStandardMaterial(o);
    const mats: SceneState["mats"] = {
      A: std({ roughness: 0.45, metalness: 0.25 }),
      B: std({ roughness: 0.45, metalness: 0.25 }),
      T: std({ roughness: 0.25, metalness: 0.75 }),
      leaf: std({ color: 0xc9b06a, metalness: 0.6, roughness: 0.4 }),
      cream: std({ color: 0xf1e9d6, metalness: 0.3, roughness: 0.3 }),
      cap: std({ color: 0xc9a227, metalness: 0.9, roughness: 0.3 }),
      tree: std({ color: 0x2e6b45, roughness: 0.9, flatShading: true }),
      trunk: std({ color: 0x6b4a32, roughness: 1 }),
      floor: std({ color: 0x9aa79c, roughness: 1, transparent: true, opacity: 0.35 }),
    };
    for (let i = 1; i <= 4; i++) mats[`c${i}`] = std({ roughness: 0.25, metalness: 0.35 });
    const tree = new THREE.Group();
    scene.add(tree);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    controls.autoRotate = !reduce;
    controls.autoRotateSpeed = 1.4;
    const stop = () => {
      if (controls.autoRotate) {
        controls.autoRotate = false;
        onSpinRef.current(false);
      }
    };
    canvas.addEventListener("pointerdown", stop);
    canvas.addEventListener("wheel", stop, { passive: true });
    const resize = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    resize();
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
    });
    const state: SceneState = {
      renderer,
      scene,
      camera,
      controls,
      tree,
      mats,
      rowItems: [],
      labels: [],
      lines: [],
      topper: null,
      height: 0,
      dispose: () => {
        renderer.setAnimationLoop(null);
        ro.disconnect();
        canvas.removeEventListener("pointerdown", stop);
        canvas.removeEventListener("wheel", stop);
        controls.dispose();
        clearTree(state);
        Object.values(mats).forEach((m) => m.dispose());
        renderer.dispose();
      },
    };
    stateRef.current = state;
    if (reduce) onSpinRef.current(false);
    return () => {
      state.dispose();
      stateRef.current = null;
    };
  }, []);

  // 2. the tree itself: rebuilt when the layout changes
  const { layout } = props;
  useEffect(() => {
    const st = stateRef.current;
    if (!st) return;
    clearTree(st);
    const H = layout.heightIn;
    const R = layout.baseRadiusIn;
    const { mats, tree } = st;
    st.height = H;

    const coneGeo = new THREE.ConeGeometry(R * 0.97, H, 96, 16);
    // a little unevenness so it reads as branches, not a smooth cone
    const pos = coneGeo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const wobble = 1 + 0.035 * Math.sin(i * 12.9898) * Math.sin(i * 78.233);
      pos.setX(i, x * wobble);
      pos.setZ(i, z * wobble);
    }
    coneGeo.computeVertexNormals();
    const cone = new THREE.Mesh(coneGeo, mats.tree);
    cone.position.y = H / 2;
    tree.add(cone);
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 4.5, 10, 16), mats.trunk);
    trunk.position.y = -5;
    tree.add(trunk);
    const floor = new THREE.Mesh(new THREE.CylinderGeometry(R * 1.25, R * 1.25, 0.6, 64), mats.floor);
    floor.position.y = -10;
    tree.add(floor);

    const addRow = (row: number, obj: THREE.Object3D) => {
      tree.add(obj);
      st.rowItems.push({ row, obj });
    };
    for (const o of layout.ornaments) {
      const { pos: p, normal } = surface(o, H, R);
      const r = o.size / 2;
      const holder = new THREE.Group();
      const ball = mesh(sphereGeo, mats[`c${o.color}`] ?? mats.c1);
      ball.scale.setScalar(r);
      // nestled into the branches: a little more than half the ball shows\n      ball.position.copy(p).addScaledVector(normal, r * 0.2);
      holder.add(ball);
      const cap = mesh(capGeo, mats.cap);
      cap.scale.set(r * 0.22, r * 0.25, r * 0.22);
      cap.position.copy(ball.position).add(new THREE.Vector3(0, r * 1.02, 0));
      holder.add(cap);
      const label = labelSprite(String(o.color));
      label.position.copy(ball.position).addScaledVector(normal, r + 1.2);
      holder.add(label);
      st.labels.push(label);
      addRow(o.row, holder);
    }
    const bowSize = ENHANCER_WIDTH_IN;
    for (const e of layout.enhancers) {
      const mid = surface(e, H, R);
      const low = surface(e.downhill, H, R);
      let down = low.pos.clone().sub(mid.pos);
      // the last bow on a line: hang it straight down the slant instead
      if (down.lengthSq() < 1e-6) down = new THREE.Vector3(0, -1, 0);
      down.normalize();
      const ribbon = e.letter === "A" ? mats.A : mats.B;
      const trim = e.letter === "A" ? mats.B : mats.A;
      const inside = e.inside.map((size, i) => ({ size, mat: mats[`c${(i % 4) + 1}`] }));
      const holder = new THREE.Group();
      // set into the branches: the knot sits just proud of the surface
      const center = mid.pos.clone().addScaledVector(mid.normal, 0.3);
      holder.add(buildBow(center, mid.normal, down, bowSize, ribbon, trim, mats.leaf, mats.cream, inside));
      const label = labelSprite(e.letter);
      label.position.copy(mid.pos).addScaledVector(mid.normal, 5.5);
      holder.add(label);
      st.labels.push(label);
      addRow(e.row, holder);
    }
    // the six swirl lines, dashed, just off the surface
    const lineMat = new THREE.LineDashedMaterial({ color: 0x7a3fb0, dashSize: 2.2, gapSize: 1.6 });
    for (const ln of layout.lines) {
      const ptsL = ln.map((p) => {
        const s = surface(p, H, R);
        return s.pos.addScaledVector(s.normal, 0.5);
      });
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ptsL), lineMat);
      line.computeLineDistances();
      tree.add(line);
      st.lines.push(line);
    }
    st.topper = buildTopper(mats, H, Math.max(10, layout.topperIn * 1.1));
    tree.add(st.topper);

    st.controls.target.set(0, H * 0.48, 0);
    st.controls.minDistance = H * 0.5;
    st.controls.maxDistance = H * 5;
    setView(st, "front");
    applyVisibility(st, propsRef.current);
    applyColors(st, propsRef.current);
  }, [layout]);

  // 3. colors, labels, lines and rows: no rebuild
  const { colors, ribbonA, ribbonB, topper, showLabels, showLines, rowsShown, spin, view } = props;
  useEffect(() => {
    const st = stateRef.current;
    if (st) applyColors(st, { colors, ribbonA, ribbonB, topper });
  }, [colors, ribbonA, ribbonB, topper]);
  useEffect(() => {
    const st = stateRef.current;
    if (st) applyVisibility(st, { showLabels, showLines, rowsShown });
  }, [showLabels, showLines, rowsShown, layout]);
  useEffect(() => {
    const st = stateRef.current;
    if (st) st.controls.autoRotate = spin;
  }, [spin]);
  useEffect(() => {
    const st = stateRef.current;
    if (st && view) setView(st, view.name);
  }, [view]);

  return (
    <canvas
      ref={canvasRef}
      className="block h-full w-full touch-none"
      aria-label="3D tree mockup. Drag to turn it, pinch or scroll to zoom."
      role="img"
    />
  );
}

function clearTree(st: SceneState) {
  const disposeObj = (o: THREE.Object3D) => {
    o.traverse((c) => {
      if (c instanceof THREE.Sprite) {
        c.material.map?.dispose();
        c.material.dispose();
      }
      if (c instanceof THREE.Line) {
        c.geometry.dispose();
        (c.material as THREE.Material).dispose();
      }
    });
  };
  [...st.tree.children].forEach((c) => {
    disposeObj(c);
    // the cone, trunk and floor have their own geometry; the pieces share theirs
    if (c instanceof THREE.Mesh && ![sphereGeo, leafGeo, capGeo, loopGeo, boxGeo].includes(c.geometry)) c.geometry.dispose();
    st.tree.remove(c);
  });
  st.rowItems = [];
  st.labels = [];
  st.lines = [];
  st.topper = null;
}

function applyColors(
  st: SceneState,
  p: Pick<TreeInstall3DProps, "colors" | "ribbonA" | "ribbonB" | "topper">
) {
  p.colors.forEach((c, i) => st.mats[`c${i + 1}`]?.color.set(c));
  st.mats.A.color.set(p.ribbonA);
  st.mats.B.color.set(p.ribbonB);
  st.mats.T.color.set(p.topper);
}

function applyVisibility(
  st: SceneState,
  p: Pick<TreeInstall3DProps, "showLabels" | "showLines" | "rowsShown">
) {
  st.rowItems.forEach(({ row, obj }) => (obj.visible = row < p.rowsShown));
  st.labels.forEach((l) => (l.visible = p.showLabels));
  st.lines.forEach((l) => (l.visible = p.showLines));
}

function setView(st: SceneState, name: TreeView) {
  const H = st.height || 108;
  const d = H * 2.2;
  const y = H * 0.6;
  const { camera, controls } = st;
  if (name === "top") camera.position.set(0.01, H * 2.6, H * 0.35);
  else {
    const theta = name === "front" ? 0 : name === "side" ? Math.PI / 2 : Math.PI;
    camera.position.set(Math.sin(theta) * d, y, Math.cos(theta) * d);
  }
  controls.update();
}
