import type {
  BuilderFieldKey,
  BuilderSpecies,
  SilhouetteOption,
  CanopyTiersResponse,
  DensityResponse,
  CommonBuild,
} from "./types";
import { confidenceLabel } from "./builderTypes";

/**
 * Step 1's measured fields.
 *
 * Replaces the old Height / "Width / canopy" / "Depth / density" text boxes.
 * Every control here is fed by `/api/builder/*`, and only the fields the build
 * type declares in its `fields` map are rendered - Container Only shows no
 * canopy, silhouette or density at all, Drop-in no canopy or silhouette.
 */
export function MeasuredScopeFields({
  buildTypeLabel,
  fields,
  recipeCount,
  typeNotes,
  height,
  onHeightChange,
  species,
  onSpeciesChange,
  speciesOptions,
  activeSpecies,
  canopyTiers,
  canopyTier,
  onCanopyTier,
  width,
  onWidthChange,
  silhouetteOptions,
  silhouette,
  onSilhouette,
  depth,
  onDepthChange,
  densityInfo,
  densityApplies,
  densityBand,
  onDensityBand,
  commonBuilds,
  commonBuildPick,
  onCommonBuild,
}: {
  buildTypeLabel: string;
  fields: Record<BuilderFieldKey, boolean>;
  recipeCount?: number;
  typeNotes?: string | null;
  height: string;
  onHeightChange: (value: string) => void;
  species: string;
  onSpeciesChange: (value: string) => void;
  speciesOptions: BuilderSpecies[];
  activeSpecies: BuilderSpecies | null;
  canopyTiers: CanopyTiersResponse | null;
  canopyTier: string;
  onCanopyTier: (key: string) => void;
  width: string;
  onWidthChange: (value: string) => void;
  silhouetteOptions: SilhouetteOption[];
  silhouette: string;
  onSilhouette: (key: string) => void;
  depth: string;
  onDepthChange: (value: string) => void;
  densityInfo: DensityResponse | null;
  densityApplies: boolean;
  densityBand: string;
  onDensityBand: (key: string) => void;
  commonBuilds: CommonBuild[];
  commonBuildPick: string;
  onCommonBuild: (name: string) => void;
}) {
  const activeTier = canopyTiers?.tiers?.find((tier) => tier.key === canopyTier) || null;
  const activeBand = densityInfo?.bands?.find((band) => band.key === densityBand) || null;
  const specimenSpecies = activeSpecies?.density_applies === false || densityInfo?.density_applies === false;

  return (
    <div className="mt-5 space-y-4 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Build scope</p>
          <p className="mt-1 text-xs text-stone-400">Sizing and density guide the recommendation before products are chosen.</p>
        </div>
      </div>

      {/* Species drives every suggestion under it, so it is explicit at Step 1. */}
      {fields.species && (
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-stone-500">Species / style</span>
          <select
            value={species}
            onChange={(event) => onSpeciesChange(event.target.value)}
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          >
            <option value="">Select a species or style...</option>
            {speciesOptions.map((option) => (
              <option key={option.name} value={option.name}>
                {option.name}
              </option>
            ))}
          </select>
          {activeSpecies && (
            <span className="mt-1 block text-[11px] text-stone-400">
              {specimenSpecies
                ? "Specimen: about one stem — a single large potted plant, nothing to build up."
                : "Built up from many stems, so density below is a real dial."}
            </span>
          )}
        </label>
      )}

      {fields.height && (
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-stone-500">Height</span>
          <input
            value={height}
            onChange={(event) => onHeightChange(event.target.value)}
            placeholder={`e.g. 7' or 42"`}
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          {canopyTiers?.band && (
            <span className="mt-1 block text-[11px] text-stone-400">
              Height band {canopyTiers.band}
              {canopyTiers.height_display ? ` · read as ${canopyTiers.height_display}` : ""}
            </span>
          )}
        </label>
      )}

      {/* Canopy tiers are defined inside the build's own height band, so
          "Medium" means the same visual fullness at any height. */}
      {fields.canopy && (
        <div>
          <span className="mb-1 block text-xs font-semibold text-stone-500">Canopy</span>
          {!canopyTiers?.tiers?.length ? (
            <p className="rounded-lg border border-dashed border-stone-300 bg-white px-3 py-2 text-[11px] text-stone-400">
              Enter a height first — canopy tiers are cut per height band, so 42&quot; is full on a 6&apos; tree and standard on a 9&apos;.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-5 gap-1">
                {canopyTiers.tiers.map((tier) => (
                  <button
                    key={tier.key}
                    type="button"
                    onClick={() => onCanopyTier(tier.key)}
                    title={`${tier.label} · ${tier.range_label}`}
                    className={`rounded-lg border px-1 py-2 text-center transition-colors ${
                      canopyTier === tier.key
                        ? "border-stone-900 bg-white text-stone-950 shadow-sm"
                        : "border-stone-200 bg-white/70 text-stone-500 hover:border-stone-300 hover:text-stone-800"
                    }`}
                  >
                    <span className="block text-xs font-semibold">{tier.key}</span>
                    <span className="mt-0.5 block text-[10px] leading-tight text-stone-400">{tier.range_label}</span>
                  </button>
                ))}
              </div>
              <span className="mt-1 block text-[11px] text-stone-400">
                {activeTier ? `${activeTier.label} · ${activeTier.range_label} wide in the ${canopyTiers.band} band` : "Pick a tier"}
                {canopyTiers.default_tier ? ` · most builds here are ${canopyTiers.default_tier}` : ""}
              </span>
              {canopyTiers.provisional && (
                <span className="mt-1 block rounded-lg bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-900 ring-1 ring-amber-100">
                  Provisional: few past builds in this band, so these cut points will shift as more land.
                </span>
              )}
            </>
          )}
        </div>
      )}

      {fields.width && (
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-stone-500">Width{fields.canopy ? " (canopy diameter)" : ""}</span>
          <input
            value={width}
            onChange={(event) => onWidthChange(event.target.value)}
            placeholder={`e.g. 42"`}
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
        </label>
      )}

      {/* No historical build was anything but round (median depth:width 1.00), so
          this is capture-going-forward - and it sets the depth. */}
      {fields.depth && (
        <label className="block">
          <span className="mb-1 block text-xs font-semibold text-stone-500">Depth</span>
          <input
            value={depth}
            onChange={(event) => onDepthChange(event.target.value)}
            placeholder={`e.g. 42"`}
            className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          {fields.silhouette && (
            <span className="mt-1 block text-[11px] text-stone-400">Computed from width x silhouette. Override it if the build says otherwise.</span>
          )}
        </label>
      )}

      {/* Density is f(species, height) and never pooled: at 7ft an Areca is 1
          stem and a Eucalyptus 16. The piece count sits under each band. */}
      {fields.density && (
        <div>
          <span className="mb-1 block text-xs font-semibold text-stone-500">Density</span>
          {!species.trim() ? (
            <p className="rounded-lg border border-dashed border-stone-300 bg-white px-3 py-2 text-[11px] text-stone-400">
              Pick a species first — piece counts are per species, not pooled. At 7&apos; an Areca is 1 stem and a Eucalyptus 16.
            </p>
          ) : !densityApplies ? (
            <p className="rounded-lg border border-dashed border-stone-300 bg-white px-3 py-2 text-[11px] text-stone-500">
              {specimenSpecies
                ? `${densityInfo?.species || species} is a specimen — about one stem, so there is no density to set.`
                : "Density does not apply to this build type."}
            </p>
          ) : !densityInfo?.bands?.length ? (
            <p className="rounded-lg border border-dashed border-stone-300 bg-white px-3 py-2 text-[11px] text-stone-400">
              No measured baseline for this species and height yet.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-4 gap-1">
                {densityInfo.bands.map((band) => (
                  <button
                    key={band.key}
                    type="button"
                    onClick={() => onDensityBand(band.key)}
                    className={`rounded-lg border px-1 py-2 text-center transition-colors ${
                      densityBand === band.key
                        ? "border-stone-900 bg-white text-stone-950 shadow-sm"
                        : "border-stone-200 bg-white/70 text-stone-500 hover:border-stone-300 hover:text-stone-800"
                    }`}
                  >
                    <span className="block text-[11px] font-semibold leading-tight">{band.label}</span>
                    <span className="mt-0.5 block text-[10px] leading-tight text-stone-400">
                      {band.pieces} piece{band.pieces === 1 ? "" : "s"}
                    </span>
                  </button>
                ))}
              </div>
              <span className="mt-1 block text-[11px] text-stone-400">
                {densityInfo.species}
                {densityInfo.height_display ? ` at ${densityInfo.height_display}` : ""}
                {densityInfo.baseline_pieces != null ? ` · baseline ${densityInfo.baseline_pieces} pieces` : ""}
                {activeBand ? ` · ${activeBand.label} = ${activeBand.pieces}` : ""}
              </span>
              {/* Sparse data is reported, never smoothed over. */}
              <span className="mt-1 block text-[11px] text-stone-400">
                {densityInfo.observed_min != null && densityInfo.observed_max != null
                  ? `Ranged ${densityInfo.observed_min}–${densityInfo.observed_max} pieces`
                  : "Suggested range"}
                {densityInfo.confidence ? ` · ${confidenceLabel(densityInfo.confidence)} confidence` : ""}
                {densityInfo.source === "class" ? " · no history for this species, using its structural class" : ""}
              </span>
              {(densityInfo.notes || []).map((note) => (
                <span key={note} className="mt-1 block text-[11px] text-stone-400">{note}</span>
              ))}
            </>
          )}
        </div>
      )}

      {fields.silhouette && (
        <div>
          <span className="mb-1 block text-xs font-semibold text-stone-500">Silhouette</span>
          <div className="grid gap-1">
            {silhouetteOptions.map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => onSilhouette(option.key)}
                className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  silhouette === option.key
                    ? "border-stone-900 bg-white text-stone-950 shadow-sm"
                    : "border-stone-200 bg-white/70 text-stone-500 hover:border-stone-300 hover:text-stone-800"
                }`}
              >
                <span>
                  <span className="font-semibold">{option.label}</span>
                  {option.use ? <span className="ml-2 text-stone-400">{option.use}</span> : null}
                </span>
                <span className="shrink-0 text-[10px] font-semibold text-stone-400">depth {option.depth_ratio}x width</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {!fields.canopy && !fields.silhouette && !fields.density && (
        <p className="text-[11px] text-stone-400">
          {buildTypeLabel} records height, width and depth only — canopy, silhouette and density do not apply to it.
        </p>
      )}
    </div>
  );
}
