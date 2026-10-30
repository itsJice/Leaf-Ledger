import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { TreeInstallLayout } from "utils/treeInstallLayout";

// The Tree Install mockup, ported from the designer-approved 3D tree
// (tree-design-map/oneway/3d-body.html): every ornament at its true size, sunk into
// the branches and hanging straight down; every enhancer an 11" ribbon bow nestled
// in, hanging diagonally down its swirl line; a tall spray-and-bow topper. Like the
// prototype, the tree is drawn 3 units tall and every size is scaled to it.

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

/** The tree's height in scene units (3d-body.html). */
const H = 3;

interface SceneState {
  renderer: THREE.WebGLRenderer;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  tree: THREE.Group;
  topper: THREE.Group;
  mats: Record<string, THREE.MeshStandardMaterial>;
  rowItems: { row: number; obj: THREE.Object3D }[];
  labels: THREE.Sprite[];
  lines: THREE.Object3D[];
  disposables: { dispose: () => void }[];
}

function labelSprite(text: string): THREE.Sprite {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d");
  if (x) {
    x.fillStyle = "rgba(255,255,255,0.92)";
    x.beginPath();
    x.arc(64, 64, 46, 0, Math.PI * 2);
    x.fill();
    x.fillStyle = "#17241c";
    x.font = '800 64px "Nunito Sans", Arial, sans-serif';
    x.textAlign = "center";
    x.textBaseline = "middle";
    x.fillText(text, 64, 68);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthTest: true }));
  s.scale.set(0.15, 0.15, 1);
  return s;
}

export default function TreeInstall3D(props: TreeInstall3DProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<SceneState | null>(null);
  const onSpinRef = useRef(props.onSpinChange);
  onSpinRef.current = props.onSpinChange;
  const propsRef = useRef(props);
  propsRef.current = props;

  // 1. renderer, camera, lights, controls and the topper: once
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
    } catch {
      return; // no WebGL: the page still shows its counts
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    const controls = new OrbitControls(camera, canvas);
    controls.target.set(0, H * 0.48, 0);
    controls.enableDamping = true;
    controls.minDistance = 2.5;
    controls.maxDistance = 14;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    controls.autoRotate = !reduce;
    controls.autoRotateSpeed = 1.4;
    camera.position.set(0, H * 0.6, 6.6);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x334433, 1.2));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(4, 7, 6);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xfff1d6, 1.0);
    rim.position.set(-5, 3, -4);
    scene.add(rim);

    const std = (o: THREE.MeshStandardMaterialParameters) => new THREE.MeshStandardMaterial(o);
    const mats: SceneState["mats"] = {
      c1: std({ roughness: 0.25, metalness: 0.35 }),
      c2: std({ roughness: 0.25, metalness: 0.35 }),
      c3: std({ roughness: 0.25, metalness: 0.35 }),
      c4: std({ roughness: 0.25, metalness: 0.35 }),
      A: std({ roughness: 0.35, metalness: 0.6 }),
      B: std({ roughness: 0.5, metalness: 0.1 }),
      T: std({ roughness: 0.2, metalness: 0.8, emissive: 0x7a5a10 }),
      leaf: std({ color: 0xc9b06a, metalness: 0.6, roughness: 0.4 }),
      cream: std({ color: 0xf1e9d6, metalness: 0.3, roughness: 0.3 }),
      cap: std({ color: 0xc9a227, metalness: 0.9, roughness: 0.3 }),
      tree: std({ color: 0x2e6b45, roughness: 0.9, flatShading: true }),
      trunk: std({ color: 0x6b4a32, roughness: 1 }),
      floor: std({ color: 0x9aa79c, roughness: 1, transparent: true, opacity: 0.35 }),
    };

    // topper: a tall spray of leaves with a bow, like the finished trees
    const leafGeo = new THREE.SphereGeometry(0.1, 10, 8);
    const topLoopGeo = new THREE.TorusGeometry(0.09, 0.03, 10, 22);
    const topBallGeo = new THREE.SphereGeometry(0.045, 14, 12);
    const topper = new THREE.Group();
    for (let k = 0; k < 9; k++) {
      const leaf = new THREE.Mesh(leafGeo, mats.T);
      const a = (k - 4) * 0.28;
      const len = k === 4 ? 1.6 : 1.15 - Math.abs(k - 4) * 0.08;
      leaf.scale.set(0.28, len, 0.12);
      leaf.position.set(Math.sin(a) * 0.12 * len, Math.cos(a) * 0.12 * len, (k % 2) * 0.03);
      leaf.rotation.z = -a;
      topper.add(leaf);
    }
    for (const s of [-1, 1]) {
      const loop = new THREE.Mesh(topLoopGeo, mats.A);
      loop.position.set(s * 0.09, -0.02, 0.05);
      loop.scale.set(1, 0.6, 0.45);
      topper.add(loop);
    }
    const tb = new THREE.Mesh(topBallGeo, mats.cream);
    tb.position.set(0, -0.02, 0.08);
    topper.add(tb);
    topper.position.set(0, H + 0.02, 0);
    scene.add(topper);

    const tree = new THREE.Group();
    scene.add(tree);

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
      if (controls.autoRotate) topper.rotation.y += 0.01;
      renderer.render(scene, camera);
    });
    const state: SceneState = {
      renderer,
      camera,
      controls,
      tree,
      topper,
      mats,
      rowItems: [],
      labels: [],
      lines: [],
      disposables: [],
    };
    stateRef.current = state;
    if (reduce) onSpinRef.current(false);
    return () => {
      renderer.setAnimationLoop(null);
      ro.disconnect();
      canvas.removeEventListener("pointerdown", stop);
      canvas.removeEventListener("wheel", stop);
      controls.dispose();
      clearTree(state);
      [leafGeo, topLoopGeo, topBallGeo].forEach((g) => g.dispose());
      Object.values(mats).forEach((m) => m.dispose());
      renderer.dispose();
      stateRef.current = null;
    };
  }, []);

  // 2. the tree and every piece: rebuilt when the layout changes
  const { layout } = props;
  useEffect(() => {
    const st = stateRef.current;
    if (!st) return;
    clearTree(st);
    const { mats, tree } = st;
    const R = layout.R * H;
    const track = <T extends { dispose: () => void }>(x: T) => {
      st.disposables.push(x);
      return x;
    };

    const cone = new THREE.Mesh(track(new THREE.ConeGeometry(R * 0.97, H, 72, 12)), mats.tree);
    cone.position.y = H / 2;
    tree.add(cone);
    const trunk = new THREE.Mesh(track(new THREE.CylinderGeometry(0.13, 0.16, 0.35, 16)), mats.trunk);
    trunk.position.y = -0.17;
    tree.add(trunk);
    const base = new THREE.Mesh(track(new THREE.CylinderGeometry(R * 1.25, R * 1.25, 0.02, 64)), mats.floor);
    base.position.y = -0.35;
    tree.add(base);

    // shared shapes for the bows (3d-body.html's sizes; each bow is scaled to 11")
    const loopGeo = track(new THREE.TorusGeometry(0.1, 0.032, 10, 22));
    const innerGeo = track(new THREE.TorusGeometry(0.065, 0.012, 8, 20));
    const tailGeo = track(new THREE.BoxGeometry(0.05, 0.26, 0.012));
    const tail2Geo = track(new THREE.BoxGeometry(0.022, 0.22, 0.012));
    const pickGeo = track(new THREE.SphereGeometry(0.06, 8, 6));
    const knotGeo = track(new THREE.SphereGeometry(0.05, 18, 14));
    const ballGeo = track(new THREE.SphereGeometry(1, 28, 20));
    const capGeo = track(new THREE.CylinderGeometry(1, 1, 1, 12));

    const sink = layout.sink ?? 0.5;
    for (const it of layout.items) {
      const r = it.t * R;
      const y = H * (1 - it.t);
      const surf = r * 0.97; // the cone mesh is 0.97 R
      const out = new THREE.Vector3(Math.sin(it.ang), 0, Math.cos(it.ang)); // angle 0 faces the front
      const g = new THREE.Group();
      let lift: number;
      if (it.kind === "orn") {
        const rad = (it.gap * H) / 2; // true size
        const ball = new THREE.Mesh(ballGeo, mats[`c${it.color}`] ?? mats.c1);
        ball.scale.setScalar(rad);
        g.add(ball);
        // hanging straight down: the cap on top
        const cap = new THREE.Mesh(capGeo, mats.cap);
        cap.scale.set(rad * 0.22, rad * 0.25, rad * 0.22);
        cap.position.y = rad * 1.02;
        g.add(cap);
        // IN the tree, not on it: sunk into the branches
        const cR = surf + rad * (1 - 2 * sink);
        g.position.copy(out.clone().multiplyScalar(cR)).setY(y);
        lift = cR - r + rad + 0.03;
      } else {
        // a whole cluster: a layered ribbon bow with tails, a ball nested in the middle
        // and a pick of leaves behind it
        const rib = it.letter === "A" ? mats.A : mats.B;
        const trim = it.letter === "A" ? mats.B : mats.A;
        for (const s of [-1, 1]) {
          const loop = new THREE.Mesh(loopGeo, rib);
          loop.position.set(s * 0.1, 0.02, 0);
          loop.scale.set(1, 0.62, 0.45);
          loop.rotation.z = s * -0.25;
          g.add(loop);
          const inner = new THREE.Mesh(innerGeo, trim);
          inner.position.set(s * 0.085, 0.02, 0.02);
          inner.scale.set(1, 0.55, 0.4);
          inner.rotation.z = s * -0.25;
          g.add(inner);
          const tail = new THREE.Mesh(tailGeo, rib);
          tail.position.set(s * 0.06, -0.15, 0.01);
          tail.rotation.z = s * 0.28;
          g.add(tail);
          const tail2 = new THREE.Mesh(tail2Geo, trim);
          tail2.position.set(s * 0.035, -0.13, 0.02);
          tail2.rotation.z = s * 0.18;
          g.add(tail2);
        }
        for (const a of [-2.4, -0.7, -1.57]) {
          const leaf = new THREE.Mesh(pickGeo, mats.leaf);
          leaf.scale.set(1.6, 0.35, 0.2);
          leaf.position.set(Math.cos(a) * -0.12, -Math.sin(a) * 0.1 + 0.04, -0.03);
          leaf.rotation.z = a;
          g.add(leaf);
        }
        const knot = new THREE.Mesh(knotGeo, mats.cream);
        knot.position.set(0, 0.015, 0.04);
        g.add(knot);
        const es = (it.gap * H) / 2 / 0.2; // the bow model is ~0.4 wide
        g.scale.setScalar(es);
        g.position.copy(out.clone().multiplyScalar(surf - 0.01 * es)).setY(y); // nestled into the branches
        g.lookAt(g.position.clone().add(out));
        g.rotateZ(((it.tilt || 0) * Math.PI) / 180); // hangs diagonally, tails trailing down its swirl line
        lift = surf - r + 0.08 * es;
      }
      const lbl = labelSprite(it.kind === "orn" ? String(it.color) : it.letter);
      lbl.position.copy(out.clone().multiplyScalar(r + lift + 0.04)).setY(y + 0.02);
      const holder = new THREE.Group();
      holder.add(g);
      holder.add(lbl);
      tree.add(holder);
      st.labels.push(lbl);
      st.rowItems.push({ row: it.row, obj: holder });
    }

    // the six swirl lines (dashed), on the cone surface
    const lineMat = track(new THREE.LineDashedMaterial({ color: 0x5a2d82, dashSize: 0.06, gapSize: 0.04 }));
    for (const ln of layout.lines) {
      const pts = ln.pts.map(([tt, an]) => {
        const rr = tt * R + 0.012;
        return new THREE.Vector3(Math.sin(an) * rr, H * (1 - tt), Math.cos(an) * rr);
      });
      const line = new THREE.Line(track(new THREE.BufferGeometry().setFromPoints(pts)), lineMat);
      line.computeLineDistances();
      tree.add(line);
      st.lines.push(line);
    }

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
  st.tree.traverse((c) => {
    if (c instanceof THREE.Sprite) {
      c.material.map?.dispose();
      c.material.dispose();
    }
  });
  [...st.tree.children].forEach((c) => st.tree.remove(c));
  st.disposables.forEach((d) => d.dispose());
  st.disposables = [];
  st.rowItems = [];
  st.labels = [];
  st.lines = [];
}

function applyColors(st: SceneState, p: Pick<TreeInstall3DProps, "colors" | "ribbonA" | "ribbonB" | "topper">) {
  p.colors.forEach((c, i) => st.mats[`c${i + 1}`]?.color.set(c));
  st.mats.A.color.set(p.ribbonA);
  st.mats.B.color.set(p.ribbonB);
  st.mats.T.color.set(p.topper);
}

function applyVisibility(st: SceneState, p: Pick<TreeInstall3DProps, "showLabels" | "showLines" | "rowsShown">) {
  st.rowItems.forEach(({ row, obj }) => (obj.visible = row < p.rowsShown));
  st.labels.forEach((l) => (l.visible = p.showLabels));
  st.lines.forEach((l) => (l.visible = p.showLines));
}

function setView(st: SceneState, name: TreeView) {
  const { camera, controls } = st;
  if (name === "top") camera.position.set(0.01, 9, 0.6);
  else {
    const theta = name === "front" ? 0 : name === "side" ? Math.PI / 2 : Math.PI;
    const d = 6.6;
    camera.position.set(Math.sin(theta) * d, H * 0.62, Math.cos(theta) * d);
  }
  controls.update();
}
