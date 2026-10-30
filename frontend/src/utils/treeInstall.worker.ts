// Lays out the Tree Install mockup off the main thread: a full tree takes about a
// second, and the page should stay responsive while someone drags the height.
import { buildTreeInstallLayout, type TreeInstallLayoutInput } from "./treeInstallLayout";

self.onmessage = (event: MessageEvent<{ id: number; input: TreeInstallLayoutInput }>) => {
  const { id, input } = event.data;
  try {
    const layout = buildTreeInstallLayout(input);
    (self as unknown as Worker).postMessage({ id, layout });
  } catch (err) {
    (self as unknown as Worker).postMessage({ id, error: err instanceof Error ? err.message : String(err) });
  }
};
