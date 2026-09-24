import React, { useState } from "react";
import { Plus, Check, Loader2 } from "components/icons";
import { toast } from "sonner";
import { pinProduct, unpinProduct, type PinGroup } from "utils/jobs";
import { decidePinAction } from "utils/pinsCache";

// The + button that pins a catalog product to a job (Pinterest-style),
// reused on Catalog Search cards (grid + list) and on the product detail
// modal's header.
//
// `ready` must stay false until the caller's pins/groups for this job have
// actually loaded once. A click before that used to fall through to "this
// job has zero groups" (the empty default state), so a fast click after
// opening a card could silently pin with no group instead of asking — the
// popup didn't "always" appear because it depended on how fast the fetch
// happened to be, not on whether the job really had groups. decidePinAction
// makes that case its own outcome ("wait") instead of guessing.

interface Props {
  productId: number;
  jobId: number | null;
  groupId: number | null;
  groups: PinGroup[];
  isPinned: boolean;
  ready: boolean;
  onPinsChanged: (pins: Array<{ product_id: number; group_id: number | null }>) => void;
  // Sizes and positions the button. A grid card passes its own `absolute
  // right-2 top-10 ...` here to sit over the image; list rows and the modal
  // pass a plain `flex h-7 w-7 ...` to sit inline. Either way `className`
  // goes on THIS component's own root box, never on a wrapper around it —
  // an extra wrapper with no size of its own would swallow an `absolute`
  // class from the caller (it has nothing to be absolute *within*, so it
  // collapses to nothing and the button vanishes with it).
  className: string;
  iconSize?: number;
}

const POSITIONED = /\b(?:absolute|relative|fixed|sticky)\b/;

export default function PinToggle({ productId, jobId, groupId, groups, isPinned, ready, onPinsChanged, className, iconSize = 14 }: Props) {
  const [choosing, setChoosing] = useState(false);
  const [busy, setBusy] = useState(false);

  const doPin = async (gid: number | null) => {
    if (!jobId) return;
    setBusy(true);
    try {
      const r = await pinProduct(jobId, { product_id: productId, group_id: gid ?? undefined });
      onPinsChanged(r.pins);
      toast.success(gid ? `Pinned to ${groups.find((g) => g.id === gid)?.name || "group"}` : "Pinned");
    } catch (e: any) {
      toast.error(e?.message || "Could not pin that");
    } finally {
      setBusy(false);
    }
  };

  const doUnpin = async () => {
    if (!jobId) return;
    setBusy(true);
    try {
      const r = await unpinProduct(jobId, productId);
      onPinsChanged(r.pins);
      toast.success("Unpinned");
    } catch (e: any) {
      toast.error(e?.message || "Could not unpin that");
    } finally {
      setBusy(false);
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (busy) return;
    const decision = decidePinAction({ jobId, ready, groupId, groups, isPinned });
    switch (decision.action) {
      case "need-job":
        toast.message("Pick a job first", { description: "Use “Pinning to” at the top, then hit + again." });
        return;
      case "wait":
        // Data for this job hasn't loaded yet (should be rare — the button
        // is dimmed and effectively disabled through this window). Nothing
        // to do but not guess.
        return;
      case "unpin":
        doUnpin();
        return;
      case "pin":
        doPin(decision.groupId);
        return;
      case "choose":
        setChoosing(true);
        return;
    }
  };

  // The root box is positioned exactly as the caller asked (its own
  // `absolute`/`relative`/etc, if any) — any position other than static
  // already anchors a descendant, so the popover below needs nothing added
  // when the caller supplied one. When the caller left it static (a plain
  // flex sizing box for list/modal use), add `relative` so the popover still
  // has something to anchor to, without touching a position the caller set.
  const rootClass = `${className} ${POSITIONED.test(className) ? "" : "relative"} ${!ready ? "opacity-50" : ""}`;

  const title = !jobId ? "Pick a job to pin to" : !ready ? "Loading…" : isPinned ? "Remove from this job" : "Pin to this job";

  // A real <button> can't contain the popover's own buttons (nested
  // interactive content is invalid HTML and browsers mishandle its clicks),
  // so the root is a div playing the button role; it still needs the same
  // keyboard affordance a button gets for free.
  return (
    <div
      role="button"
      aria-disabled={!ready || busy}
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(e as unknown as React.MouseEvent); }}
      className={`${rootClass} cursor-pointer`}
      title={title}
    >
      {busy || (!ready && jobId)
        ? <Loader2 size={iconSize} className="animate-spin" style={{ color: "rgb(var(--nc-400))" }} />
        : isPinned
        ? <Check size={iconSize} className="text-white" />
        : <Plus size={iconSize} style={{ color: jobId ? "rgb(var(--ll-brand))" : "rgb(var(--nc-400))" }} />}
      {choosing && (
        <div
          className="ll-popover origin-top-right absolute right-0 top-full z-30 mt-1 w-48 cursor-default rounded-lg border border-stone-200 bg-white p-1 text-left normal-case shadow-lg"
          onClick={(e) => e.stopPropagation()}
          onMouseLeave={() => setChoosing(false)}
        >
          <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">Pin to which group?</p>
          <button type="button" onClick={() => { doPin(null); setChoosing(false); }} className="block w-full rounded px-2 py-1.5 text-left text-sm font-normal text-stone-600 hover:bg-stone-50">No group</button>
          {groups.map((g) => (
            <button key={g.id} type="button" onClick={() => { doPin(g.id); setChoosing(false); }} className="block w-full rounded px-2 py-1.5 text-left text-sm font-normal text-stone-700 hover:bg-emerald-50 hover:text-emerald-800">{g.name}</button>
          ))}
        </div>
      )}
    </div>
  );
}
