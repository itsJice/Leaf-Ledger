// Build-type configs and the enhancer, wreath and garland tables.
import { Circle, Grid3X3, Leaf, Package } from "lucide-react";
import type { GarlandDiameter, WreathSize, EnhancerPartConfig } from "./types";
import { normalizeLabel } from "./textHelpers";

export const BUILD_TYPE_CONFIGS = [
  {
    section: "green",
    label: "Tree",
    skuCode: "GR-TREE",
    icon: Leaf,
    aliases: ["Tree", "Tree / Plant", "Greenery Tree"],
    prefixes: ["TT", "TL", "GT"],
    visibleParts: ["Leaves", "Trunks & Branches", "Top Dressing", "Container"],
  },
  {
    section: "green",
    label: "Arrangement",
    skuCode: "GR-ARR",
    icon: Leaf,
    aliases: ["Arrangement", "Orchid Arrangement", "Succulent Arrangement", "Greenery Arrangement", "Foliage Arrangement"],
    prefixes: ["OR", "SG", "WG", "FP"],
    visibleParts: ["Accent Material", "Focal Material", "Finish/Top Dressing", "Container/Base"],
  },
  {
    section: "green",
    label: "Planter",
    skuCode: "GR-PLN",
    icon: Grid3X3,
    aliases: ["Planter", "Container Garden", "Plant / Vase", "Container Arrangement"],
    prefixes: ["CG", "PV", "CT"],
    visibleParts: ["Accent Plant", "Main Plant", "Finish/Top Dressing", "Container/Planter"],
  },
  {
    section: "green",
    label: "Drop-in Arrangement",
    skuCode: "GR-DRP",
    icon: Package,
    aliases: ["Drop-in Arrangement", "Drop in", "Drop-in", "Dropin Arrangement"],
    prefixes: ["DR", "DI"],
    visibleParts: ["Finish", "Accent Material", "Main Material", "Drop-in Base"],
  },
  {
    section: "christmas",
    label: "Christmas Tree",
    skuCode: "CH-TREE",
    icon: Leaf,
    aliases: ["Christmas Tree"],
    prefixes: [],
    visibleParts: ["Tree", "Enhancers", "Tree Skirt", "Tree Topper"],
  },
  {
    section: "christmas",
    label: "Garland",
    skuCode: "CH-GAR",
    icon: Leaf,
    aliases: ["Garland"],
    prefixes: [],
    visibleParts: ["Garland", "Enhancers"],
  },
  {
    section: "christmas",
    label: "Wreath",
    skuCode: "CH-WRE",
    icon: Circle,
    aliases: ["Wreath"],
    prefixes: [],
    visibleParts: ["Wreath Base", "Decor Package"],
  },
  {
    section: "christmas",
    label: "Vertical Spray",
    skuCode: "CH-VSP",
    icon: Leaf,
    aliases: ["Vertical Spray", "Teardrop", "Door Drop", "Lantern Drop"],
    prefixes: [],
    visibleParts: ["Vertical Spray Base", "Greenery", "Ribbon", "Decor"],
  },
  {
    section: "christmas",
    label: "Horizontal Swag",
    skuCode: "CH-HSW",
    icon: Leaf,
    aliases: ["Horizontal Swag", "Swag", "Holiday Accent"],
    prefixes: [],
    visibleParts: ["Horizontal Swag Base", "Greenery", "Ribbon", "Decor"],
  },
] as const;

export const CHRISTMAS_ENHANCER_PARTS: EnhancerPartConfig[] = [
  {
    label: "Assorted Branch",
    note: "Used in both enhancer packages",
    regularFormula: "2 each",
    premiumFormula: "2 each",
    fallbackQuantity: 8,
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: '4" Ornament',
    note: "Used in both enhancer packages",
    regularFormula: "1 each",
    premiumFormula: "1 each",
    fallbackQuantity: 8,
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Ribbon",
    note: "Ribbon amount changes with the package",
    regularFormula: "2.5 yd",
    premiumFormula: "1.5 yd",
    fallbackQuantity: 20,
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: "Flower",
    note: "Only needed for premium enhancers",
    premiumFormula: "1 each",
    fallbackQuantity: 8,
    optional: true,
    searchTerms: "christmas flower floral pick",
  },
  {
    label: "Premium Ribbon",
    note: "Only needed for premium enhancers",
    premiumFormula: "1 yd",
    fallbackQuantity: 8,
    optional: true,
    searchTerms: "premium christmas ribbon wired ribbon",
  },
];

export const GARLAND_DIAMETER_OPTIONS: GarlandDiameter[] = ["14", "18"];

export const WREATH_SIZE_OPTIONS: WreathSize[] = ["24", "30", "36", "48"];

export const WREATH_DECOR_PARTS = [
  {
    label: "Assorted Branches",
    note: "Branch count changes with wreath size",
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: "Ribbon",
    note: "Ribbon yardage changes with wreath size",
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: '4" Ornaments',
    note: "Small ornaments for 24 and 30 inch wreaths",
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Flowers",
    note: "Floral accents for larger wreaths",
    searchTerms: "christmas flower floral pick",
  },
  {
    label: '8" Ornaments',
    note: "Large ornaments for 48 inch wreaths",
    searchTerms: "christmas 8 inch ornament ball",
  },
  {
    label: '6" Ornaments',
    note: "Medium ornaments for 48 inch wreaths",
    searchTerms: "christmas 6 inch ornament ball",
  },
] as const;

export const WREATH_DECOR_RECIPES: Record<WreathSize, Array<{ label: string; quantity: number; unit: "total" | "yd" }>> = {
  "24": [
    { label: "Assorted Branches", quantity: 4, unit: "total" },
    { label: "Ribbon", quantity: 3, unit: "yd" },
    { label: '4" Ornaments', quantity: 3, unit: "total" },
  ],
  "30": [
    { label: "Assorted Branches", quantity: 5, unit: "total" },
    { label: "Ribbon", quantity: 4, unit: "yd" },
    { label: '4" Ornaments', quantity: 5, unit: "total" },
  ],
  "36": [
    { label: "Flowers", quantity: 2, unit: "total" },
    { label: "Assorted Branches", quantity: 7, unit: "total" },
    { label: "Ribbon", quantity: 6, unit: "yd" },
  ],
  "48": [
    { label: "Flowers", quantity: 3, unit: "total" },
    { label: "Assorted Branches", quantity: 14, unit: "total" },
    { label: '8" Ornaments', quantity: 2, unit: "total" },
    { label: '6" Ornaments', quantity: 3, unit: "total" },
  ],
};

export const GARLAND_ENHANCER_PARTS = [
  {
    label: "Assorted Branches",
    note: "Branches used to build out the garland body",
    searchTerms: "christmas assorted branch pine berry pick spray",
  },
  {
    label: '4" Ornament',
    note: "Main ornament inside each enhancer set",
    searchTerms: "christmas 4 inch ornament ball",
  },
  {
    label: "Ribbon",
    note: "Ribbon yardage based on the selected package",
    searchTerms: "christmas ribbon wired ribbon",
  },
  {
    label: "Flower",
    note: "Only needed for premium garland",
    premiumOnly: true,
    searchTerms: "christmas flower floral pick",
  },
  {
    label: "Premium Ribbon",
    note: "Only needed for premium garland",
    premiumOnly: true,
    searchTerms: "premium christmas ribbon wired ribbon",
  },
  {
    label: "Extra Ornaments",
    note: "Extra ornaments added to the premium garland package",
    premiumOnly: true,
    searchTerms: "christmas ornament cluster decor",
  },
] as const;

export const CHRISTMAS_TREE_OPTIONS = [
  { code: "C164176LED", name: "Oregon Fir WA 900LED Warm White", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 65, profile: "Standard", lightStatus: "Lit" },
  { code: "K184076LED", name: "Kamas Fraser Dura-Lit 450WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 48, profile: "Standard", lightStatus: "Lit" },
  { code: "K194076LED", name: "Slim Natural Fraser Dura-Lit 700WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 45, profile: "Slim", lightStatus: "Lit" },
  { code: "K201276LED", name: "Brighton Pine Dura-Lit 650WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 48, profile: "Standard", lightStatus: "Lit" },
  { code: "A118277LED", name: "Cashmere Pine LED 700WW", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 55, profile: "Standard", lightStatus: "Lit" },
  { code: "D172376LED", name: "Mixed Brussels Pine 1300LED", source: "Vickerman", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 61, profile: "Standard", lightStatus: "Lit" },
  { code: "K194081LED", name: "Natural Fraser Dura-Lit 850WW", source: "Vickerman", heightFeet: 8.5, heightLabel: "8.5 ft", diameterIn: 50, profile: "Slim", lightStatus: "Lit" },
  { code: "K173381LED", name: "Flocked Kiana Dura-Lit 1000WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 66, profile: "Standard", lightStatus: "Lit" },
  { code: "K184081LED", name: "Kamas Fraser Fir Dura-Lit 650WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "K201281LED", name: "Brighton Pine Dura-Lit 900WW", source: "Vickerman", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "A118286LED", name: "Cashmere Pine LED 1150WW", source: "Vickerman", heightFeet: 9.5, heightLabel: "9.5 ft", diameterIn: 67, profile: "Standard", lightStatus: "Lit" },
  { code: "C164186LED", name: "Oregon Fir WA 1400LED Warm White", source: "Vickerman", heightFeet: 9.5, heightLabel: "9.5 ft", diameterIn: 82, profile: "Full", lightStatus: "Lit" },
  { code: "K201286LED", name: "Brighton Pine Dura-Lit 1100WW", source: "Vickerman", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard", lightStatus: "Lit" },
  { code: "C164191LED", name: "Oregon Fir WA 2400LED Warm White", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard", lightStatus: "Lit" },
  { code: "K194091LED", name: "Natural Fraser Dura-Lit 1350WW", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 72, profile: "Slim", lightStatus: "Lit" },
  { code: "K201291LED", name: "Brighton Pine Dura-Lit", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 73, profile: "Standard", lightStatus: "Lit" },
  { code: "A118291LED", name: "Brighton Pine Dura-Lit 1400WW", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 85, profile: "Standard", lightStatus: "Lit" },
  { code: "D172391LED", name: "Mixed Brussels Pine 2400LED", source: "Vickerman", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard", lightStatus: "Lit" },
  { code: "K201296LED", name: "Brighton Pine Dura-Lit 2000WW", source: "Vickerman", heightFeet: 14, heightLabel: "14 ft", diameterIn: 87, profile: "Standard", lightStatus: "Lit" },
  { code: "C164196LED", name: "Oregon Fir WA 3450LED Warm White", source: "Vickerman", heightFeet: 15, heightLabel: "15 ft", diameterIn: 114, profile: "Full", lightStatus: "Lit" },
  { code: "G194218WW", name: "Grand Teton Frame LED 7200WW", source: "Vickerman", heightFeet: 18, heightLabel: "18 ft", diameterIn: 131, profile: "Full", lightStatus: "Lit" },
  { code: "MTX70096B-TGCB", name: "Lit Asheville Alpine Tree 150L", source: "Regency", heightFeet: 4, heightLabel: "4 ft", diameterIn: 24, profile: "Pencil", lightStatus: "Lit" },
  { code: "MTX43286L", name: "LED Slim Belgium Tree 450L", source: "Regency", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 41, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX45177L", name: "LED Deluxe Belgium Tree 950LT", source: "Regency", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 61, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX43287B", name: "Lit Slim Belgium Mix Tree 650L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 49, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX43283B", name: "Lit Belgium Mix Tree 900L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX45178L", name: "LED Belgium Mix Tree 1400L", source: "Regency", heightFeet: 9, heightLabel: "9 ft", diameterIn: 73, profile: "Full", lightStatus: "Lit" },
  { code: "MTX43284L", name: "LED Belgium Mix Tree 1050L", source: "Regency", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard", lightStatus: "Lit" },
  { code: "MTX47019N", name: "LED Deluxe Mix Belgium Tree 2150L", source: "Regency", heightFeet: 10, heightLabel: "10 ft", diameterIn: 75, profile: "Full", lightStatus: "Lit" },
  { code: "MTX43289L", name: "LED Slim Belgium 1300L", source: "Regency", heightFeet: 12, heightLabel: "12 ft", diameterIn: 63, profile: "Slim", lightStatus: "Lit" },
  { code: "MTX32248L", name: "LED Flock Bear Mountain Tree 1100LT", source: "Regency", heightFeet: 9.9, heightLabel: "9 ft 11 in", diameterIn: 73, profile: "Full", lightStatus: "Lit" },
] as const;

export const CHRISTMAS_TREE_SIZE_OPTIONS = [
  { code: "6-PENCIL", label: "6' Pencil", heightFeet: 6, heightLabel: "6 ft", diameterIn: 30, profile: "Pencil" },
  { code: "7-5-PENCIL", label: "7.5' Pencil", heightFeet: 7.5, heightLabel: "7.5 ft", diameterIn: 30, profile: "Pencil" },
  { code: "7-SLIM", label: "7' Slim", heightFeet: 7, heightLabel: "7 ft", diameterIn: 42, profile: "Slim" },
  { code: "7-5-8-STANDARD", label: "7.5-8' Standard", heightFeet: 7.5, heightLabel: "7.5-8 ft", diameterIn: 55, profile: "Standard" },
  { code: "9-PENCIL", label: "9' Pencil", heightFeet: 9, heightLabel: "9 ft", diameterIn: 32, profile: "Pencil" },
  { code: "9-SLIM", label: "9' Slim", heightFeet: 9, heightLabel: "9 ft", diameterIn: 50, profile: "Slim" },
  { code: "9-STANDARD", label: "9' Standard", heightFeet: 9, heightLabel: "9 ft", diameterIn: 57, profile: "Standard" },
  { code: "10-STANDARD", label: "10'", heightFeet: 10, heightLabel: "10 ft", diameterIn: 63, profile: "Standard" },
  { code: "12-SLIM", label: "12' Slim", heightFeet: 12, heightLabel: "12 ft", diameterIn: 72, profile: "Slim" },
  { code: "12-STANDARD", label: "12' Standard", heightFeet: 12, heightLabel: "12 ft", diameterIn: 86, profile: "Standard" },
  { code: "14-STANDARD", label: "14'", heightFeet: 14, heightLabel: "14 ft", diameterIn: 87, profile: "Standard" },
  { code: "15-STANDARD", label: "15'", heightFeet: 15, heightLabel: "15 ft", diameterIn: 114, profile: "Standard" },
] as const;

export function buildTypeConfigFor(buildType: string) {
  const normalized = normalizeLabel(buildType);
  const exact = BUILD_TYPE_CONFIGS.find((config) =>
    normalizeLabel(config.label) === normalized || config.aliases.some((alias) => normalizeLabel(alias) === normalized)
  );
  if (exact) return exact;
  if (normalized.includes("christmas tree")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Christmas Tree") || null;
  if (normalized.includes("garland")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Garland") || null;
  if (normalized.includes("wreath")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Wreath") || null;
  if (normalized.includes("vertical spray") || normalized.includes("teardrop") || normalized.includes("door drop")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Vertical Spray") || null;
  if (normalized.includes("horizontal swag") || normalized.includes("swag")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Horizontal Swag") || null;
  if (normalized.includes("drop")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Drop-in Arrangement") || null;
  if (normalized.includes("container garden") || normalized.includes("plant / vase") || normalized.includes("planter")) {
    return BUILD_TYPE_CONFIGS.find((config) => config.label === "Planter") || null;
  }
  if (normalized.includes("tree") || normalized.includes("fig")) return BUILD_TYPE_CONFIGS.find((config) => config.label === "Tree") || null;
  if (["orchid", "succulent", "greenery", "foliage"].some((word) => normalized.includes(word)) || normalized.includes("arrangement")) {
    return BUILD_TYPE_CONFIGS.find((config) => config.label === "Arrangement") || null;
  }
  return null;
}
