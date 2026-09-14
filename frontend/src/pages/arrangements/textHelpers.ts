// Label and scope-note text helpers shared by the Arrangements modules.

export function normalizeLabel(value?: string | null) {
  return (value || "").trim().toLowerCase();
}

export function firstNumber(value?: string | null) {
  const match = String(value || "").match(/(\d+(?:\.\d+)?)/);
  return match ? Number(match[1]) : null;
}

export function scopeNoteValue(notes: string | null | undefined, label: string) {
  const prefix = `${label}:`;
  const line = (notes || "").split("\n").find((part) => part.trim().toLowerCase().startsWith(prefix.toLowerCase()));
  return line ? line.slice(prefix.length).trim() : "";
}
