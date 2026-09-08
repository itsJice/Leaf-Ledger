import React, { useCallback, useEffect, useState } from "react";
import { ClipboardList, Plus, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  listBoards, createJob, addGroup, writeWorkingJob,
  type BoardJob, type PinGroup, type WorkingJob,
} from "utils/jobs";
import { loadPins, setCachedPins } from "utils/pinsCache";

// "Pinning to: Hanover · Ornaments". Sits in the Catalog Search header so the
// plus button on every card knows where a pin goes. The choice is remembered
// per browser; the pins themselves are shared on the server.

interface Props {
  value: WorkingJob;
  onChange: (v: WorkingJob) => void;
  pinnedCount: number;
}

const sel = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm text-stone-800 outline-none focus:border-emerald-500";

export default function WorkingJobBar({ value, onChange, pinnedCount }: Props) {
  const [jobs, setJobs] = useState<BoardJob[]>([]);
  const [groups, setGroups] = useState<PinGroup[]>([]);
  const [open, setOpen] = useState(false);

  const refreshJobs = useCallback(async () => {
    try { setJobs(await listBoards()); } catch { setJobs([]); }
  }, []);
  useEffect(() => { refreshJobs(); }, [refreshJobs]);

  useEffect(() => {
    if (!value.jobId) { setGroups([]); return; }
    loadPins(value.jobId).then((p) => setGroups(p.groups)).catch(() => setGroups([]));
  }, [value.jobId]);

  const job = jobs.find((j) => j.id === value.jobId) || null;
  const group = groups.find((g) => g.id === value.groupId) || null;

  const pickJob = (id: number | null) => {
    const v = { jobId: id, groupId: null };
    writeWorkingJob(v);
    onChange(v);
  };
  const pickGroup = (id: number | null) => {
    const v = { jobId: value.jobId, groupId: id };
    writeWorkingJob(v);
    onChange(v);
  };

  const newJob = async () => {
    const name = window.prompt("New job", "Client · project");
    if (!name?.trim()) return;
    try {
      const created = await createJob({ name: name.trim() });
      await refreshJobs();
      pickJob(created.id);
      toast.success(`Pinning to ${created.name}`);
    } catch (e: any) { toast.error(e?.message || "Could not create the job"); }
  };

  const newGroup = async () => {
    if (!value.jobId) return;
    const name = window.prompt("New group on this job", "Ornaments");
    if (!name?.trim()) return;
    try {
      const board = await addGroup(value.jobId, name.trim());
      setGroups(board.groups);
      // Keep the shared cache in step — a card's + button reads groups from
      // here, not from this bar, so a newly made group needs to land in the
      // cache too or the popup elsewhere on the page would still be one
      // group short until something else forces a reload.
      setCachedPins(value.jobId, board.items.map((i) => ({ product_id: i.product_id, group_id: i.group_id ?? null })), board.groups);
      if (board.created_group_id) pickGroup(board.created_group_id);
    } catch (e: any) { toast.error(e?.message || "Could not create the group"); }
  };

  return (
    <div className="relative">
      <button
        onClick={() => { setOpen((o) => !o); if (!open) refreshJobs(); }}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${job ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-stone-300 bg-white text-stone-600"}`}
        title="Which job the + button pins to"
      >
        <ClipboardList size={14} className={job ? "text-emerald-700" : "text-stone-400"} />
        {job ? (
          <span className="max-w-[18rem] truncate">
            <span className="text-[11px] uppercase tracking-wide text-emerald-700/80">Pinning to </span>
            <b>{job.name}</b>{group ? <span className="text-emerald-800"> · {group.name}</span> : null}
            {pinnedCount > 0 && <span className="ml-1.5 rounded-full bg-emerald-700 px-1.5 text-[10px] font-semibold text-white">{pinnedCount}</span>}
          </span>
        ) : (
          <span>Pick a job to pin to</span>
        )}
        <ChevronDown size={13} className="text-stone-400" />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-1 w-80 rounded-xl border border-stone-200 bg-white p-3 shadow-lg" onMouseLeave={() => setOpen(false)}>
          <label className="flex flex-col gap-1 text-xs text-stone-500">
            Job
            <div className="flex gap-1.5">
              <select value={value.jobId ?? ""} onChange={(e) => pickJob(e.target.value ? Number(e.target.value) : null)} className={`${sel} flex-1`}>
                <option value="">— none —</option>
                {jobs.map((j) => <option key={j.id} value={j.id}>{j.name}{j.item_count ? ` (${j.item_count})` : ""}</option>)}
              </select>
              <button onClick={newJob} className="rounded-md border border-stone-300 px-2 text-stone-600 hover:border-emerald-400 hover:text-emerald-700" title="New job"><Plus size={14} /></button>
            </div>
          </label>
          {value.jobId && (
            <label className="mt-3 flex flex-col gap-1 text-xs text-stone-500">
              Group <span className="font-normal text-stone-400">(optional: Ornaments, Garland…)</span>
              <div className="flex gap-1.5">
                <select value={value.groupId ?? ""} onChange={(e) => pickGroup(e.target.value ? Number(e.target.value) : null)} className={`${sel} flex-1`}>
                  <option value="">— no group —</option>
                  {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
                <button onClick={newGroup} className="rounded-md border border-stone-300 px-2 text-stone-600 hover:border-emerald-400 hover:text-emerald-700" title="New group"><Plus size={14} /></button>
              </div>
            </label>
          )}
          <div className="mt-3 flex items-center justify-between text-[11px] text-stone-400">
            <span>Hit + on any card to pin it here.</span>
            {value.jobId && <Link to={`/jobs/${value.jobId}`} className="font-medium text-emerald-700 hover:underline">Open the board</Link>}
          </div>
        </div>
      )}
    </div>
  );
}
