import React from "react";
import type { LucideIcon } from "components/icons";

/**
 * Centered "nothing selected" panel: a round brand-tinted badge with an icon,
 * a title and a short hint. It renders exactly the DOM of the inline `Empty()`
 * in pages/Sourcing.tsx and pages/Orders.tsx (see empty-state.test.tsx).
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  className = "flex flex-col items-center justify-center py-24 text-center",
}: {
  icon: LucideIcon;
  title: React.ReactNode;
  description: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
        <Icon size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">{title}</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">{description}</p>
    </div>
  );
}

export default EmptyState;
