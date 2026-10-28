import { useEffect, useRef, useState } from "react";
import { buildTreeInstallLayout, type TreeInstallLayout, type TreeInstallLayoutInput } from "utils/treeInstallLayout";

// Shared by the Tree Install page and its print sheets.
/** Lays the tree out in a worker so typing a height never freezes the page. */
export function useTreeLayout(input: TreeInstallLayoutInput | null) {
  const [layout, setLayout] = useState<TreeInstallLayout | null>(null);
  const [busy, setBusy] = useState(false);
  const workerRef = useRef<Worker | null>(null);
  const idRef = useRef(0);
  const key = input ? JSON.stringify(input) : "";

  useEffect(() => {
    return () => workerRef.current?.terminate();
  }, []);

  useEffect(() => {
    if (!input) {
      setLayout(null);
      setBusy(false);
      return;
    }
    const id = ++idRef.current;
    setBusy(true);
    const timer = window.setTimeout(() => {
      const done = (next: TreeInstallLayout) => {
        if (id !== idRef.current) return;
        setLayout(next);
        setBusy(false);
      };
      if (typeof Worker === "undefined") {
        done(buildTreeInstallLayout(input));
        return;
      }
      try {
        if (!workerRef.current) {
          workerRef.current = new Worker(new URL("../utils/treeInstall.worker.ts", import.meta.url), { type: "module" });
        }
        const worker = workerRef.current;
        worker.onmessage = (event: MessageEvent<{ id: number; layout?: TreeInstallLayout; error?: string }>) => {
          if (event.data.layout) {
            if (event.data.id === idRef.current) done(event.data.layout);
          } else if (event.data.id === idRef.current) {
            setBusy(false);
          }
        };
        worker.postMessage({ id, input });
      } catch {
        done(buildTreeInstallLayout(input));
      }
    }, 250);
    return () => window.clearTimeout(timer);
    // `key` is the input, by value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { layout, busy };
}
