import { useEffect, useState, useCallback, useRef } from "react";
import { apiClient } from "app";
import type {
  AdminDashboardResponse,
  SupplierHealth,
  SyncLogEntry,
  PriceChangeEntry,
  CategoryIndexResponse,
  SupplierCategoryIndex,
} from "../apiclient/data-contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  CheckCircle,
  AlertCircle,
  Clock,
  RefreshCw,
  Package,
  ImageOff,
  Download,
  DollarSign,
  Zap,
  TrendingUp,
  TrendingDown,
  Minus,
  ShieldCheck,
  ShieldOff,
  Activity,
  BookOpen,
  RotateCcw,
  ChevronDown,
  ChevronRight,
} from "lucide-react";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = new Date(d);
  const now = new Date();
  const diffH = (now.getTime() - dt.getTime()) / 3_600_000;
  if (diffH < 1) return `${Math.round(diffH * 60)}m ago`;
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD}d ago`;
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function fmtDuration(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${(s / 3600).toFixed(1)}h`;
}

function credBadge(status: string, hasKey: boolean) {
  if (!hasKey)
    return (
      <Badge variant="outline" className="text-xs border-amber-300 text-amber-700 bg-amber-50">
        No Scraper
      </Badge>
    );
  if (status === "verified" || status === "ok")
    return (
      <Badge className="text-xs bg-emerald-100 text-emerald-800 border-emerald-200 hover:bg-emerald-100">
        <ShieldCheck className="w-3 h-3 mr-1" /> {status === "ok" ? "OK" : "Verified"}
      </Badge>
    );
  if (status === "untested")
    return (
      <Badge variant="outline" className="text-xs border-amber-300 text-amber-700 bg-amber-50">
        <ShieldOff className="w-3 h-3 mr-1" /> Untested
      </Badge>
    );
  if (status === "error")
    return (
      <Badge variant="destructive" className="text-xs">
        <ShieldOff className="w-3 h-3 mr-1" /> Error
      </Badge>
    );
  return (
    <Badge variant="outline" className="text-xs border-stone-300 text-stone-600">
      <ShieldOff className="w-3 h-3 mr-1" /> Missing
    </Badge>
  );
}

function syncStatusBadge(status: string | null | undefined) {
  if (!status) return <span className="text-stone-400 text-xs">Never</span>;
  if (status === "completed")
    return (
      <span className="flex items-center gap-1 text-emerald-700 text-xs font-medium">
        <CheckCircle className="w-3.5 h-3.5" /> Done
      </span>
    );
  if (status === "running")
    return (
      <span className="flex items-center gap-1 text-blue-700 text-xs font-medium animate-pulse">
        <Activity className="w-3.5 h-3.5" /> Running
      </span>
    );
  if (status === "error")
    return (
      <span className="flex items-center gap-1 text-red-700 text-xs font-medium">
        <AlertCircle className="w-3.5 h-3.5" /> Error
      </span>
    );
  return <span className="text-stone-500 text-xs capitalize">{status}</span>;
}

function changePctIcon(pct: number | null | undefined) {
  if (pct == null) return <Minus className="w-3 h-3 text-stone-400" />;
  if (pct > 0) return <TrendingUp className="w-3 h-3 text-red-500" />;
  if (pct < 0) return <TrendingDown className="w-3 h-3 text-emerald-600" />;
  return <Minus className="w-3 h-3 text-stone-400" />;
}

// ── stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  sub?: string;
  accent?: string;
  iconColor?: string;
}

function StatCard({
  icon,
  label,
  value,
  sub,
  accent = "bg-brand/10",
  iconColor = "text-brand",
}: StatCardProps) {
  return (
    <div className="bg-white border border-stone-200 rounded-xl p-4 flex items-start gap-3 shadow-sm">
      <div className={`mt-0.5 p-2 rounded-lg ${accent}`}>
        <span className={iconColor}>{icon}</span>
      </div>
      <div>
        <p className="text-2xl font-semibold font-serif text-stone-800">{value}</p>
        <p className="text-xs font-medium text-stone-600 mt-0.5">{label}</p>
        {sub && <p className="text-xs text-stone-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function SectionLabel({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-xs font-semibold text-stone-500 uppercase tracking-wide">{label}</span>
      <span className="text-xs text-stone-400">({count})</span>
    </div>
  );
}

function EmptyState({ icon, message }: { icon: React.ReactNode; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      {icon}
      <p className="text-sm text-stone-500 max-w-sm">{message}</p>
    </div>
  );
}

function SupplierRow({
  s,
  onToggle,
  toggling,
}: {
  s: SupplierHealth;
  onToggle: () => void;
  toggling: boolean;
}) {
  const syncOverdue =
    s.scraper_enabled &&
    s.sync_frequency_hours != null &&
    s.last_full_sync_at != null
      ? (Date.now() - new Date(s.last_full_sync_at as unknown as string).getTime()) / 3_600_000 >
        s.sync_frequency_hours * 1.5
      : false;

  return (
    <TableRow
      className={`hover:bg-stone-50 border-stone-100 ${
        s.last_sync_status === "error" ? "bg-red-50/40" : ""
      }`}
    >
      <TableCell className="font-medium text-sm text-stone-800">{s.name}</TableCell>
      <TableCell>{credBadge(s.credential_status, !!s.scraper_key)}</TableCell>
      <TableCell className="text-right text-sm text-stone-700">
        {s.product_count > 0 ? (
          s.product_count.toLocaleString()
        ) : (
          <span className="text-stone-400">0</span>
        )}
      </TableCell>
      <TableCell className="text-right text-sm">
        {s.missing_images > 0 ? (
          <span className="text-amber-700">{s.missing_images}</span>
        ) : (
          <span className="text-stone-300">0</span>
        )}
      </TableCell>
      <TableCell className="text-right text-sm">
        {s.missing_prices > 0 ? (
          <span className="text-red-600">{s.missing_prices}</span>
        ) : (
          <span className="text-stone-300">0</span>
        )}
      </TableCell>
      <TableCell>
        <span
          className={`text-xs ${
            syncOverdue ? "text-red-600 font-medium" : "text-stone-500"
          }`}
        >
          {s.last_full_sync_at ? (
            <>
              {fmtDate(s.last_full_sync_at as unknown as string)}
              {syncOverdue && " ⚠️"}
            </>
          ) : (
            <span className="text-stone-400">Never</span>
          )}
        </span>
      </TableCell>
      <TableCell>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="cursor-default">{syncStatusBadge(s.last_sync_status)}</div>
          </TooltipTrigger>
          {s.last_sync_status && (
            <TooltipContent className="text-xs max-w-xs">
              {s.last_sync_error ? (
                <p className="text-red-400">{s.last_sync_error}</p>
              ) : (
                <p>
                  +{s.last_sync_inserted ?? 0} new &nbsp;|&nbsp; ~
                  {s.last_sync_updated ?? 0} updated &nbsp;|&nbsp;
                  {s.last_sync_failed ?? 0} failed &nbsp;|&nbsp; Δ
                  {s.last_sync_price_changes ?? 0} prices
                </p>
              )}
            </TooltipContent>
          )}
        </Tooltip>
      </TableCell>
      <TableCell className="text-right text-xs text-stone-500">
        {s.sync_frequency_hours != null
          ? s.sync_frequency_hours >= 24
            ? `${s.sync_frequency_hours / 24}d`
            : `${s.sync_frequency_hours}h`
          : "—"}
      </TableCell>
      <TableCell>
        <button
          onClick={onToggle}
          disabled={toggling}
          title={s.scraper_enabled ? "Disable scraper" : "Enable scraper"}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
            s.scraper_enabled ? "bg-brand" : "bg-stone-200"
          } ${toggling ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
        >
          <span
            className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
              s.scraper_enabled ? "translate-x-4" : "translate-x-0.5"
            }`}
          />
        </button>
      </TableCell>
    </TableRow>
  );
}

// ── CategoryIndexCard ────────────────────────────────────────────────────────────────────

function CategoryIndexCard() {
  const [data, setData] = useState<CategoryIndexResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [rebuilding, setRebuilding] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get_category_index();
      const json = (await res.json()) as CategoryIndexResponse;
      setData(json);
    } catch {
      toast.error("Failed to load category index.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRebuild = async (sup: SupplierCategoryIndex) => {
    if (!confirm(`Clear the category index for ${sup.supplier_name}? The next scrape will do a full re-discovery.`)) return;
    setRebuilding(sup.supplier_id);
    try {
      await apiClient.rebuild_supplier_category_index({ supplierId: sup.supplier_id });
      toast.success(`Index cleared for ${sup.supplier_name}. Next scrape will rediscover all categories.`);
      await load();
    } catch {
      toast.error("Failed to rebuild index.");
    } finally {
      setRebuilding(null);
    }
  };

  const toggleExpand = (id: number) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  function fmtAge(dt: string | null | undefined): { label: string; stale: boolean } {
    if (!dt) return { label: "Never verified", stale: true };
    const d = new Date(dt);
    const diffDays = (Date.now() - d.getTime()) / 86_400_000;
    const stale = diffDays > 7;
    if (diffDays < 1) return { label: "Today", stale };
    if (diffDays < 2) return { label: "Yesterday", stale };
    return { label: `${Math.round(diffDays)}d ago`, stale };
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-brand" />
          <span className="text-sm font-semibold text-stone-700">Category Index Cache</span>
          <span className="text-xs text-stone-400">
            Scrapers use this to skip re-discovery on fast syncs
          </span>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={load}
          disabled={loading}
          className="border-stone-300 text-stone-600 hover:bg-white text-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
        </div>
      ) : !data || data.suppliers.length === 0 ? (
        <div className="bg-white border border-stone-200 rounded-xl p-8 text-center">
          <BookOpen className="w-8 h-8 text-stone-300 mx-auto mb-2" />
          <p className="text-stone-500 text-sm">No category index found.</p>
          <p className="text-stone-400 text-xs mt-1">
            Run a full scrape to build the index automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.suppliers.map((sup) => {
            const isExpanded = !!expanded[sup.supplier_id];
            const isRebuilding = rebuilding === sup.supplier_id;
            const age = fmtAge(sup.oldest_verified_at as unknown as string | null);
            const isEmpty = sup.total_categories === 0;

            return (
              <div
                key={sup.supplier_id}
                className="bg-white border border-stone-200 rounded-xl shadow-sm overflow-hidden"
              >
                {/* Header row */}
                <div className="flex items-center gap-4 px-5 py-3.5">
                  <button
                    onClick={() => toggleExpand(sup.supplier_id)}
                    className="flex items-center gap-2 flex-1 text-left group"
                  >
                    <span className="text-stone-400 group-hover:text-stone-600 transition-colors">
                      {isExpanded
                        ? <ChevronDown className="w-4 h-4" />
                        : <ChevronRight className="w-4 h-4" />}
                    </span>
                    <span className="text-sm font-semibold text-stone-800">{sup.supplier_name}</span>
                    <span className="text-xs text-stone-400 font-mono bg-stone-50 border border-stone-200 rounded px-1.5 py-0.5">
                      {sup.scraper_key}
                    </span>
                  </button>

                  {/* Stats */}
                  <div className="flex items-center gap-5 text-xs shrink-0">
                    {isEmpty ? (
                      <span className="text-amber-600 flex items-center gap-1">
                        <AlertCircle className="w-3.5 h-3.5" /> No index yet
                      </span>
                    ) : (
                      <>
                        <div className="text-center">
                          <p className="font-semibold text-stone-800">{sup.active_categories}</p>
                          <p className="text-stone-400">categories</p>
                        </div>
                        <div className="text-center">
                          <p className="font-semibold text-stone-800">
                            {sup.total_cached_products.toLocaleString()}
                          </p>
                          <p className="text-stone-400">cached products</p>
                        </div>
                        <div className="text-center">
                          <p
                            className={`font-semibold ${
                              age.stale ? "text-amber-600" : "text-emerald-700"
                            }`}
                          >
                            {age.label}
                          </p>
                          <p className="text-stone-400">last verified</p>
                        </div>
                      </>
                    )}

                    <Button
                      size="sm"
                      variant="outline"
                      disabled={isRebuilding}
                      onClick={() => handleRebuild(sup)}
                      className="border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300 text-xs ml-2"
                    >
                      {isRebuilding ? (
                        <><RefreshCw className="w-3 h-3 mr-1.5 animate-spin" /> Clearing…</>
                      ) : (
                        <><RotateCcw className="w-3 h-3 mr-1.5" /> Rebuild Index</>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Expanded category table */}
                {isExpanded && !isEmpty && (
                  <div className="border-t border-stone-100">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-stone-50 border-stone-100">
                          <TableHead className="text-xs font-semibold text-stone-500 pl-10">Category</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-500 text-right">Cached Products</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-500">Last Verified</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-500">Status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sup.categories.map((cat) => {
                          const catAge = fmtAge(cat.last_verified_at as unknown as string | null);
                          return (
                            <TableRow key={cat.id} className="border-stone-100 hover:bg-stone-50">
                              <TableCell className="text-xs text-stone-700 pl-10 font-medium">
                                {cat.category_name}
                                <span className="ml-2 text-stone-400 font-mono text-[10px]">
                                  {cat.category_slug_or_url}
                                </span>
                              </TableCell>
                              <TableCell className="text-xs text-stone-600 text-right">
                                {cat.product_count?.toLocaleString() ?? "—"}
                              </TableCell>
                              <TableCell className="text-xs text-stone-500">
                                {catAge.label}
                              </TableCell>
                              <TableCell>
                                {cat.is_active ? (
                                  <span className="flex items-center gap-1 text-emerald-700 text-xs">
                                    <CheckCircle className="w-3 h-3" /> Active
                                  </span>
                                ) : (
                                  <span className="flex items-center gap-1 text-stone-400 text-xs">
                                    <Minus className="w-3 h-3" /> Inactive
                                  </span>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}

                {isExpanded && isEmpty && (
                  <div className="border-t border-stone-100 px-10 py-4 text-xs text-stone-400">
                    No categories cached yet. Run a full scrape to populate the index.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Legend */}
      <div className="text-xs text-stone-400 flex items-center gap-4 pt-1">
        <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3 text-emerald-600" /> Fresh (&lt;7 days) — scraper will use cache</span>
        <span className="flex items-center gap-1"><AlertCircle className="w-3 h-3 text-amber-500" /> Stale (&gt;7 days) — scraper will re-discover</span>
        <span className="flex items-center gap-1"><RotateCcw className="w-3 h-3 text-red-500" /> Rebuild clears index for full re-discovery on next scrape</span>
      </div>
    </div>
  );
}

// ── BackfillCard ───────────────────────────────────────────────────────────────────────────
interface BackfillStatus {
  status: string;
  total: number;
  done: number;
  stored: number;
  skipped: number;
  failed: number;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

function BackfillCard() {
  const [bf, setBf] = useState<BackfillStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiClient.get_backfill_status();
      const json = (await res.json()) as BackfillStatus;
      setBf(json);
      if (json.status !== "running" && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (bf?.status === "running" && !pollRef.current) {
      pollRef.current = setInterval(fetchStatus, 3000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [bf?.status, fetchStatus]);

  const handleStart = async () => {
    setStarting(true);
    try {
      const res = await apiClient.start_backfill_images();
      const json = (await res.json()) as BackfillStatus;
      setBf(json);
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchStatus, 3000);
      }
      toast.success("Image download started — this may take several minutes.");
    } catch {
      toast.error("Failed to start image backfill.");
    } finally {
      setStarting(false);
    }
  };

  const pct = bf && bf.total > 0 ? Math.round((bf.done / bf.total) * 100) : 0;
  const isRunning = bf?.status === "running";
  const isDone = bf?.status === "done";
  const isFailed = bf?.status === "failed";

  return (
    <div className="mx-8 mb-5">
      <div className="bg-white border border-stone-200 rounded-xl shadow-sm px-5 py-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-50">
              <Download className="w-4 h-4 text-amber-700" />
            </div>
            <div>
              <p className="text-sm font-semibold text-stone-800">Product Image Library</p>
              <p className="text-xs text-stone-500">
                {!bf || bf.status === "idle"
                  ? "Download all product images to permanent storage so they load reliably in Catalog Search."
                  : isRunning
                  ? `Downloading images… ${bf.done.toLocaleString()} / ${bf.total.toLocaleString()}`
                  : isDone
                  ? `${bf.stored.toLocaleString()} images stored · ${bf.skipped.toLocaleString()} already stored · ${bf.failed.toLocaleString()} failed`
                  : isFailed
                  ? `Failed: ${bf.error || "unknown error"}`
                  : null}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {isDone && (
              <span className="flex items-center gap-1 text-emerald-700 text-xs font-medium">
                <CheckCircle className="w-3.5 h-3.5" /> Complete
              </span>
            )}
            {isFailed && (
              <span className="flex items-center gap-1 text-red-600 text-xs font-medium">
                <AlertCircle className="w-3.5 h-3.5" /> Failed
              </span>
            )}
            <Button
              size="sm"
              variant={isDone ? "outline" : "default"}
              disabled={isRunning || starting}
              onClick={handleStart}
              className={
                isDone
                  ? "border-stone-300 text-stone-600 hover:bg-white text-xs"
                  : "bg-brand hover:bg-brand-hover text-white text-xs"
              }
            >
              {isRunning || starting ? (
                <><RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />{isRunning ? "Running…" : "Starting…"}</>
              ) : isDone ? (
                <><RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Re-run</>
              ) : (
                <><Download className="w-3.5 h-3.5 mr-1.5" /> Download All Images</>
              )}
            </Button>
          </div>
        </div>
        {isRunning && bf && bf.total > 0 && (
          <div className="space-y-1">
            <Progress value={pct} className="h-1.5 bg-stone-100" />
            <div className="flex justify-between text-[10px] text-stone-400">
              <span>{pct}% complete</span>
              <span>{bf.stored.toLocaleString()} stored · {bf.failed.toLocaleString()} failed</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── main page ───────────────────────────────────────────────────────────────────────────

export default function AdminDashboard() {
  const [data, setData] = useState<AdminDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await apiClient.get_admin_dashboard();
      const json = (await res.json()) as AdminDashboardResponse;
      setData(json);
    } catch (e) {
      console.error("Failed to load admin dashboard", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleScraper = async (s: SupplierHealth) => {
    setTogglingId(s.id);
    try {
      await apiClient.toggle_scraper({ supplierId: s.id, enabled: !s.scraper_enabled });
      await load(true);
    } finally {
      setTogglingId(null);
    }
  };

  if (loading) {
    return (
      <div className="p-8 space-y-4" style={{ background: "rgb(var(--ll-page))", minHeight: "100vh" }}>
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-96 rounded-xl" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-8 text-stone-500">
        Failed to load dashboard.{" "}
        <button onClick={() => load()} className="underline">
          Retry
        </button>
      </div>
    );
  }

  const { summary, supplier_health, recent_syncs, recent_price_changes } = data;
  const scrapedSuppliers = supplier_health.filter((s) => !!s.scraper_key);
  const manualSuppliers = supplier_health.filter((s) => !s.scraper_key);

  return (
    <TooltipProvider>
      <div className="min-h-screen" style={{ background: "rgb(var(--ll-page))" }}>
        {/* ── Header ── */}
        <div className="px-8 pt-8 pb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-serif font-semibold text-brand">Sync Operations</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              Supplier health, catalog sync status, and price change log
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(true)}
            disabled={refreshing}
            className="border-stone-300 text-stone-600 hover:bg-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {/* ── Summary stat cards ── */}
        <div className="px-8 pb-6 grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard
            icon={<Package className="w-4 h-4" />}
            label="Total Products"
            value={summary.total_products.toLocaleString()}
            sub={`across ${summary.total_suppliers} suppliers`}
          />
          <StatCard
            icon={<ShieldCheck className="w-4 h-4" />}
            label="With Credentials"
            value={summary.suppliers_with_credentials}
            sub={`${summary.suppliers_with_scraper} have scrapers`}
          />
          <StatCard
            icon={<Zap className="w-4 h-4" />}
            label="Synced This Week"
            value={summary.suppliers_synced_this_week}
            accent="bg-amber-50"
            iconColor="text-amber-700"
          />
          <StatCard
            icon={<ImageOff className="w-4 h-4" />}
            label="Missing Images"
            value={summary.products_missing_images.toLocaleString()}
            accent="bg-stone-100"
            iconColor="text-stone-500"
          />
          <StatCard
            icon={<DollarSign className="w-4 h-4" />}
            label="Price Δ This Week"
            value={summary.price_changes_this_week}
            sub={
              summary.failed_syncs_this_week > 0
                ? `${summary.failed_syncs_this_week} failed syncs`
                : "No failed syncs"
            }
            accent="bg-red-50"
            iconColor="text-red-600"
          />
        </div>

        {/* ── Image Backfill panel ── */}
        <BackfillCard />

        {/* ── Tabs ── */}
        <div className="px-8">
          <Tabs defaultValue="suppliers">
            <TabsList className="bg-white border border-stone-200 rounded-lg mb-4">
              <TabsTrigger value="suppliers">
                Supplier Health ({supplier_health.length})
              </TabsTrigger>
              <TabsTrigger value="categories">Category Index</TabsTrigger>
              <TabsTrigger value="syncs">Sync Log ({recent_syncs.length})</TabsTrigger>
              <TabsTrigger value="prices">
                Price Changes ({recent_price_changes.length})
              </TabsTrigger>
            </TabsList>

            {/* ── Category Index ── */}
            <TabsContent value="categories">
              <CategoryIndexCard />
            </TabsContent>

            {/* ── Supplier Health ── */}
            <TabsContent value="suppliers" className="space-y-6">              {scrapedSuppliers.length > 0 && (
                <div>
                  <SectionLabel label="Automated Scrapers" count={scrapedSuppliers.length} />
                  <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-stone-50 border-stone-200">
                          <TableHead className="text-xs font-semibold text-stone-600 w-40">Supplier</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600">Credentials</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600 text-right">Products</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600 text-right">No Image</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600 text-right">No Price</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600">Last Full Sync</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600">Last Result</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600 text-right">Freq</TableHead>
                          <TableHead className="text-xs font-semibold text-stone-600">Auto-Sync</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {scrapedSuppliers.map((s) => (
                          <SupplierRow
                            key={s.id}
                            s={s}
                            onToggle={() => toggleScraper(s)}
                            toggling={togglingId === s.id}
                          />
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              <div>
                <SectionLabel label="Manual / No Scraper" count={manualSuppliers.length} />
                <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-stone-50 border-stone-200">
                        <TableHead className="text-xs font-semibold text-stone-600 w-64">Supplier</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Products</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">No Image</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">No Price</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Last Price Sync</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {manualSuppliers.map((s) => (
                        <TableRow key={s.id} className="hover:bg-stone-50 border-stone-100">
                          <TableCell className="font-medium text-sm text-stone-800">{s.name}</TableCell>
                          <TableCell className="text-right text-sm text-stone-700">
                            {s.product_count > 0 ? (
                              s.product_count.toLocaleString()
                            ) : (
                              <span className="text-stone-400">0</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-sm">
                            {s.missing_images > 0 ? (
                              <span className="text-amber-700">{s.missing_images}</span>
                            ) : (
                              <span className="text-stone-300">0</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-sm">
                            {s.missing_prices > 0 ? (
                              <span className="text-red-600">{s.missing_prices}</span>
                            ) : (
                              <span className="text-stone-300">0</span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-stone-500">
                            {s.last_price_synced_at ? (
                              fmtDate(s.last_price_synced_at as unknown as string)
                            ) : (
                              <span className="text-stone-400">Never</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </TabsContent>

            {/* ── Sync Log ── */}
            <TabsContent value="syncs">
              <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                {recent_syncs.length === 0 ? (
                  <EmptyState
                    icon={<Clock className="w-8 h-8 text-stone-300" />}
                    message="No syncs recorded yet. Run your first catalog scrape from the Suppliers page."
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-stone-50 border-stone-200">
                        <TableHead className="text-xs font-semibold text-stone-600">Supplier</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Type</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Status</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Started</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Duration</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Found</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">New</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Updated</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Failed</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Δ Price</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Error</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {recent_syncs.map((log: SyncLogEntry) => (
                        <TableRow
                          key={log.id}
                          className={`hover:bg-stone-50 border-stone-100 ${
                            log.status === "error" ? "bg-red-50/50" : ""
                          }`}
                        >
                          <TableCell className="font-medium text-sm text-stone-800">
                            {log.supplier_name}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs capitalize border-stone-200">
                              {log.sync_type}
                            </Badge>
                          </TableCell>
                          <TableCell>{syncStatusBadge(log.status)}</TableCell>
                          <TableCell className="text-xs text-stone-500">
                            {fmtDate(log.started_at as unknown as string)}
                          </TableCell>
                          <TableCell className="text-xs text-stone-600">
                            {fmtDuration(log.duration_s)}
                          </TableCell>
                          <TableCell className="text-right text-sm text-stone-600">
                            {log.products_found ?? "—"}
                          </TableCell>
                          <TableCell className="text-right text-sm text-emerald-700">
                            {log.products_inserted ?? "—"}
                          </TableCell>
                          <TableCell className="text-right text-sm text-blue-700">
                            {log.products_updated ?? "—"}
                          </TableCell>
                          <TableCell className="text-right text-sm">
                            {(log.products_failed ?? 0) > 0 ? (
                              <span className="text-red-600">{log.products_failed}</span>
                            ) : (
                              <span className="text-stone-300">0</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-sm text-amber-700">
                            {log.price_changes ?? "—"}
                          </TableCell>
                          <TableCell className="text-xs max-w-[180px]">
                            {log.error_message ? (
                              <Tooltip>
                                <TooltipTrigger>
                                  <span className="text-red-600 truncate block cursor-help">
                                    {log.error_message.slice(0, 40)}…
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent className="max-w-sm text-xs">
                                  {log.error_message}
                                </TooltipContent>
                              </Tooltip>
                            ) : (
                              <span className="text-stone-300">—</span>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </TabsContent>

            {/* ── Price Changes ── */}
            <TabsContent value="prices">
              <div className="bg-white border border-stone-200 rounded-xl overflow-hidden shadow-sm">
                {recent_price_changes.length === 0 ? (
                  <EmptyState
                    icon={<DollarSign className="w-8 h-8 text-stone-300" />}
                    message="No price changes recorded in the last 7 days."
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-stone-50 border-stone-200">
                        <TableHead className="text-xs font-semibold text-stone-600">Product</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Supplier</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Old</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">New</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600 text-right">Change</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">Source</TableHead>
                        <TableHead className="text-xs font-semibold text-stone-600">When</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {recent_price_changes.map((pc: PriceChangeEntry) => (
                        <TableRow key={pc.id} className="hover:bg-stone-50 border-stone-100">
                          <TableCell className="font-medium text-sm text-stone-800 max-w-[220px] truncate">
                            {pc.product_name}
                          </TableCell>
                          <TableCell className="text-sm text-stone-600">{pc.supplier_name}</TableCell>
                          <TableCell className="text-right text-sm text-stone-500">
                            {pc.old_price != null ? `$${pc.old_price.toFixed(2)}` : "—"}
                          </TableCell>
                          <TableCell className="text-right text-sm font-medium text-stone-800">
                            {pc.new_price != null ? `$${pc.new_price.toFixed(2)}` : "—"}
                          </TableCell>
                          <TableCell className="text-right">
                            <span
                              className={`flex items-center justify-end gap-1 text-sm font-medium ${
                                pc.change_pct == null
                                  ? "text-stone-400"
                                  : pc.change_pct > 0
                                  ? "text-red-600"
                                  : pc.change_pct < 0
                                  ? "text-emerald-700"
                                  : "text-stone-500"
                              }`}
                            >
                              {changePctIcon(pc.change_pct)}
                              {pc.change_pct != null
                                ? `${pc.change_pct > 0 ? "+" : ""}${pc.change_pct}%`
                                : "—"}
                            </span>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs capitalize border-stone-200">
                              {pc.source}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs text-stone-500">
                            {fmtDate(pc.changed_at as unknown as string)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <div className="h-8" />
      </div>
    </TooltipProvider>
  );
}
