/**
 * CatalogWizard — lets designers select exactly which catalog sections/categories
 * to scrape for a given supplier. Opens as a modal dialog.
 *
 * Modes:
 * - View mode (default): Shows saved selections as checked, read-only. Edit button enters edit mode.
 * - Edit mode: Checkboxes interactive. Cancel reverts to saved state. Save writes to DB.
 *
 * Flow:
 * 1. Mount → discover_catalog (cache-first) + get_catalog_filters in sequence
 * 2. Render in VIEW mode with saved DDCODEs pre-checked
 * 3. User clicks Edit → enter EDIT mode
 * 4. User checks/unchecks → clicks Save Configuration → saves + returns to view mode
 * 5. Cancel in edit mode → reverts to last saved selection
 * 6. "Re-discover live" forces a fresh crawl (force_refresh=true)
 */
import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  X, Loader2, RefreshCw, CheckSquare, Square, ChevronDown,
  ChevronRight, CheckCircle2, Minus, AlertTriangle, BookOpen, Pencil,
} from "lucide-react";
import { apiClient } from "app";
import { toast } from "sonner";
import type { CatalogSection, DiscoverCatalogResponse, CatalogFilters } from "types";

// ── Types ────────────────────────────────────────────────────────────────────

interface Subcategory {
  ddcode: string;
  label: string;
  item_count: number;
}

interface SectionState {
  name: string;
  subcategories: Subcategory[];
  expanded: boolean;
}

interface Props {
  supplierId: number;
  supplierName: string;
  onClose: () => void;
  onSaved: () => void;
}

async function readCatalogError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.message === "string") return body.message;
  } catch {
    // Fall through to a status-based message when the response body is not JSON.
  }
  return `Catalog discovery failed with status ${res.status}.`;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function sectionCheckState(
  section: SectionState,
  selected: Set<string>,
): "all" | "none" | "partial" {
  const total = section.subcategories.length;
  if (total === 0) return "none";
  const checked = section.subcategories.filter((s) => selected.has(s.ddcode)).length;
  if (checked === 0) return "none";
  if (checked === total) return "all";
  return "partial";
}

// ── Component ────────────────────────────────────────────────────────────────

export default function CatalogWizard({ supplierId, supplierName, onClose, onSaved }: Props) {
  const onSavedRef = useRef(onSaved);
  const [sections, setSections] = useState<SectionState[]>([]);
  // `savedSelected` = what's persisted in DB; `selected` = current working set in edit mode
  const [savedSelected, setSavedSelected] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editMode, setEditMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [fromCache, setFromCache] = useState(false);
  const [saving, setSaving] = useState(false);
  const [liveRefreshing, setLiveRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [totalProducts, setTotalProducts] = useState(0);
  const [sectionListingTotal, setSectionListingTotal] = useState(0);

  useEffect(() => {
    onSavedRef.current = onSaved;
  }, [onSaved]);

  // ── Load catalog (cache-first) ──────────────────────────────────────────────
  const loadCatalog = useCallback(async (forceRefresh = false) => {
    if (forceRefresh) {
      setLiveRefreshing(true);
    } else {
      setLoading(true);
    }
    setLoadError(null);

    try {
      // 1. Discover categories (cache-first, or live if force_refresh)
      const res = await fetch(
        `/api/suppliers/${supplierId}/discover-catalog?force_refresh=${forceRefresh ? "true" : "false"}`,
        {
          method: "POST",
          cache: "no-store",
          headers: { "Cache-Control": "no-cache" },
        },
      );
      if (!res.ok) {
        throw new Error(await readCatalogError(res));
      }
      const data: DiscoverCatalogResponse = await res.json();

      const sectionStates: SectionState[] = (data.sections || []).map((sec: CatalogSection) => ({
        name: sec.name,
        subcategories: (sec.subcategories || []).map((sub: Record<string, unknown>) => ({
          ddcode: sub.ddcode as string,
          label: (sub.label as string) || (sub.ddcode as string),
          item_count: (sub.item_count as number) || 0,
        })),
        expanded: true,  // start expanded so user can see all options
      }));

      setSections(sectionStates);
      setFromCache(data.from_cache);
      setTotalProducts(data.total_products || 0);
      setSectionListingTotal(data.section_listing_total || 0);

      // 2. Load existing selections and pre-check them
      const filtersRes = await apiClient.get_catalog_filters({ supplierId });
      const filters: CatalogFilters = await filtersRes.json();
      const savedCats = new Set<string>(filters.categories || []);
      const allCats = new Set<string>();
      sectionStates.forEach((sec) => sec.subcategories.forEach((sub) => allCats.add(sub.ddcode)));
      // Keep savedSelected as the DB truth; selected mirrors it for view mode
      setSavedSelected(savedCats);
      setSelected(savedCats.size > 0 ? savedCats : allCats);
      // Always open in view mode (not edit) so user sees what was saved
      setEditMode(false);
      onSavedRef.current();

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load catalog";
      setLoadError(msg);
      toast.error(msg || "Could not load catalog — check supplier credentials.");
    } finally {
      setLoading(false);
      setLiveRefreshing(false);
    }
  }, [supplierId]);

  useEffect(() => {
    loadCatalog(false);
  }, [loadCatalog]);

  // ── Selection helpers ────────────────────────────────────────────────────────

  const getAllCategoryCodes = () => {
    const all = new Set<string>();
    sections.forEach((sec) => sec.subcategories.forEach((s) => all.add(s.ddcode)));
    return all;
  };

  // Enter edit mode — working copy starts from saved state
  const enterEdit = () => {
    if (savedSelected.size > 0) {
      setSelected(new Set(savedSelected));
    } else {
      setSelected(getAllCategoryCodes());
    }
    setEditMode(true);
  };

  // Cancel edit — discard working changes, go back to view mode
  const cancelEdit = () => {
    if (savedSelected.size > 0) {
      setSelected(new Set(savedSelected));
    } else {
      setSelected(getAllCategoryCodes());
    }
    setEditMode(false);
  };

  const toggleSubcategory = (ddcode: string) => {
    if (!editMode) return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ddcode)) next.delete(ddcode);
      else next.add(ddcode);
      return next;
    });
  };

  const toggleSection = (section: SectionState) => {
    if (!editMode) return;
    const state = sectionCheckState(section, selected);
    setSelected((prev) => {
      const next = new Set(prev);
      if (state === "all") {
        section.subcategories.forEach((s) => next.delete(s.ddcode));
      } else {
        section.subcategories.forEach((s) => next.add(s.ddcode));
      }
      return next;
    });
  };

  const selectAll = () => {
    if (!editMode) return;
    setSelected(getAllCategoryCodes());
  };

  const clearFilter = () => {
    if (!editMode) return;
    selectAll();
  };

  const toggleSectionExpanded = (idx: number) => {
    setSections((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, expanded: !s.expanded } : s))
    );
  };

  // ── Save ─────────────────────────────────────────────────────────────────────

  const handleSave = async () => {
    setSaving(true);
    try {
      const ddcodes = Array.from(selected);
      const allCount = sections.reduce((acc, s) => acc + s.subcategories.length, 0);
      const categoriesToSave = ddcodes.length === allCount ? [] : ddcodes;
      await apiClient.save_catalog_filters(
        { supplierId },
        { sections: [], categories: categoriesToSave },
      );

      // Commit working selection → saved state; return to view mode
      const committed = new Set(categoriesToSave);
      setSavedSelected(committed);
      setEditMode(false);

      const count = categoriesToSave.length;
      if (count === 0) {
        toast.success("Catalog filter cleared — next scrape will include everything.");
      } else {
        toast.success(
          `Saved ${count} selected ${count === 1 ? "category" : "categories"}. Next scrape will only import these.`
        );
      }
      onSaved();
    } catch {
      toast.error("Failed to save catalog selections.");
    } finally {
      setSaving(false);
    }
  };

  // ── Derived counts ───────────────────────────────────────────────────────────

  const totalSubs = sections.reduce((acc, s) => acc + s.subcategories.length, 0);
  const selectedCount = selected.size;
  const allCategoriesSelected = totalSubs > 0 && selectedCount === totalSubs;
  const selectedProducts = sections
    .flatMap((s) => s.subcategories)
    .filter((s) => selected.has(s.ddcode))
    .reduce((acc, s) => acc + (s.item_count || 0), 0);
  const selectedSummary = allCategoriesSelected && totalProducts > 0
    ? {
        value: totalProducts,
        label: "unique products",
        prefix: "",
      }
    : {
        value: selectedProducts,
        label: "category listings before dedupe",
        prefix: "~",
      };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(30,25,20,0.45)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Modal panel */}
      <div
        className="relative flex flex-col bg-white rounded-2xl shadow-2xl w-full max-w-2xl"
        style={{ maxHeight: "88vh" }}
      >
        {/* ── Header ── */}
        <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-stone-100 flex-shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <BookOpen size={16} className="text-emerald-700" />
              <h2 className="text-base font-semibold text-stone-800" style={{ fontFamily: "'Playfair Display', serif" }}>
                Configure Catalog
              </h2>
              {/* Mode badge */}
              {!loading && !liveRefreshing && !loadError && (
                <span className={`ml-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${
                  editMode
                    ? "bg-amber-50 text-amber-700 border border-amber-200"
                    : "bg-stone-100 text-stone-500 border border-stone-200"
                }`}>
                  {editMode ? "Editing" : "View"}
                </span>
              )}
            </div>
            <p className="text-xs text-stone-500">
              {supplierName} · {editMode ? "Make changes then save" : "Select which categories to include in future scrapes"}
            </p>
          </div>
          <div className="flex items-center gap-2 ml-4">
            {/* Edit button — only in view mode */}
            {!loading && !liveRefreshing && !loadError && sections.length > 0 && !editMode && (
              <button
                onClick={enterEdit}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-emerald-700 border border-emerald-200 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors"
              >
                <Pencil size={11} /> Edit
              </button>
            )}
            <button
              onClick={onClose}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── Loading state ── */}
        {(loading || liveRefreshing) && (
          <div className="flex flex-col items-center justify-center py-20 gap-4 flex-shrink-0">
            <Loader2 size={28} className="text-emerald-600 animate-spin" />
            <div className="text-center">
              <p className="text-sm font-medium text-stone-700">
                {liveRefreshing ? "Re-discovering live catalog…" : "Loading catalog…"}
              </p>
              <p className="text-xs text-stone-400 mt-1">
                {liveRefreshing
                  ? "Logging into supplier site — this takes 1–3 minutes"
                  : "Checking cached categories and live totals…"}
              </p>
            </div>
          </div>
        )}

        {/* ── Error state ── */}
        {!loading && !liveRefreshing && loadError && (
          <div className="flex flex-col items-center justify-center py-16 gap-4 px-6">
            <AlertTriangle size={28} className="text-amber-500" />
            <div className="text-center">
              <p className="text-sm font-semibold text-stone-700">Could not load catalog</p>
              <p className="text-xs text-stone-500 mt-1 max-w-xs">
                {loadError}
              </p>
              <p className="text-[11px] text-stone-400 mt-2 max-w-xs">
                Update the supplier credentials, then try live discovery again.
              </p>
            </div>
            <button
              onClick={() => loadCatalog(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg"
              style={{ backgroundColor: "#2d5a33" }}
            >
              <RefreshCw size={13} /> Try Again
            </button>
          </div>
        )}

        {/* ── Main content ── */}
        {!loading && !liveRefreshing && !loadError && sections.length > 0 && (
          <>
            {/* Stats bar */}
            <div className="flex items-center gap-6 px-6 py-3 bg-stone-50 border-b border-stone-100 flex-shrink-0">
              <div className="flex items-center gap-1.5">
                {fromCache ? (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
                    <CheckCircle2 size={9} /> Cached categories
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-700 bg-amber-50 border border-amber-100 px-2 py-0.5 rounded-full">
                    <RefreshCw size={9} /> Live catalog
                  </span>
                )}
              </div>
              <div className="text-xs text-stone-500">
                <span className="font-semibold text-stone-800">{selectedCount}</span>
                {" / "}
                {totalSubs} categories selected
              </div>
              {selectedCount > 0 && (
                <div className="text-xs text-stone-500">
                  {selectedSummary.prefix}
                  <span className="font-semibold text-stone-800">{selectedSummary.value.toLocaleString()}</span>{" "}
                  {selectedSummary.label}
                  {allCategoriesSelected && sectionListingTotal > totalProducts && (
                    <span className="text-stone-400">
                      {" "}({sectionListingTotal.toLocaleString()} section listings)
                    </span>
                  )}
                </div>
              )}
              {/* Select all / Clear all — only in edit mode */}
              {editMode && (
                <div className="ml-auto flex items-center gap-2">
                  <button
                    onClick={selectAll}
                    className="text-[11px] text-emerald-700 hover:text-emerald-800 font-medium underline underline-offset-2"
                  >
                    Select all
                  </button>
                  <span className="text-stone-300">·</span>
                  <button
                    onClick={clearFilter}
                    className="text-[11px] text-stone-500 hover:text-stone-700 font-medium underline underline-offset-2"
                  >
                    Clear filter
                  </button>
                </div>
              )}
            </div>

            {/* Sections checklist */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
              {sections.map((section, idx) => {
                const checkState = sectionCheckState(section, selected);
                const sectionSelectedCount = section.subcategories.filter((s) => selected.has(s.ddcode)).length;

                return (
                  <div key={section.name} className="border border-stone-200 rounded-xl overflow-hidden">
                    {/* Section header */}
                    <button
                      className="w-full flex items-center gap-3 px-4 py-3 bg-stone-50 hover:bg-stone-100 transition-colors text-left"
                      onClick={() => toggleSectionExpanded(idx)}
                    >
                      {/* Section checkbox — interactive only in edit mode */}
                      <div
                        onClick={(e) => { e.stopPropagation(); if (editMode) toggleSection(section); }}
                        className={`flex-shrink-0 w-5 h-5 flex items-center justify-center rounded border transition-colors ${
                          editMode ? "cursor-pointer" : "cursor-default"
                        }`}
                        style={{
                          borderColor: checkState !== "none" ? "#2d5a33" : "#d6d3d1",
                          backgroundColor: checkState === "all" ? "#2d5a33" : "transparent",
                        }}
                      >
                        {checkState === "all" && <CheckSquare size={12} className="text-white" />}
                        {checkState === "partial" && <Minus size={12} style={{ color: "#2d5a33" }} />}
                        {checkState === "none" && <Square size={12} className="text-transparent" />}
                      </div>

                      <span className="flex-1 text-sm font-semibold text-stone-800">{section.name}</span>

                      {/* Count badge */}
                      <span className="text-[11px] text-stone-500 tabular-nums">
                        {sectionSelectedCount > 0 ? (
                          <span className="font-semibold text-emerald-700">{sectionSelectedCount}</span>
                        ) : (
                          <span>0</span>
                        )}
                        /{section.subcategories.length}
                      </span>

                      {/* Expand chevron */}
                      <span className="text-stone-400 flex-shrink-0">
                        {section.expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </span>
                    </button>

                    {/* Subcategories */}
                    {section.expanded && (
                      <div className="divide-y divide-stone-100">
                        {section.subcategories.map((sub) => {
                          const isChecked = selected.has(sub.ddcode);
                          return (
                            <label
                              key={sub.ddcode}
                              className={`flex items-center gap-3 px-4 py-2.5 transition-colors ${
                                editMode ? "cursor-pointer hover:bg-stone-50" : "cursor-default"
                              }`}
                            >
                              {/* Custom checkbox — clickable only in edit mode */}
                              <div
                                onClick={() => editMode && toggleSubcategory(sub.ddcode)}
                                className={`flex-shrink-0 w-4 h-4 rounded border transition-colors flex items-center justify-center ${
                                  editMode ? "cursor-pointer" : "cursor-default"
                                }`}
                                style={{
                                  borderColor: isChecked ? "#2d5a33" : "#d6d3d1",
                                  backgroundColor: isChecked ? "#2d5a33" : "transparent",
                                }}
                              >
                                {isChecked && (
                                  <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
                                    <path d="M1 3.5L3.5 6L8 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                )}
                              </div>

                              {/* Label */}
                              <span
                                className={`flex-1 text-xs transition-colors ${
                                  isChecked ? "text-stone-800 font-medium" : "text-stone-500"
                                }`}
                              >
                                {sub.label}
                              </span>

                              {/* DDCODE */}
                              <span className="text-[10px] font-mono text-stone-300">{sub.ddcode}</span>

                              {/* Item count */}
                              <span className="text-[11px] text-stone-400 tabular-nums flex-shrink-0">
                                {sub.item_count > 0 ? `~${sub.item_count.toLocaleString()}` : "0"}
                              </span>
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* ── Footer ── */}
            <div className="flex items-center justify-between gap-4 px-6 py-4 border-t border-stone-100 bg-stone-50 flex-shrink-0 rounded-b-2xl">
              {/* Re-discover — only in view mode (don't interrupt active editing) */}
              {!editMode && (
                <button
                  onClick={() => loadCatalog(true)}
                  disabled={liveRefreshing || saving}
                  className="flex items-center gap-1.5 text-xs text-stone-500 hover:text-stone-700 font-medium disabled:opacity-40 transition-colors"
                >
                  <RefreshCw size={12} />
                  Re-discover live
                </button>
              )}
              {editMode && <div />} {/* spacer to keep right side aligned */}

              <div className="flex items-center gap-3">
                {/* Selected summary pill */}
                {allCategoriesSelected ? (
                  <p className="text-xs text-stone-400 italic">No filter — scrapes everything</p>
                ) : (
                  <p className="text-xs text-stone-500">
                    <span className="font-semibold text-emerald-700">{selectedCount}</span> selected
                  </p>
                )}

                {/* VIEW MODE: just a close button */}
                {!editMode && (
                  <button
                    onClick={onClose}
                    className="px-4 py-2 text-sm text-stone-600 border border-stone-200 rounded-lg hover:bg-stone-100 transition-colors"
                  >
                    Close
                  </button>
                )}

                {/* EDIT MODE: Cancel + Save */}
                {editMode && (
                  <>
                    <button
                      onClick={cancelEdit}
                      disabled={saving}
                      className="px-4 py-2 text-sm text-stone-600 border border-stone-200 rounded-lg hover:bg-stone-100 transition-colors disabled:opacity-40"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={saving}
                      className="flex items-center gap-2 px-5 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-50 hover:opacity-90 transition-colors"
                      style={{ backgroundColor: "#2d5a33" }}
                    >
                      {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                      {saving ? "Saving…" : "Save Configuration"}
                    </button>
                  </>
                )}
              </div>
            </div>
          </>
        )}

        {/* Empty state — catalog loaded but no sections returned */}
        {!loading && !liveRefreshing && !loadError && sections.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 px-6">
            <BookOpen size={28} className="text-stone-300" />
            <p className="text-sm font-medium text-stone-600">No categories found</p>
            <p className="text-xs text-stone-400 text-center max-w-xs">
              The catalog may still be loading or credentials may need to be updated.
            </p>
            <button
              onClick={() => loadCatalog(true)}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg mt-1"
              style={{ backgroundColor: "#2d5a33" }}
            >
              <RefreshCw size={13} /> Try Live Discovery
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
