import React, { useState } from "react";
import { Plus, Check } from "lucide-react";
import { toast } from "sonner";
import { pinProduct, unpinProduct, type PinGroup } from "utils/jobs";

// The + button that pins a catalog product to a job (Pinterest-style),
// reused on Catalog Search cards (grid + list) and on the product detail
// modal's header. Handles its own click logic:
//   - no job picked            -> toast pointing at the job picker
//   - already pinned           -> unpin, no confirmation needed
//   - a group is preselected,
//     or the job has no groups -> pin straight there
//   - job has groups but none
//     is preselected           -> quick popover asking which group

interface Props {
  productId: number;
  jobId: number | null;
  groupId: number | null;
  groups: PinGroup[];
  isPinned: boolean;
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

export default function PinToggle({ productId, jobId, groupId, groups, isPinned, onPinsChanged, className, iconSize = 14 }: Props) {
  const [choosing, setChoosing] = useState(false);

  const doPin = async (gid: number | null) => {
    if (!jobId) return;
    try {
      const r = await pinProduct(jobId, { product_id: productId, group_id: gid ?? undefined });
      onPinsChanged(r.pins);
      toast.success(gid ? `Pinned to ${groups.find((g) => g.id === gid)?.name || "group"}` : "Pinned");
    } catch (e: any) {
      toast.error(e?.message || "Could not pin that");
    }
  };

  const doUnpin = async () => {
    if (!jobId) return;
    try {
      const r = await unpinProduct(jobId, productId);
      onPinsChanged(r.pins);
      toast.success("Unpinned");
    } catch (e: any) {
      toast.error(e?.message || "Could not unpin that");
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!jobId) {
      toast.message("Pick a job first", { description: "Use “Pinning to” at the top, then hit + again." });
      return;
    }
    if (isPinned) { doUnpin(); return; }
    if (groupId != null || groups.length === 0) { doPin(groupId); return; }
    setChoosing(true);
  };

  // The root box is positioned exactly as the caller asked (its own
  // `absolute`/`relative`/etc, if any) — any position other than static
  // already anchors a descendant, so the popover below needs nothing added
  // when the caller supplied one. When the caller left it static (a plain
  // flex sizing box for list/modal use), add `relative` so the popover still
  // has something to anchor to, without touching a position the caller set.
  const rootClass = `${className} ${POSITIONED.test(className) ? "" : "relative"}`;

  // A real <button> can't contain the popover's own buttons (nested
  // interactive content is invalid HTML and browsers mishandle its clicks),
  // so the root is a div playing the button role; it still needs the same
  // keyboard affordance a button gets for free.
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(e as unknown as React.MouseEvent); }}
      className={`${rootClass} cursor-pointer`}
      title={isPinned ? "Remove from this job" : jobId ? "Pin to this job" : "Pick a job to pin to"}
    >
      {isPinned ? <Check size={iconSize} className="text-white" /> : <Plus size={iconSize} style={{ color: jobId ? "rgb(var(--ll-brand))" : "rgb(var(--nc-400))" }} />}
      {choosing && (
        <div
          className="absolute right-0 top-full z-30 mt-1 w-48 cursor-default rounded-lg border border-stone-200 bg-white p-1 text-left normal-case shadow-lg"
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
