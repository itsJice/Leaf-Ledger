import * as React from "react";

/**
 * The Leaf & Ledger icon set: the 117 icons the app uses, redrawn as our own
 * shapes (rounded geometry, botanical details) but with the exact API the
 * Lucide components had, so a page keeps `<Search size={15} strokeWidth={1.8} />`
 * and only its import line changes. Defaults match Lucide (24px, 2px stroke,
 * `currentColor`), so every icon sits at the size it always did.
 *
 * Source of truth for the drawings: the "Leaf & Ledger icon sheet" (2026-09-24).
 * Regenerate this file from it rather than editing paths by hand.
 */
export type IconProps = React.SVGProps<SVGSVGElement> & {
  size?: number | string;
  strokeWidth?: number | string;
  absoluteStrokeWidth?: boolean;
};
export type LucideIcon = React.ForwardRefExoticComponent<IconProps & React.RefAttributes<SVGSVGElement>>;

function icon(name: string, kebab: string, body: string): LucideIcon {
  const C = React.forwardRef<SVGSVGElement, IconProps>(function Icon(
    { size = 24, strokeWidth = 2, absoluteStrokeWidth, className, ...rest },
    ref,
  ) {
    const sw = absoluteStrokeWidth ? (Number(strokeWidth) * 24) / Number(size) : strokeWidth;
    return (
      <svg
        ref={ref}
        xmlns="http://www.w3.org/2000/svg"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={sw}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={["lucide", `lucide-${kebab}`, className].filter(Boolean).join(" ")}
        aria-hidden={rest["aria-label"] ? undefined : true}
        {...rest}
        dangerouslySetInnerHTML={{ __html: body }}
      />
    );
  });
  C.displayName = name;
  return C;
}

export const Activity = icon("Activity", "activity", `<path d="M3 12h4l3-8 4 16 3-8h4"/>`);
export const AlertCircle = icon("AlertCircle", "alert-circle", `<circle cx="12" cy="12" r="9"/><path d="M12 7v6"/><circle cx="12" cy="17" r="1.2" fill="currentColor" stroke="none"/>`);
export const AlertTriangle = icon("AlertTriangle", "alert-triangle", `<path d="M10 4a2.3 2.3 0 0 1 4 0l8 14a2 2 0 0 1-2 3H4a2 2 0 0 1-2-3Z"/><path d="M12 9v4"/><circle cx="12" cy="17" r="1.2" fill="currentColor" stroke="none"/>`);
export const ArrowLeft = icon("ArrowLeft", "arrow-left", `<g transform="rotate(180 12 12)"><path d="M4 12h16m-6-6 6 6-6 6"/></g>`);
export const ArrowRight = icon("ArrowRight", "arrow-right", `<g transform="rotate(0 12 12)"><path d="M4 12h16m-6-6 6 6-6 6"/></g>`);
export const ArrowUpRight = icon("ArrowUpRight", "arrow-up-right", `<g transform="rotate(-45 12 12)"><path d="M4 12h16m-6-6 6 6-6 6"/></g>`);
export const BookOpen = icon("BookOpen", "book-open", `<path d="M12 6C9 3 5 3 3 4v15c3-1 6-1 9 2 3-3 6-3 9-2V4c-2-1-6-1-9 2ZM12 6v15M6 8l3 1M15 9l3-1"/>`);
export const Briefcase = icon("Briefcase", "briefcase", `<rect x="3" y="7" width="18" height="14" rx="3.5"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12c5 4 13 4 18 0M12 13v3"/>`);
export const Building2 = icon("Building2", "building2", `<rect x="7" y="3" width="10" height="18" rx="3"/><path d="M7 10H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2h-2M11 7h2M11 11h2M11 15h2M12 19v2"/>`);
export const Calculator = icon("Calculator", "calculator", `<rect x="4" y="2.5" width="16" height="19" rx="4"/><path d="M8 7h8M16 13v4"/><circle cx="8" cy="12" r="1.1" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none"/><circle cx="8" cy="17" r="1.1" fill="currentColor" stroke="none"/><circle cx="12" cy="17" r="1.1" fill="currentColor" stroke="none"/>`);
export const CalendarDays = icon("CalendarDays", "calendar-days", `<rect x="3" y="5" width="18" height="16" rx="3.5"/><path d="M8 3v4M16 3v4M3 10h18"/><circle cx="8" cy="14" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="14" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="14" r="1" fill="currentColor" stroke="none"/><circle cx="8" cy="18" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="18" r="1" fill="currentColor" stroke="none"/>`);
export const Camera = icon("Camera", "camera", `<path d="M8 6 9.5 3h5L16 6h2a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3Z"/><circle cx="12" cy="13" r="4"/>`);
export const Check = icon("Check", "check", `<path d="m4 12 5 5L20 6"/>`);
export const CheckCircle = icon("CheckCircle", "check-circle", `<path d="M21 12a9 9 0 1 1-7-8.8M9 10l4 4 8-9"/>`);
export const CheckCircle2 = icon("CheckCircle2", "check-circle2", `<circle cx="12" cy="12" r="9"/><path d="m7.5 12 3 3 6-6"/>`);
export const ChevronDown = icon("ChevronDown", "chevron-down", `<g transform="rotate(90 12 12)"><path d="m9 5 7 7-7 7"/></g>`);
export const ChevronLeft = icon("ChevronLeft", "chevron-left", `<g transform="rotate(180 12 12)"><path d="m9 5 7 7-7 7"/></g>`);
export const ChevronRight = icon("ChevronRight", "chevron-right", `<g transform="rotate(0 12 12)"><path d="m9 5 7 7-7 7"/></g>`);
export const ChevronUp = icon("ChevronUp", "chevron-up", `<g transform="rotate(270 12 12)"><path d="m9 5 7 7-7 7"/></g>`);
export const Circle = icon("Circle", "circle", `<circle cx="12" cy="12" r="9"/>`);
export const CircleDashed = icon("CircleDashed", "circle-dashed", `<g transform="rotate(0 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(45 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(90 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(135 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(180 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(225 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(270 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g><g transform="rotate(315 12 12)"><path d="M10 3c4-1 6 1 5 4-3 0-5-1-5-4Z" fill="currentColor" stroke="none"/></g>`);
export const ClipboardCheck = icon("ClipboardCheck", "clipboard-check", `<path d="M8 5H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V8a3 3 0 0 0-3-3h-1"/><rect x="8" y="2.5" width="8" height="5" rx="2.5"/><path d="m8 14 3 3 5-6"/>`);
export const ClipboardList = icon("ClipboardList", "clipboard-list", `<path d="M8 5H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V8a3 3 0 0 0-3-3h-1"/><rect x="8" y="2.5" width="8" height="5" rx="2.5"/><path d="M11 12h5M11 17h5"/><circle cx="7.5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="7.5" cy="17" r="1" fill="currentColor" stroke="none"/>`);
export const Clock = icon("Clock", "clock", `<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/>`);
export const Copy = icon("Copy", "copy", `<rect x="8" y="8" width="13" height="13" rx="3.5"/><path d="M16 4V3H6a3 3 0 0 0-3 3v10h1"/>`);
export const Database = icon("Database", "database", `<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 4 16 4 16 0V6M4 12c0 4 16 4 16 0"/>`);
export const DollarSign = icon("DollarSign", "dollar-sign", `<path d="M17 6c-1-2-9-3-9 2 0 5 9 3 9 8 0 5-8 4-11 2M12 2v20"/>`);
export const Download = icon("Download", "download", `<path d="M3 15v3a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-3M12 3v13m-5-5 5 5 5-5"/>`);
export const Eraser = icon("Eraser", "eraser", `<path d="m4 12 9-9a2 2 0 0 1 3 0l5 5a2 2 0 0 1 0 3L11 21H8l-4-4a3 3 0 0 1 0-5ZM8 8l8 8M11 21h10"/>`);
export const ExternalLink = icon("ExternalLink", "external-link", `<path d="M10 4H7a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-3M14 3h7v7M21 3 11 13"/>`);
export const Eye = icon("Eye", "eye", `<path d="M2 12c5-10 15-10 20 0-5 10-15 10-20 0Z"/><circle cx="12" cy="12" r="3"/>`);
export const EyeOff = icon("EyeOff", "eye-off", `<path d="M9 5c5-2 10 1 13 7l-2 3M16 18C10 21 5 18 2 12l3-4M3 3l18 18"/>`);
export const FileSpreadsheet = icon("FileSpreadsheet", "file-spreadsheet", `<path d="M14 3H7a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V9l-6-6Z"/><path d="M14 3v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8v5H8ZM12 13v5"/>`);
export const FileText = icon("FileText", "file-text", `<path d="M14 3H7a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V9l-6-6Z"/><path d="M14 3v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8M8 17h5"/>`);
export const FileType = icon("FileType", "file-type", `<path d="M14 3H7a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V9l-6-6Z"/><path d="M14 3v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8M12 13v5"/>`);
export const FileUp = icon("FileUp", "file-up", `<path d="M14 3H7a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V9l-6-6Z"/><path d="M14 3v4a2 2 0 0 0 2 2h4"/><path d="M12 18v-6m-3 3 3-3 3 3"/>`);
export const Flower2 = icon("Flower2", "flower2", `<path d="M12 7c-6-8-12 1-5 5-8 6 1 12 5 5 6 8 12-1 5-5 8-6-1-12-5-5Z"/><circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none"/>`);
export const FolderOpen = icon("FolderOpen", "folder-open", `<path d="M3 18V6a3 3 0 0 1 3-3h4l3 3h5a3 3 0 0 1 3 3M3 20l3-9h16l-3 9a2 2 0 0 1-2 1H5a2 2 0 0 1-2-1Z"/>`);
export const FolderPlus = icon("FolderPlus", "folder-plus", `<path d="M3 8V6a3 3 0 0 1 3-3h4l3 3h5a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V8Z"/><path d="M8 13h8M12 9v8"/>`);
export const Grid3X3 = icon("Grid3X3", "grid3-x3", `<rect x="3" y="3" width="18" height="18" rx="4"/><path d="M9 4v16M15 4v16M4 9h16M4 15h16"/>`);
export const GripVertical = icon("GripVertical", "grip-vertical", `<circle cx="9" cy="5" r="1.5" fill="currentColor" stroke="none"/><circle cx="9" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="9" cy="19" r="1.5" fill="currentColor" stroke="none"/><circle cx="15" cy="5" r="1.5" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="15" cy="19" r="1.5" fill="currentColor" stroke="none"/>`);
export const Heart = icon("Heart", "heart", `<path d="M12 21C9 19 3 14 3 8a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 6-6 11-9 13Z"/>`);
export const HelpCircle = icon("HelpCircle", "help-circle", `<circle cx="12" cy="12" r="9"/><path d="M9 9c0-4 7-4 7 0 0 2-4 2-4 5"/><circle cx="12" cy="17.5" r="1" fill="currentColor" stroke="none"/>`);
export const Image = icon("Image", "image", `<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none"/><path d="M4 18l5-5 4 3 4-6 4 5"/>`);
export const ImageOff = icon("ImageOff", "image-off", `<path d="M9 3h8a4 4 0 0 1 4 4v7M18 21H7a4 4 0 0 1-4-4V7M4 18l5-5M3 3l18 18"/>`);
export const ImagePlus = icon("ImagePlus", "image-plus", `<path d="M13 3H7a4 4 0 0 0-4 4v10a4 4 0 0 0 4 4h10a4 4 0 0 0 4-4v-5M16 5h6M19 2v6M4 18l5-5 4 3 4-4 4 5"/><circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none"/>`);
export const KeyRound = icon("KeyRound", "key-round", `<circle cx="8" cy="8" r="5"/><path d="m12 12 9 9M16 16l3-3M19 19l3-3"/>`);
export const Layers = icon("Layers", "layers", `<path d="m3 7 9-4 9 4-9 4ZM3 12l9 4 9-4M3 17l9 4 9-4"/>`);
export const LayoutGrid = icon("LayoutGrid", "layout-grid", `<rect x="3" y="3" width="7" height="7" rx="2.7"/><path d="M14 10V7a4 4 0 0 1 4-4h3v3a4 4 0 0 1-4 4Z" fill="currentColor" stroke="none"/><rect x="3" y="14" width="7" height="7" rx="2.7"/><rect x="14" y="14" width="7" height="7" rx="2.7"/>`);
export const Leaf = icon("Leaf", "leaf", `<path d="M11 13C4 14 2 9 2 5c5 0 9 2 9 8ZM13 12C12 5 16 2 22 2c0 6-3 11-9 10Z" fill="currentColor" stroke="none"/><path d="M12 21v-6"/>`);
export const Link2 = icon("Link2", "link2", `<g transform="translate(1 0) scale(.92 1)"><path d="m9 15 6-6M8 16l-2 2a3 3 0 0 1-4-4l5-5a3 3 0 0 1 4 0M16 8l2-2a3 3 0 0 1 4 4l-5 5a3 3 0 0 1-4 0"/></g>`);
export const List = icon("List", "list", `<path d="M9 5h12M9 12h12M9 19h12"/><circle cx="3" cy="5" r="1.3" fill="currentColor" stroke="none"/><circle cx="3" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="3" cy="19" r="1.3" fill="currentColor" stroke="none"/>`);
export const ListChecks = icon("ListChecks", "list-checks", `<path d="m3 5 2 2 3-4M12 5h9m-18 9 2 2 3-4M12 14h9M12 20h9"/>`);
export const Loader2 = icon("Loader2", "loader2", `<path d="M21 12a9 9 0 1 1-9-9"/>`);
export const Lock = icon("Lock", "lock", `<rect x="4" y="10" width="16" height="11" rx="3.5"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 15v2"/>`);
export const LogIn = icon("LogIn", "log-in", `<path d="M14 3h3a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3h-3M3 12h11m-4-4 4 4-4 4"/>`);
export const LogOut = icon("LogOut", "log-out", `<path d="M10 3H7a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h3M10 12h11m-4-4 4 4-4 4"/>`);
export const Mail = icon("Mail", "mail", `<rect x="3" y="5" width="18" height="15" rx="4"/><path d="m4 7 8 6 8-6"/>`);
export const MapPin = icon("MapPin", "map-pin", `<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>`);
export const MapPinned = icon("MapPinned", "map-pinned", `<path d="m3 8 5-2 8 3 5-2v13l-5 2-8-3-5 2ZM8 11v8M16 14v8"/><path d="M16 6c0 3-4 6-4 6S8 9 8 6a4 4 0 0 1 8 0Z"/><circle cx="12" cy="6" r="1" fill="currentColor" stroke="none"/>`);
export const Maximize2 = icon("Maximize2", "maximize2", `<path d="M14 3h7v7M21 3l-7 7M3 14v7h7M3 21l7-7"/>`);
export const Menu = icon("Menu", "menu", `<path d="M4 6h16M4 12h12M4 18h16"/>`);
export const MessageSquare = icon("MessageSquare", "message-square", `<path d="M7 3h10a4 4 0 0 1 4 4v7a4 4 0 0 1-4 4H9l-5 3V7a4 4 0 0 1 3-4Z"/>`);
export const MessageSquarePlus = icon("MessageSquarePlus", "message-square-plus", `<path d="M7 3h10a4 4 0 0 1 4 4v7a4 4 0 0 1-4 4H9l-5 3V7a4 4 0 0 1 3-4Z"/><path d="M9 10h7M12.5 6.5v7"/>`);
export const MessageSquareText = icon("MessageSquareText", "message-square-text", `<path d="M7 3h10a4 4 0 0 1 4 4v7a4 4 0 0 1-4 4H9l-5 3V7a4 4 0 0 1 3-4Z"/><path d="M8 8h8M8 13h5"/>`);
export const Minimize2 = icon("Minimize2", "minimize2", `<path d="M21 3l-7 7V3M14 10h7M3 21l7-7v7M10 14H3"/>`);
export const Minus = icon("Minus", "minus", `<path d="M5 12h14"/>`);
export const Monitor = icon("Monitor", "monitor", `<rect x="3" y="3" width="18" height="13" rx="3.5"/><path d="M12 16v5M8 21h8"/>`);
export const Moon = icon("Moon", "moon", `<path d="M20.5 14.5A9 9 0 0 1 9.5 3.5a9 9 0 1 0 11 11Z"/>`);
export const Navigation = icon("Navigation", "navigation", `<path d="M21 3 3 10l8 3 3 8Z"/>`);
export const NotebookPen = icon("NotebookPen", "notebook-pen", `<path d="M13 3H8a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h9a3 3 0 0 0 3-3v-5M3 8h4M3 15h4"/><path d="m12 12 1-4 5-5c2-2 5 1 3 3l-5 5Z"/>`);
export const Package = icon("Package", "package", `<path d="m4 7 8-4 8 4v10a2 2 0 0 1-1 2l-7 3-7-3a2 2 0 0 1-1-2ZM4 7l8 4 8-4M12 11v11M8 5l8 4"/>`);
export const PackageCheck = icon("PackageCheck", "package-check", `<path d="m3 6 8-3 8 3-8 4ZM3 6v11l8 4M11 10v11M19 6v6"/><path d="m15 18 3 3 4-6"/>`);
export const PackageSearch = icon("PackageSearch", "package-search", `<path d="m3 6 8-3 8 3-8 4ZM3 6v11l6 3M11 10v3M19 6v3"/><circle cx="17" cy="16" r="4"/><path d="m20 19 2 3"/>`);
export const Palette = icon("Palette", "palette", `<path d="M12 3a9 9 0 0 0 0 18h1a2 2 0 0 0 1-4 2 2 0 0 1 1-3h3c5 0 4-11-6-11Z"/><circle cx="7" cy="10" r="1.2" fill="currentColor" stroke="none"/><circle cx="10" cy="6.5" r="1.2" fill="currentColor" stroke="none"/><circle cx="15" cy="7" r="1.2" fill="currentColor" stroke="none"/><circle cx="6.5" cy="15" r="1.2" fill="currentColor" stroke="none"/>`);
export const Pencil = icon("Pencil", "pencil", `<path d="m4 15 12-12c2-2 7 3 5 5L9 20l-6 1ZM14 5l5 5M4 15l5 5"/>`);
export const Phone = icon("Phone", "phone", `<path d="M5 3h3l2 5-3 3c1 3 3 5 6 6l3-3 5 2v3a2 2 0 0 1-2 2C10 21 3 14 3 5a2 2 0 0 1 2-2Z"/>`);
export const Play = icon("Play", "play", `<path d="M6 5c0-2 1-3 3-2l11 7c2 1 2 3 0 4L9 21c-2 1-3 0-3-2Z" fill="currentColor" stroke="none"/>`);
export const Plus = icon("Plus", "plus", `<path d="M5 12h14M12 5v14"/>`);
export const Printer = icon("Printer", "printer", `<path d="M7 8V3h10v5M7 18H5a2 2 0 0 1-2-2v-5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v5a2 2 0 0 1-2 2h-2"/><rect x="7" y="14" width="10" height="7" rx="1.5"/><circle cx="17" cy="11" r="1" fill="currentColor" stroke="none"/>`);
export const Redo2 = icon("Redo2", "redo2", `<g transform="translate(24 0) scale(-1 1)"><path d="M3 11h11a7 7 0 0 1 7 7M8 5l-6 6 6 6"/></g>`);
export const RefreshCcw = icon("RefreshCcw", "refresh-ccw", `<g transform="translate(24 0) scale(-1 1)"><path d="M4 9a8 8 0 0 1 14-4l3 4M21 3v6h-6M20 15a8 8 0 0 1-14 4l-3-4M3 21v-6h6"/></g>`);
export const RefreshCw = icon("RefreshCw", "refresh-cw", `<path d="M4 9a8 8 0 0 1 14-4l3 4M21 3v6h-6M20 15a8 8 0 0 1-14 4l-3-4M3 21v-6h6"/>`);
export const RotateCcw = icon("RotateCcw", "rotate-ccw", `<path d="M4 9a8.5 8.5 0 1 1 0 7M3 3v6h6"/>`);
export const Save = icon("Save", "save", `<path d="M6 3h11l4 4v11a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3ZM8 3v6h8V3"/><rect x="7" y="14" width="10" height="7" rx="2"/>`);
export const Scale = icon("Scale", "scale", `<path d="M12 3v18M8 21h8M4 7c5 0 6-2 8-2s3 2 8 2M5 8l-3 7c1 3 5 3 6 0ZM19 8l-3 7c1 3 5 3 6 0Z"/>`);
export const Search = icon("Search", "search", `<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/>`);
export const Settings = icon("Settings", "settings", `<path d="M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z"/><circle cx="12" cy="12" r="3"/>`);
export const Shapes = icon("Shapes", "shapes", `<path d="M10 10C4 11 3 6 3 3c5 0 8 2 7 7Z" fill="currentColor" stroke="none"/><circle cx="17" cy="7" r="3.5"/><rect x="4" y="15" width="6" height="6" rx="2.4"/><path d="M15 20v-3a3 3 0 0 1 3-3h3v3a3 3 0 0 1-3 3Z"/>`);
export const ShieldCheck = icon("ShieldCheck", "shield-check", `<path d="M12 3c3 2 5 3 8 3v6c0 5-4 8-8 10-4-2-8-5-8-10V6c3 0 5-1 8-3Z"/><path d="m8 12 3 3 5-6"/>`);
export const ShieldOff = icon("ShieldOff", "shield-off", `<path d="M9 4l3-1c3 2 5 3 8 3v6l-.5 2M4 7v5c0 5 4 8 8 10l5-4M3 3l18 18"/>`);
export const ShoppingCart = icon("ShoppingCart", "shopping-cart", `<path d="M3 4h2l2.2 11a2 2 0 0 0 2 1.5h8.6a2 2 0 0 0 2-1.6L21 8H6"/><circle cx="9" cy="21" r="1.4" fill="currentColor" stroke="none"/><circle cx="18" cy="21" r="1.4" fill="currentColor" stroke="none"/>`);
export const Shrub = icon("Shrub", "shrub", `<path d="M6 18c-6-1-5-8 0-8-1-8 13-8 12 0 5 0 6 7 0 8Z"/><path d="M12 21v-8m-4 1 4 3 4-3"/>`);
export const SlidersHorizontal = icon("SlidersHorizontal", "sliders-horizontal", `<path d="M3 6h3M11 6h10M3 18h10M18 18h3"/><circle cx="8.5" cy="6" r="2.5"/><circle cx="15.5" cy="18" r="2.5"/>`);
export const Sparkle = icon("Sparkle", "sparkle", `<path d="M12 3C14 9 15 10 21 12 15 14 14 15 12 21 10 15 9 14 3 12 9 10 10 9 12 3Z"/>`);
export const Sparkles = icon("Sparkles", "sparkles", `<path d="M11 3c1.5 6 2 6.5 8 8-6 1.5-6.5 2-8 8-1.5-6-2-6.5-8-8 6-1.5 6.5-2 8-8Z"/><path d="M18 6c0-3 1-4 4-4 0 3-1 4-4 4ZM18 18c3 0 4 1 4 4-3 0-4-1-4-4Z" fill="currentColor" stroke="none"/>`);
export const Spline = icon("Spline", "spline", `<path d="M4 19c0-10 16 0 16-10 0-3-3-5-6-5M14 4H9"/><circle cx="4" cy="19" r="1.5" fill="currentColor" stroke="none"/><circle cx="9" cy="4" r="1.5" fill="currentColor" stroke="none"/>`);
export const Sprout = icon("Sprout", "sprout", `<path d="M11 13C4 14 2 9 2 5c5 0 9 2 9 8ZM13 12C12 5 16 2 22 2c0 6-3 11-9 10Z" fill="currentColor" stroke="none"/><path d="M12 21v-6M8 21h8"/>`);
export const Square = icon("Square", "square", `<rect x="4" y="4" width="16" height="16" rx="5"/>`);
export const Star = icon("Star", "star", `<path d="m12 3 3 6 6 1-4.5 5 1 6-5.5-3-5.5 3 1-6L3 10l6-1Z"/>`);
export const Store = icon("Store", "store", `<path d="M4 10v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-9M3 8l2-5h14l2 5c0 4-5 4-6 1-1 3-5 3-6 0-1 3-6 3-6-1ZM9 21v-6h6v6"/>`);
export const Sun = icon("Sun", "sun", `<circle cx="12" cy="12" r="4"/><path d="M12 2v1M12 21v1M2 12h1M21 12h1M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1"/>`);
export const Tag = icon("Tag", "tag", `<path d="M4 4h7a3 3 0 0 1 2 1l8 8a2 2 0 0 1 0 3l-5 5a2 2 0 0 1-3 0l-8-8a3 3 0 0 1-1-2Z"/><circle cx="8" cy="8" r="1.2" fill="currentColor" stroke="none"/>`);
export const Tags = icon("Tags", "tags", `<path d="M3 5v7l8 8a2 2 0 0 0 3 0l5-5a2 2 0 0 0 0-3l-7-7ZM11 2h4l7 7"/><circle cx="7" cy="9" r="1.2" fill="currentColor" stroke="none"/>`);
export const Trash2 = icon("Trash2", "trash2", `<path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M5 6l1 12a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3l1-12M10 10v7M14 10v7"/>`);
export const TreeDeciduous = icon("TreeDeciduous", "tree-deciduous", `<path d="M8 16c-7 0-7-8-2-9 0-7 12-7 12 0 5 1 5 9-2 9Z"/><path d="M12 21V11m-4 1 4 4 4-4M9 21h6"/>`);
export const TreePine = icon("TreePine", "tree-pine", `<path d="M12 2c-1 4-3 6-6 8h3c-1 3-3 5-5 7 4 3 12 3 16 0-2-2-4-4-5-7h3c-3-2-5-4-6-8Z"/><path d="M12 19v3"/>`);
export const TrendingDown = icon("TrendingDown", "trending-down", `<path d="m3 7 6 6 5-4 7 9M15 18h6v-6"/>`);
export const TrendingUp = icon("TrendingUp", "trending-up", `<path d="m3 17 6-6 5 4 7-9M15 6h6v6"/>`);
export const Undo2 = icon("Undo2", "undo2", `<path d="M3 11h11a7 7 0 0 1 7 7M8 5l-6 6 6 6"/>`);
export const Upload = icon("Upload", "upload", `<path d="M3 15v3a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-3M12 16V3m-5 5 5-5 5 5"/>`);
export const Users = icon("Users", "users", `<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3Z"/><path d="M16 4a3 3 0 0 1 0 6M18 14c3 0 4 2 4 5v2h-3"/>`);
export const Waves = icon("Waves", "waves", `<path d="M3 6c3-4 6 4 9 0s6 4 9 0M3 12c3-4 6 4 9 0s6 4 9 0M3 18c3-4 6 4 9 0s6 4 9 0"/>`);
export const X = icon("X", "x", `<path d="m6 6 12 12M18 6 6 18"/>`);
export const XCircle = icon("XCircle", "x-circle", `<circle cx="12" cy="12" r="9"/><path d="m8.5 8.5 7 7m0-7-7 7"/>`);
export const Zap = icon("Zap", "zap", `<path d="M13 3 4 13h7l-1 8 10-11h-7Z"/>`);
export const ZoomIn = icon("ZoomIn", "zoom-in", `<circle cx="10.5" cy="10.5" r="7"/><path d="m16 16 5 5"/><path d="M7 10.5h7M10.5 7v7"/>`);
