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
  className: string;
  iconSize?: number;
}

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

  const handleClick = () => {
    if (!jobId) {
      toast.message("Pick a job first", { description: "Use “Pinning to” at the top, then hit + again." });
      return;
    }
    if (isPinned) { doUnpin(); return; }
    if (groupId != null || groups.length === 0) { doPin(groupId); return; }
    setChoosing(true);
  };

  return (
    <div className="relative inline-block" onClick={(e) => e.stopPropagation()}>
      <button onClick={handleClick} className={className} title={isPinned ? "Remove from this job" : jobId ? "Pin to this job" : "Pick a job to pin to"}>
        {isPinned ? <Check size={iconSize} className="text-white" /> : <Plus size={iconSize} style={{ color: jobId ? "rgb(var(--ll-brand))" : "rgb(var(--nc-400))" }} />}
      </button>
      {choosing && (
        <div className="absolute right-0 top-full z-30 mt-1 w-48 rounded-lg border border-stone-200 bg-white p-1 shadow-lg" onMouseLeave={() => setChoosing(false)}>
          <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">Pin to which group?</p>
          <button onClick={() => { doPin(null); setChoosing(false); }} className="block w-full rounded px-2 py-1.5 text-left text-sm text-stone-600 hover:bg-stone-50">No group</button>
          {groups.map((g) => (
            <button key={g.id} onClick={() => { doPin(g.id); setChoosing(false); }} className="block w-full rounded px-2 py-1.5 text-left text-sm text-stone-700 hover:bg-emerald-50 hover:text-emerald-800">{g.name}</button>
          ))}
        </div>
      )}
    </div>
  );
}
