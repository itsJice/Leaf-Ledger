// Generic multi-select dropdown filter used by the product library's
// filter row. Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useEffect, useRef, useState } from "react";
import { ChevronDown, Check, X } from "lucide-react";

export function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const toggleValue = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value]
    );
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-300"
      >
        <span className="truncate text-left">
          {selected.length === 0 ? label : `${selected.length} selected`}
        </span>
        <ChevronDown size={15} className={`text-stone-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-xl border border-stone-200 bg-white p-1 shadow-lg">
          {options.map((option) => {
            const active = selected.includes(option);
            return (
              <button
                key={option}
                type="button"
                onClick={() => toggleValue(option)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm text-left ${
                  active ? "bg-emerald-50 text-emerald-700" : "text-stone-700 hover:bg-stone-50"
                }`}
              >
                <span className="truncate">{option}</span>
                {active && <Check size={14} />}
              </button>
            );
          })}
        </div>
      )}
      {selected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {selected.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => toggleValue(value)}
              className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
            >
              <span>{value}</span>
              <X size={12} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
