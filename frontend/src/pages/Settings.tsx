import React, { useEffect, useState } from "react";
import { Save, Plus, Trash2, Settings as SettingsIcon, DollarSign, Users } from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { categoryLabel } from "utils/format";
import { toast } from "sonner";

const CATEGORIES = ["plant", "container", "filler", "accent", "other"];

type CategoryMarkup = { id: number; category: string; markup_percentage: number; updated_at: string };

export default function Settings() {
  const [globalMarkup, setGlobalMarkup] = useState(30);
  const [categoryMarkups, setCategoryMarkups] = useState<CategoryMarkup[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [addingCategory, setAddingCategory] = useState(false);
  const [newCat, setNewCat] = useState("");
  const [newCatMarkup, setNewCatMarkup] = useState("30");

  const load = async () => {
    try {
      const data = await apiClient.get_markup_settings().then((r) => r.json());
      setGlobalMarkup(data.global_markup);
      setCategoryMarkups(data.category_markups);
    } catch {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const saveGlobal = async () => {
    setSaving(true);
    try {
      await apiClient.update_markup({ category: null, markup_percentage: globalMarkup });
      toast.success("Global markup saved");
    } catch {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveCategoryMarkup = async (category: string, value: number) => {
    try {
      await apiClient.update_markup({ category, markup_percentage: value });
      toast.success(`${categoryLabel(category)} markup saved`);
    } catch {
      toast.error("Failed to save");
    }
  };

  const deleteCategoryMarkup = async (category: string) => {
    try {
      await apiClient.delete_category_markup({ category });
      setCategoryMarkups((prev) => prev.filter((m) => m.category !== category));
      toast.success("Category override removed");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const addCategoryMarkup = async () => {
    if (!newCat) { toast.error("Select a category"); return; }
    if (categoryMarkups.some((m) => m.category === newCat)) { toast.error("Override already exists for this category"); return; }
    try {
      await apiClient.update_markup({ category: newCat, markup_percentage: parseFloat(newCatMarkup) });
      await load();
      setAddingCategory(false);
      setNewCat("");
      setNewCatMarkup("30");
      toast.success("Category markup added");
    } catch {
      toast.error("Failed to add");
    }
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Settings</h1>
          <p className="text-xs text-stone-500 mt-0.5">Manage markup percentages and application settings</p>
        </div>
      </header>

      <div className="px-10 py-8 max-w-2xl space-y-6">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            {/* Global markup */}
            <div className="bg-white rounded-xl border border-stone-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#e8f0e8" }}>
                  <DollarSign size={15} className="text-emerald-700" />
                </div>
                <h2 className="text-sm font-semibold text-stone-800">Global Markup</h2>
              </div>
              <p className="text-xs text-stone-500 mb-4 leading-relaxed">
                Applied to all arrangements by default. Category overrides below will take precedence for specific product types.
              </p>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 flex-1">
                  <input
                    type="number"
                    min="0"
                    max="500"
                    step="0.5"
                    className="w-24 border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                    value={globalMarkup}
                    onChange={(e) => setGlobalMarkup(parseFloat(e.target.value))}
                  />
                  <span className="text-sm font-medium text-stone-600">%</span>
                </div>
                <button
                  onClick={saveGlobal}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-60 hover:opacity-90"
                  style={{ backgroundColor: "#2d5a33" }}
                >
                  <Save size={13} />
                  {saving ? "Saving..." : "Save"}
                </button>
              </div>
            </div>

            {/* Category overrides */}
            <div className="bg-white rounded-xl border border-stone-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#e8f0e8" }}>
                    <SettingsIcon size={15} className="text-emerald-700" />
                  </div>
                  <h2 className="text-sm font-semibold text-stone-800">Category Overrides</h2>
                </div>
                <button
                  onClick={() => setAddingCategory(true)}
                  className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-50 transition-colors"
                >
                  <Plus size={12} /> Add override
                </button>
              </div>
              <p className="text-xs text-stone-500 mb-4 leading-relaxed">Override the global markup for specific product categories.</p>

              {addingCategory && (
                <div className="flex items-center gap-3 mb-4 p-3 bg-stone-50 rounded-lg border border-stone-200">
                  <select
                    className="border border-stone-200 rounded-lg px-2 py-1.5 text-sm flex-1 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                    value={newCat}
                    onChange={(e) => setNewCat(e.target.value)}
                  >
                    <option value="">Select category</option>
                    {CATEGORIES.filter((c) => !categoryMarkups.some((m) => m.category === c)).map((c) => (
                      <option key={c} value={c}>{categoryLabel(c)}</option>
                    ))}
                  </select>
                  <input
                    type="number"
                    className="w-20 border border-stone-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                    value={newCatMarkup}
                    onChange={(e) => setNewCatMarkup(e.target.value)}
                    placeholder="%"
                  />
                  <span className="text-sm text-stone-400">%</span>
                  <button onClick={addCategoryMarkup} className="px-3 py-1.5 text-xs font-semibold text-white rounded-lg hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>Add</button>
                  <button onClick={() => setAddingCategory(false)} className="text-stone-400 hover:text-stone-600 text-xs">Cancel</button>
                </div>
              )}

              {categoryMarkups.length === 0 && !addingCategory ? (
                <p className="text-sm text-stone-400 text-center py-6">No category overrides. Using global markup for all categories.</p>
              ) : (
                <div className="space-y-2">
                  {categoryMarkups.map((m) => (
                    <div key={m.category} className="flex items-center gap-4 p-3 rounded-lg border border-stone-100 hover:bg-stone-50 transition-colors">
                      <span className="text-sm font-medium text-stone-700 flex-1">{categoryLabel(m.category)}</span>
                      <input
                        type="number"
                        className="w-20 border border-stone-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        defaultValue={m.markup_percentage}
                        onBlur={(e) => saveCategoryMarkup(m.category, parseFloat(e.target.value))}
                      />
                      <span className="text-sm text-stone-400">%</span>
                      <button onClick={() => deleteCategoryMarkup(m.category)} className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-red-50 text-stone-300 hover:text-red-400 transition-colors">
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Suppliers link */}
            <div className="bg-white rounded-xl border border-stone-200 p-6">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ backgroundColor: "#e8f0e8" }}>
                  <Users size={15} className="text-emerald-700" />
                </div>
                <h2 className="text-sm font-semibold text-stone-800">Supplier Management</h2>
              </div>
              <p className="text-xs text-stone-500 mb-4">Manage your supplier profiles, contacts, and credentials.</p>
              <a
                href="/suppliers"
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-white rounded-lg hover:opacity-90"
                style={{ backgroundColor: "#2d5a33" }}
              >
                Manage Suppliers
              </a>
            </div>
          </>
        )}
      </div>
    </Layout>
  );
}
