/**
 * The home screen's app icons: what each icon is,
 * where it goes and in what order. Pure data + helpers so tests can import it.
 *
 * Order follows how often each page is used during install season: the
 * schedule and client work first, the catalog / design tools after.
 */
import type { LucideIcon } from "components/icons";
import {
  Briefcase,
  Building2,
  Calculator,
  CalendarDays,
  ClipboardCheck,
  ClipboardList,
  DollarSign,
  Heart,
  ListChecks,
  MapPinned,
  MessageSquare,
  MessageSquareText,
  Scale,
  Search,
  Settings,
  Shapes,
  ShoppingCart,
  Store,
  TreePine,
  TrendingUp,
  Users,
} from "components/icons";
import type { Me } from "utils/me";

export type TileGroup = "season" | "catalog" | "more";

export interface HomeTile {
  id: string;
  label: string;
  path: string;
  icon: LucideIcon;
  group: TileGroup;
  /** Tile fill, a brand-family colour; the glyph is white on it. */
  tone: string;
  adminOnly?: boolean;
}

/** Brand-family fills: greens for season work, warm tones for the rest. */
const T = {
  pine: "#1f3d2b",
  brand: "#2d5a33",
  moss: "#4f7a3a",
  sage: "#6b8f71",
  teal: "#2f6b62",
  gold: "#b9892b",
  clay: "#a5523a",
  berry: "#8c3b4a",
  bark: "#6b5440",
  slate: "#4b5a55",
};

export const HOME_TILES: HomeTile[] = [
  // Install season, most used first.
  { id: "schedule", label: "Schedule", path: "/install-schedule", icon: TreePine, group: "season", tone: T.pine },
  { id: "clients", label: "Clients", path: "/clients", icon: Store, group: "season", tone: T.brand },
  { id: "roster", label: "Roster", path: "/install-roster", icon: Users, group: "season", tone: T.teal },
  { id: "staffing", label: "Staffing", path: "/install-staffing", icon: Briefcase, group: "season", tone: T.moss },
  // Send mass text lives on the Roster view of the schedule.
  { id: "text", label: "Text crew", path: "/install-roster", icon: MessageSquareText, group: "season", tone: T.sage },
  { id: "quotes", label: "Quotes", path: "/quote-calculator", icon: DollarSign, group: "season", tone: T.gold, adminOnly: true },
  { id: "comments", label: "Comments", path: "/comments", icon: MessageSquare, group: "season", tone: T.clay },
  { id: "forms", label: "Forms", path: "/forms/product-request/responses", icon: ListChecks, group: "season", tone: T.berry },
  { id: "calendar", label: "Calendar", path: "/install-calendar", icon: CalendarDays, group: "season", tone: T.brand },
  { id: "shifts", label: "Crew shifts", path: "/shifts", icon: MapPinned, group: "season", tone: T.teal },
  { id: "profit", label: "Day profit", path: "/crew-profit", icon: TrendingUp, group: "season", tone: T.gold, adminOnly: true },
  { id: "budgets", label: "Job budgets", path: "/job-budgets", icon: Scale, group: "season", tone: T.bark, adminOnly: true },
  // Catalog and design tools.
  { id: "search", label: "Search", path: "/search", icon: Search, group: "catalog", tone: T.slate },
  { id: "designs", label: "Designs", path: "/designs", icon: Shapes, group: "catalog", tone: T.moss },
  { id: "orders", label: "Orders", path: "/orders", icon: ShoppingCart, group: "catalog", tone: T.bark },
  { id: "ornaments", label: "Ornaments", path: "/ornament-calculator", icon: Calculator, group: "catalog", tone: T.berry },
  { id: "suppliers", label: "Suppliers", path: "/suppliers", icon: Building2, group: "catalog", tone: T.slate },
  { id: "trees", label: "Tree counts", path: "/tree-counts", icon: ClipboardCheck, group: "catalog", tone: T.sage },
  { id: "jobs", label: "Jobs", path: "/jobs", icon: ClipboardList, group: "catalog", tone: T.clay },
  // Everything else.
  { id: "favorites", label: "Favorites", path: "/favorites", icon: Heart, group: "more", tone: T.clay },
  { id: "settings", label: "Settings", path: "/settings", icon: Settings, group: "more", tone: T.slate },
];

export const GROUP_LABELS: Record<TileGroup, string> = {
  season: "Install season",
  catalog: "Catalog & design",
  more: "More",
};

/** Same visibility rules as the sidebar: admin-only tiles for admins, and a
 *  restricted login only sees the pages it may open. */
export function visibleTiles(me: Pick<Me, "isAdmin" | "pages"> | null, tiles: HomeTile[] = HOME_TILES): HomeTile[] {
  return tiles.filter((t) => {
    if (t.adminOnly && !me?.isAdmin) return false;
    if (me?.pages && !me.pages.some((p) => t.path === p || t.path.startsWith(p + "/"))) return false;
    return true;
  });
}

/** Comments still open (not checked off), for the Comments badge. */
export function openCommentCount(rows: unknown): number {
  if (!Array.isArray(rows)) return 0;
  return rows.filter((r) => r && typeof r === "object" && (r as { status?: string }).status !== "done").length;
}

// ---- The "Today" strip: GET /api/lead/today-summary ----------------------

/** Today's (or the next) install day, as counts only. */
export interface TodaySummary {
  date: string; // YYYY-MM-DD
  isToday: boolean;
  crews: Array<{ label: string; jobs: number; people: number }>;
  jobs: number;
  people: number;
}
