import React, { useEffect, useState } from "react";
import { Sparkles, Image, Trash2, RefreshCw, ChevronDown, AlertCircle } from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { toast } from "sonner";

type ArrangementSummary = { id: number; name: string; client_name?: string };
type Mockup = {
  id: number;
  arrangement_id: number;
  style: string;
  image_url?: string;
  prompt_used?: string;
  status: string;
  created_at: string;
};

const STYLES = [
  { value: "photo-realistic", label: "Photo-Realistic", description: "Detailed, lifelike render" },
  { value: "illustrated", label: "Illustrated", description: "Painterly botanical art" },
  { value: "mood-board", label: "Mood Board", description: "Flat lay design layout" },
];

const MOCKUPS_PROJECTS_CACHE_KEY = "leaf-ledger:mockups-projects-cache:v1";

function readMockupsProjectsCache(): ArrangementSummary[] {
  try {
    const raw = localStorage.getItem(MOCKUPS_PROJECTS_CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return Array.isArray(parsed?.arrangements) ? parsed.arrangements : [];
  } catch {
    return [];
  }
}

function writeMockupsProjectsCache(arrangements: ArrangementSummary[]) {
  try {
    localStorage.setItem(
      MOCKUPS_PROJECTS_CACHE_KEY,
      JSON.stringify({ arrangements, cachedAt: Date.now() })
    );
  } catch {
    // Ignore storage issues.
  }
}

export default function Mockups() {
  const [arrangements, setArrangements] = useState<ArrangementSummary[]>(readMockupsProjectsCache);
  const [selectedArrangement, setSelectedArrangement] = useState("");
  const [selectedStyle, setSelectedStyle] = useState("photo-realistic");
  const [mockups, setMockups] = useState<Mockup[]>([]);
  const [generating, setGenerating] = useState(false);
  const [loadingMockups, setLoadingMockups] = useState(false);

  useEffect(() => {
    apiClient.list_arrangements()
      .then((r) => r.json())
      .then((data: ArrangementSummary[]) => {
        setArrangements(data);
        writeMockupsProjectsCache(data);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedArrangement) { setMockups([]); return; }
    setLoadingMockups(true);
    apiClient.list_mockups({ arrangementId: Number(selectedArrangement) })
      .then((r) => r.json())
      .then(setMockups)
      .catch(() => toast.error("Failed to load mockups"))
      .finally(() => setLoadingMockups(false));
  }, [selectedArrangement]);

  const generate = async () => {
    if (!selectedArrangement) { toast.error("Select an arrangement first"); return; }
    setGenerating(true);
    try {
      const res = await apiClient.generate_mockup({ arrangement_id: Number(selectedArrangement), style: selectedStyle });
      const mockup = await res.json();
      setMockups((prev) => [mockup, ...prev]);
      toast.success("Mockup generated!");
    } catch (e: any) {
      const msg = e?.message || "Generation failed";
      toast.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const deleteMockup = async (id: number) => {
    try {
      await apiClient.delete_mockup({ mockupId: id });
      setMockups((prev) => prev.filter((m) => m.id !== id));
      toast.success("Mockup deleted");
    } catch {
      toast.error("Failed to delete mockup");
    }
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>AI Mockups</h1>
          <p className="text-xs text-stone-500 mt-0.5">Generate visual renders of your arrangements</p>
        </div>
      </header>

      <div className="px-10 py-8 max-w-5xl">
        {/* Generator panel */}
        <div className="bg-white rounded-2xl border border-stone-200 p-6 mb-8">
          <h2 className="text-base font-semibold text-stone-700 mb-4" style={{ fontFamily: "Georgia, serif" }}>Generate a new mockup</h2>
          <div className="grid grid-cols-2 gap-4 mb-5">
            {/* Arrangement select */}
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1.5">Arrangement</label>
              <div className="relative">
                <select
                  className="w-full appearance-none border border-stone-200 rounded-lg pl-3 pr-8 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  value={selectedArrangement}
                  onChange={(e) => setSelectedArrangement(e.target.value)}
                >
                  <option value="">Select arrangement...</option>
                  {arrangements.map((a) => (
                    <option key={a.id} value={a.id}>{a.name}{a.client_name ? ` — ${a.client_name}` : ""}</option>
                  ))}
                </select>
                <ChevronDown size={12} className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 pointer-events-none" />
              </div>
            </div>
            {/* Style select */}
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1.5">Style</label>
              <div className="grid grid-cols-3 gap-2">
                {STYLES.map((s) => (
                  <button
                    key={s.value}
                    onClick={() => setSelectedStyle(s.value)}
                    className={`text-left p-2.5 rounded-lg border text-xs transition-all ${
                      selectedStyle === s.value
                        ? "border-emerald-400 bg-emerald-50 text-emerald-800"
                        : "border-stone-200 text-stone-600 hover:border-stone-300"
                    }`}
                  >
                    <p className="font-semibold">{s.label}</p>
                    <p className="text-stone-400 mt-0.5 leading-tight">{s.description}</p>
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={generate}
              disabled={generating || !selectedArrangement}
              className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white rounded-lg disabled:opacity-50 hover:opacity-90 transition-opacity"
              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
            >
              {generating ? (
                <><RefreshCw size={14} className="animate-spin" /> Generating...</>
              ) : (
                <><Sparkles size={14} /> Generate Mockup</>
              )}
            </button>
            {generating && (
              <p className="text-xs text-stone-400">This may take 15–30 seconds...</p>
            )}
          </div>

          {/* API key warning */}
          <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200">
            <AlertCircle size={14} className="text-amber-500 mt-0.5 flex-shrink-0" />
            <p className="text-xs text-amber-700 leading-relaxed">
              Requires an OpenAI API key. Add <code className="font-mono bg-amber-100 px-1 rounded">OPENAI_API_KEY</code> in the Secrets tab to enable image generation.
            </p>
          </div>
        </div>

        {/* Mockup gallery */}
        <div>
          <h2 className="text-base font-semibold text-stone-700 mb-4" style={{ fontFamily: "Georgia, serif" }}>Generated mockups</h2>
          {loadingMockups ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : !selectedArrangement ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
                <Sparkles size={22} className="text-emerald-600" strokeWidth={1.5} />
              </div>
              <p className="text-sm font-medium text-stone-500">Select an arrangement to view its mockups</p>
            </div>
          ) : mockups.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="w-14 h-14 rounded-full flex items-center justify-center mb-3" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
                <Image size={22} className="text-emerald-600" strokeWidth={1.5} />
              </div>
              <p className="text-sm font-medium text-stone-600 mb-1">No mockups yet</p>
              <p className="text-xs text-stone-400">Generate your first mockup above</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-5 xl:grid-cols-3">
              {mockups.map((m) => (
                <div key={m.id} className="bg-white rounded-xl border border-stone-200 overflow-hidden group">
                  <div className="relative aspect-square bg-stone-100">
                    {m.status === "generating" ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                        <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
                        <p className="text-xs text-stone-400">Generating...</p>
                      </div>
                    ) : m.status === "failed" ? (
                      <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                        <AlertCircle size={24} className="text-red-400" />
                        <p className="text-xs text-red-400">Generation failed</p>
                      </div>
                    ) : m.image_url ? (
                      <img src={m.image_url} alt={m.style} className="w-full h-full object-cover" />
                    ) : null}
                    <button
                      onClick={() => deleteMockup(m.id)}
                      className="absolute top-2 right-2 w-7 h-7 flex items-center justify-center rounded-full bg-white/80 backdrop-blur-sm text-stone-400 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                  <div className="px-4 py-3">
                    <p className="text-xs font-semibold text-stone-700 capitalize">{m.style.replace("-", " ")}</p>
                    <p className="text-xs text-stone-400 mt-0.5">{new Date(m.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}
