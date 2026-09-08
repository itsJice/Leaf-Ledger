import React, { useCallback, useEffect, useState } from "react";
import { ClipboardList, Plus, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  listBoards, createJob, writeWorkingJob,
  type BoardJob, type PinGroup, type WorkingJob,
} from "utils/jobs";
import { loadPins } from "utils/pinsCache";

// "Pinning to: Hanover". Sits in the Catalog Search header so the + button on
// every card knows which job a pin goes to. The choice is remembered per
// browser; the pins themselves are shared on the server.
//
// This only ever picks a JOB, never a group — group is deliberately not
// choosable here, so a + click always asks which group to file into (unless
// something more specific, like "Add options" on a board's own group
// section, has already set one). Groups still live on the job's board page.

interface Props {
  value: WorkingJob;
  onChange: (v: WorkingJob) => void;
}

const sel = "rounded-md border border-stone-300 bg-white px-2 py-1 text-sm text-stone-800 outline-none focus:border-emerald-500";

export default function WorkingJobBar({ value, onChange }: Props) {
  const [jobs, setJobs] = useState<BoardJob[]>([]);
  const [groups, setGroups] = useState<PinGroup[]>([]);
  const [open, setOpen] = useState(false);

  const refreshJobs = useCallback(async () => {
    try { setJobs(await listBoards()); } catch { setJobs([]); }
  }, []);
  useEffect(() => { refreshJobs(); }, [refreshJobs]);

  // Only fetched to resolve a group's name for display — e.g. a job opened
  // via a board's "Add options" already carries a group, and that context is
  // worth showing even though it can't be changed from here.
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
          <div className="mt-3 flex items-center justify-between text-[11px] text-stone-400">
            <span>Hit + on any card — it'll ask which group.</span>
            {value.jobId && <Link to={`/jobs/${value.jobId}`} className="font-medium text-emerald-700 hover:underline">Open the board</Link>}
          </div>
        </div>
      )}
    </div>
  );
}
