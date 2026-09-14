import { CircleDashed, Flower2, Leaf, Shapes, Shrub, Sparkle, Spline, Sprout, TreeDeciduous, TreePine, Waves } from "lucide-react";

// Build-type → icon. Ordered: the first pattern that matches wins, so
// "Christmas Tree" beats the generic "tree" rule.
// Verbatim copy of pages/Designs.tsx (see buildTypeIcon.test.ts). pages/App.tsx
// has an older, different mapping.
type IconComponent = typeof TreePine;
const BUILD_TYPE_ICONS: [RegExp, IconComponent][] = [
  [/christmas tree|holiday tree/, TreePine],
  [/wreath/, CircleDashed],
  [/garland/, Spline],
  [/swag/, Waves],
  [/spray|teardrop|door drop/, Sprout],
  [/planter|container garden/, Shrub],
  [/ornament/, Sparkle],
  [/branch|stem/, Leaf],
  [/tree|fig/, TreeDeciduous],
  [/centerpiece|arrangement|floral|orchid|succulent/, Flower2],
];

export function buildTypeIcon(buildType?: string | null): IconComponent {
  const normalized = (buildType || "").trim().toLowerCase();
  if (!normalized) return Shapes;
  for (const [pattern, Icon] of BUILD_TYPE_ICONS) {
    if (pattern.test(normalized)) return Icon;
  }
  return Shapes;
}
