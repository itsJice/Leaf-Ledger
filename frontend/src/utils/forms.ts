import { apiFetch } from "utils/apiFetch";

/**
 * Forms (the built-in Google Forms replacement): types, API calls, and the
 * pure rules the pages share. Validation mirrors backend/app/libs/forms.py
 * so "Next" can stop at an empty required field without a round trip; the
 * server checks everything again on submit.
 */

export type QuestionType = "short_text" | "long_text" | "dropdown" | "radio" | "checkboxes" | "date";
export type Answer = string | string[] | null;
export type Answers = Record<string, Answer>;

export interface FormSection { id: number; position: number; title: string; description: string | null }
export interface FormQuestion {
  id: number; section_id: number; position: number; key: string; label: string;
  helper_text: string | null; type: QuestionType; required: boolean; options: string[] | null;
  export_position: number | null;
}
export interface FormDef {
  id: number; slug: string; title: string; description: string | null; is_accepting: boolean;
  sections: FormSection[]; questions: FormQuestion[];
}
export const STATUSES = ["New", "Ordered", "Received", "Cancelled"] as const;
export type Status = (typeof STATUSES)[number];
/** The buyer is done with these -- drawn struck through, like the Sheet. */
export const DONE: ReadonlySet<string> = new Set(["Ordered", "Received", "Cancelled"]);

export interface FormResponse {
  id: number; submitted_at: string; status: Status; buyer_notes: string | null;
  submitted_by: string | null; source: string; updated_at: string | null; updated_by: string | null;
  answers: Answers;
}

export const REQUIRED_MESSAGE = "This is a required question";

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(url, init);
  if (!res.ok) {
    let detail: unknown = null;
    try { detail = (await res.json())?.detail; } catch { /* no body */ }
    const err = new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`) as Error & { status?: number; detail?: unknown };
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return res.json() as Promise<T>;
}
const json = (method: string, body: unknown): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

export const getForm = (slug: string) => call<FormDef>(`/api/forms/${slug}`);
export const submitForm = (slug: string, answers: Answers) =>
  call<{ id: number; submitted_at: string }>(`/api/forms/${slug}/responses`, json("POST", { answers }));
export const getSuggestions = (slug: string) => call<Record<string, string[]>>(`/api/forms/${slug}/suggestions`);
export const listResponses = (slug: string) =>
  call<{ form: FormDef; responses: FormResponse[] }>(`/api/forms/${slug}/responses`);
export const updateResponse = (id: number, patch: { status?: Status; buyer_notes?: string }) =>
  call<{ id: number; status: Status; buyer_notes: string | null }>(`/api/forms/responses/${id}`, json("PATCH", patch));
export const setAccepting = (slug: string, is_accepting: boolean) =>
  call<{ is_accepting: boolean }>(`/api/forms/${slug}`, json("PATCH", { is_accepting }));
export const exportUrl = (slug: string) => `/api/forms/${slug}/export.csv`;

// ── pure rules ────────────────────────────────────────────────────────────

export function isEmpty(v: Answer | undefined): boolean {
  if (v == null) return true;
  if (Array.isArray(v)) return v.every((x) => !String(x).trim());
  return !String(v).trim();
}

/** {key: message} for one section's questions (or all, with no section). */
export function validateAnswers(questions: FormQuestion[], answers: Answers, sectionId?: number): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const q of questions) {
    if (sectionId != null && q.section_id !== sectionId) continue;
    const v = answers[q.key];
    if (isEmpty(v)) {
      if (q.required) errors[q.key] = REQUIRED_MESSAGE;
      continue;
    }
    if (q.type === "date" && !/^\d{4}-\d{2}-\d{2}/.test(String(v))) errors[q.key] = "Enter a date";
  }
  return errors;
}

/** The questions whose answers "Submit another for the same project" keeps. */
export const CARRY_KEYS = ["requestor", "client_name", "project_name", "location_item"];

export function carryOver(answers: Answers): Answers {
  const out: Answers = {};
  for (const k of CARRY_KEYS) if (!isEmpty(answers[k])) out[k] = answers[k];
  return out;
}

export function answerText(v: Answer | undefined): string {
  if (v == null) return "";
  return Array.isArray(v) ? v.join(", ") : String(v);
}

/** 9/14/2026 19:04:29 -- the Sheet's timestamp format, in the viewer's time. */
export function fmtTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getMonth() + 1}/${d.getDate()}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

/** An ISO date as 11/30/2026 (dates, not instants -- no time zone shift). */
export function fmtDate(v: Answer | undefined): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(v ?? ""));
  return m ? `${Number(m[2])}/${Number(m[3])}/${m[1]}` : answerText(v);
}

export const isUrl = (s: string) => /^https?:\/\/\S+$/i.test(s.trim());

/** A short label for a long bilingual option: its English sentence. */
export function shortOption(o: string): string {
  const m = /^(.*?[.?!])\s/.exec(o);
  return m ? m[1] : o;
}

/** Counts per value for the Summary tab -- checkbox picks counted separately,
 * free text grouped case-insensitively with the most common spelling shown. */
export function countBy(responses: FormResponse[], q: FormQuestion): { value: string; count: number }[] {
  const counts = new Map<string, { value: string; count: number; spellings: Map<string, number> }>();
  for (const r of responses) {
    const v = r.answers[q.key];
    const vals = Array.isArray(v) ? v : isEmpty(v) ? [] : [String(v)];
    for (const raw of vals) {
      const val = String(raw).trim();
      const key = q.options ? val : val.toLowerCase().replace(/\s+/g, " ");
      const e = counts.get(key) || { value: val, count: 0, spellings: new Map() };
      e.count += 1;
      e.spellings.set(val, (e.spellings.get(val) || 0) + 1);
      counts.set(key, e);
    }
  }
  return [...counts.values()]
    .map((e) => ({ value: [...e.spellings.entries()].sort((a, b) => b[1] - a[1])[0][0], count: e.count }))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value));
}

export interface ResponseFilter {
  text: string; client: string; project: string; requestor: string; status: string; from: string; to: string;
}
export const EMPTY_FILTER: ResponseFilter = { text: "", client: "", project: "", requestor: "", status: "", from: "", to: "" };

const low = (s: unknown) => String(s ?? "").trim().toLowerCase();

export function filterResponses(responses: FormResponse[], f: ResponseFilter): FormResponse[] {
  const words = low(f.text).split(/\s+/).filter(Boolean);
  return responses.filter((r) => {
    const a = r.answers;
    if (f.client && low(a.client_name) !== low(f.client)) return false;
    if (f.project && low(a.project_name) !== low(f.project)) return false;
    if (f.requestor && low(a.requestor) !== low(f.requestor)) return false;
    if (f.status && r.status !== f.status) return false;
    const d = String(a.install_date ?? "").slice(0, 10);
    if (f.from && (!d || d < f.from)) return false;
    if (f.to && (!d || d > f.to)) return false;
    if (words.length) {
      const hay = low([...Object.values(a).map(answerText), r.buyer_notes, r.status].join(" "));
      if (!words.every((w) => hay.includes(w))) return false;
    }
    return true;
  });
}
