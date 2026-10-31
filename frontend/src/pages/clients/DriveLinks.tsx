import React, { useState } from "react";
import { toast } from "sonner";
import { ExternalLink, FolderOpen, FolderPlus, Image, Pencil } from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { currentMe, isReadOnly } from "utils/me";

/**
 * The client's Google Drive folder, one tap from the card: a "Drive folder"
 * button that opens it in a new tab, and a smaller "Photos" button when the
 * photos folder is set too. With no folder, office staff see "Add folder"
 * (never a dead link); everyone else sees nothing.
 *
 * Stored on the client, not the season -- the folder is the same every year
 * (clients.drive_folder_url / drive_photos_url, migrations/026), written by
 * PUT /api/clients/{id}/drive-links, which only takes
 * https://drive.google.com/ links. The Install Schedule's stop popup shows
 * the same buttons.
 */

export interface DriveLinksValue {
  drive_folder_url?: string | null;
  drive_photos_url?: string | null;
}

export interface DriveLinksSaved {
  id: number;
  drive_folder_url: string | null;
  drive_photos_url: string | null;
}

const EDIT_ROLES = new Set(["staff", "admin", "super_admin"]);

/** Same people who edit the rest of the client card: office staff and up. */
export function canEditDriveLinks(): boolean {
  const me = currentMe();
  return Boolean(me && EDIT_ROLES.has(me.role) && !isReadOnly());
}

/** Is this a link the card may open? Mirrors app.libs.drive_links on the server. */
export function isDriveUrl(value: string | null | undefined): boolean {
  const text = (value || "").trim();
  if (!text || /\s/.test(text)) return false;
  try {
    const u = new URL(text);
    return u.protocol === "https:" && u.hostname.toLowerCase() === "drive.google.com"
      && !u.username && !u.password && !u.port && u.pathname.length > 1;
  } catch {
    return false;
  }
}

/** "" when fine, else what's wrong -- checked before Save so a typo never reaches the card. */
export function driveUrlProblem(value: string, label: string): string {
  if (!value.trim()) return "";
  return isDriveUrl(value) ? "" : `${label} must be a https://drive.google.com/ link`;
}

export async function saveDriveLinks(clientId: number, links: DriveLinksValue): Promise<DriveLinksSaved> {
  const res = await apiFetch(`/api/clients/${clientId}/drive-links`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(links),
  });
  if (!res.ok) {
    let why = res.status === 403 ? "This login can open the folder but can't change the link." : "Couldn't save the Drive links";
    try {
      const j = await res.json();
      if (j?.detail && res.status !== 403) why = String(j.detail);
    } catch { /* no body */ }
    throw new Error(why);
  }
  return res.json();
}

const BTN = "inline-flex min-h-[40px] items-center justify-center gap-2 rounded-lg border px-3 text-xs font-semibold sm:min-h-0 sm:py-2";

export function DriveLinks({
  clientId,
  links,
  onSaved,
  editable,
}: {
  clientId?: number | null;
  links: DriveLinksValue;
  onSaved?: (saved: DriveLinksSaved) => void;
  /** Defaults to the signed-in role (staff and up, not view-only logins). */
  editable?: boolean;
}) {
  const canEdit = (editable ?? canEditDriveLinks()) && clientId != null;
  const folder = isDriveUrl(links.drive_folder_url) ? links.drive_folder_url!.trim() : "";
  const photos = isDriveUrl(links.drive_photos_url) ? links.drive_photos_url!.trim() : "";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ folder: "", photos: "" });
  const [saving, setSaving] = useState(false);

  if (!folder && !photos && !canEdit) return null;

  const open = () => {
    setDraft({ folder: links.drive_folder_url || "", photos: links.drive_photos_url || "" });
    setEditing(true);
  };

  const folderProblem = driveUrlProblem(draft.folder, "Drive folder");
  const photosProblem = driveUrlProblem(draft.photos, "Photos folder");

  const save = async () => {
    if (clientId == null || folderProblem || photosProblem) return;
    setSaving(true);
    try {
      const saved = await saveDriveLinks(clientId, {
        drive_folder_url: draft.folder.trim(),
        drive_photos_url: draft.photos.trim(),
      });
      onSaved?.(saved);
      toast.success(saved.drive_folder_url || saved.drive_photos_url ? "Drive links saved" : "Drive links cleared");
      setEditing(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save the Drive links");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    const input = "w-full rounded-lg border px-3 py-2 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300";
    return (
      <form
        className="mb-4 grid gap-2.5 rounded-xl border border-stone-200 bg-white px-4 py-3"
        onSubmit={(e) => { e.preventDefault(); void save(); }}
        aria-label="Google Drive links"
      >
        <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
          <FolderOpen size={12} /> Google Drive
        </p>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-stone-600">Client folder link</span>
          <input
            autoFocus
            inputMode="url"
            autoComplete="off"
            value={draft.folder}
            onChange={(e) => setDraft((d) => ({ ...d, folder: e.target.value }))}
            placeholder="https://drive.google.com/drive/folders/..."
            className={`${input} ${folderProblem ? "border-red-300" : "border-stone-200"}`}
          />
          {folderProblem && <span className="mt-1 block text-xs text-red-600">{folderProblem}</span>}
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-stone-600">
            Photos folder link <span className="font-normal text-stone-400">(optional)</span>
          </span>
          <input
            inputMode="url"
            autoComplete="off"
            value={draft.photos}
            onChange={(e) => setDraft((d) => ({ ...d, photos: e.target.value }))}
            placeholder="https://drive.google.com/drive/folders/..."
            className={`${input} ${photosProblem ? "border-red-300" : "border-stone-200"}`}
          />
          {photosProblem && <span className="mt-1 block text-xs text-red-600">{photosProblem}</span>}
        </label>
        <p className="text-[11px] text-stone-400">In Drive, open the folder, then copy the link from the address bar. Leave a box empty to remove that link.</p>
        <div className="flex items-center justify-end gap-2">
          <button type="button" onClick={() => setEditing(false)} className="px-3 py-2 text-xs text-stone-500 hover:text-stone-700">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving || Boolean(folderProblem || photosProblem)}
            className="rounded-lg px-4 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
          >
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Google Drive">
      {folder ? (
        <a
          href={folder}
          target="_blank"
          rel="noopener noreferrer"
          className={`${BTN} border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-300 hover:bg-emerald-100`}
          title="Open the client's Google Drive folder in a new tab"
        >
          <FolderOpen size={15} />
          Drive folder
          <ExternalLink size={12} className="opacity-60" />
        </a>
      ) : canEdit ? (
        <button
          type="button"
          data-edit
          onClick={open}
          className={`${BTN} border-dashed border-stone-300 bg-white text-stone-500 hover:border-emerald-300 hover:text-emerald-700`}
          title="Paste the link to this client's Google Drive folder"
        >
          <FolderPlus size={15} />
          Add folder
        </button>
      ) : null}
      {photos && (
        <a
          href={photos}
          target="_blank"
          rel="noopener noreferrer"
          className={`${BTN} border-stone-200 bg-white px-2.5 font-medium text-stone-600 hover:border-emerald-300 hover:text-emerald-700`}
          title="Open the client's photos folder in a new tab"
        >
          <Image size={13} />
          Photos
        </a>
      )}
      {canEdit && (folder || photos) && (
        <button
          type="button"
          data-edit
          onClick={open}
          aria-label="Edit Drive links"
          title="Edit Drive links"
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-600 sm:h-8 sm:w-8"
        >
          <Pencil size={14} />
        </button>
      )}
    </div>
  );
}
