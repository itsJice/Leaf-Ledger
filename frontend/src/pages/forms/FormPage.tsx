import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { appHome } from "utils/me";
import { ArrowLeft, CheckCircle2, Loader2 } from "components/icons";
import {
  carryOver, getForm, getSuggestions, submitForm, validateAnswers,
  type Answer, type Answers, type FormDef, type FormQuestion,
} from "utils/forms";

/**
 * A form, filled out the way Google Forms is: a header card, one card per
 * question, "Section X of N" with Next / Back, "This is a required question"
 * under anything left empty, and a confirmation with "Submit another".
 *
 * Deliberately outside the app's sidebar layout -- installers open it on a
 * phone in the field, and field logins can reach this page and nothing else
 * but their shifts (app/auth/RoleGate.tsx). The questions come from the
 * database (backend/app/apis/forms), so this renders whatever the form holds.
 */

const DRAFT_KEY = (slug: string) => `ll-form-draft:${slug}`;
const SUGGEST_KEYS = new Set(["client_name", "project_name", "preferred_vendor"]);

function readDraft(slug: string): { answers: Answers; section: number } | null {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY(slug));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
function writeDraft(slug: string, answers: Answers, section: number) {
  try { sessionStorage.setItem(DRAFT_KEY(slug), JSON.stringify({ answers, section })); } catch { /* private mode */ }
}
function clearDraft(slug: string) {
  try { sessionStorage.removeItem(DRAFT_KEY(slug)); } catch { /* noop */ }
}

function Paragraphs({ text, className }: { text: string | null; className?: string }) {
  if (!text) return null;
  return (
    <div className={className}>
      {text.split(/\n+/).map((line, i) => <p key={i}>{line}</p>)}
    </div>
  );
}

const fieldBase =
  "w-full rounded-none border-0 border-b bg-transparent px-0 py-2 text-[15px] text-stone-800 outline-none transition-colors focus:border-b-2";

function QuestionCard({ q, value, error, suggestions, onChange }: {
  q: FormQuestion;
  value: Answer | undefined;
  error?: string;
  suggestions?: string[];
  onChange: (v: Answer) => void;
}) {
  const id = `q-${q.key}`;
  const lineColor = error ? "border-red-500 focus:border-red-600" : "border-stone-300 focus:border-emerald-700";
  const listId = suggestions && suggestions.length ? `${id}-list` : undefined;
  return (
    <section
      className={`rounded-lg border bg-white px-5 py-5 shadow-sm sm:px-6 ${error ? "border-red-400" : "border-stone-200"}`}
      aria-invalid={Boolean(error)}
    >
      <label htmlFor={q.type === "radio" || q.type === "checkboxes" ? undefined : id} className="block">
        <span className="whitespace-pre-line text-[15px] leading-snug text-stone-900">
          {q.label}
          {q.required && <span className="ml-1 text-red-600" aria-label="required">*</span>}
        </span>
        {q.helper_text && <span className="mt-1 block text-xs text-stone-500">{q.helper_text}</span>}
      </label>

      <div className="mt-4">
        {q.type === "short_text" && (
          <>
            <input
              id={id}
              type="text"
              value={(value as string) ?? ""}
              onChange={(e) => onChange(e.target.value)}
              list={listId}
              autoComplete="off"
              placeholder="Your answer"
              className={`${fieldBase} ${lineColor}`}
            />
            {listId && (
              <datalist id={listId}>
                {suggestions!.slice(0, 300).map((s) => <option key={s} value={s} />)}
              </datalist>
            )}
          </>
        )}
        {q.type === "long_text" && (
          <textarea
            id={id}
            rows={2}
            value={(value as string) ?? ""}
            onChange={(e) => {
              onChange(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`;
            }}
            placeholder="Your answer"
            className={`${fieldBase} ${lineColor} resize-none`}
          />
        )}
        {q.type === "date" && (
          <input
            id={id}
            type="date"
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            className={`${fieldBase} ${lineColor} max-w-[220px]`}
          />
        )}
        {q.type === "dropdown" && (
          <select
            id={id}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value || null)}
            className={`w-full max-w-xs rounded-md border bg-white px-3 py-2.5 text-[15px] outline-none focus:ring-2 focus:ring-emerald-200 ${error ? "border-red-500" : "border-stone-300"}`}
          >
            <option value="">Choose</option>
            {(q.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
        {q.type === "radio" && (
          <div role="radiogroup" className="space-y-1">
            {(q.options || []).map((o) => (
              <label key={o} className="flex cursor-pointer items-start gap-3 rounded-md px-1 py-2 hover:bg-stone-50">
                <input
                  type="radio"
                  name={id}
                  checked={value === o}
                  onChange={() => onChange(o)}
                  className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-700"
                />
                <span className="text-[14px] leading-snug text-stone-800">{o}</span>
              </label>
            ))}
          </div>
        )}
        {q.type === "checkboxes" && (
          <div className="space-y-1">
            {(q.options || []).map((o) => {
              const picked = Array.isArray(value) ? value : [];
              const on = picked.includes(o);
              return (
                <label key={o} className="flex cursor-pointer items-start gap-3 rounded-md px-1 py-2 hover:bg-stone-50">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => onChange(on ? picked.filter((x) => x !== o) : [...picked, o])}
                    className="mt-0.5 h-5 w-5 shrink-0 accent-emerald-700"
                  />
                  <span className="text-[14px] leading-snug text-stone-800">{o}</span>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {error && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-red-600" role="alert">
          <span aria-hidden className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-red-600 text-[10px] font-bold text-white">!</span>
          {error}
        </p>
      )}
    </section>
  );
}

export default function FormPage() {
  const { slug = "product-request" } = useParams();
  const [form, setForm] = useState<FormDef | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, string[]>>({});
  const draft = useMemo(() => readDraft(slug), [slug]);
  const [answers, setAnswers] = useState<Answers>(draft?.answers || {});
  const [sectionIdx, setSectionIdx] = useState(draft?.section || 0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState<Answers | null>(null);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getForm(slug).then(setForm).catch((e) => setLoadError(e.message || "This form could not be loaded."));
    getSuggestions(slug).then(setSuggestions).catch(() => {});
  }, [slug]);

  useEffect(() => { if (!done) writeDraft(slug, answers, sectionIdx); }, [slug, answers, sectionIdx, done]);

  const sections = form?.sections || [];
  const section = sections[sectionIdx];
  const sectionQs = useMemo(
    () => (form && section ? form.questions.filter((q) => q.section_id === section.id) : []),
    [form, section],
  );
  const last = sectionIdx === sections.length - 1;

  const scrollTop = () => {
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const setAnswer = (key: string, v: Answer) => {
    setAnswers((a) => ({ ...a, [key]: v }));
    if (errors[key]) setErrors((e) => { const n = { ...e }; delete n[key]; return n; });
  };

  const focusFirstError = (errs: Record<string, string>) => {
    const first = sectionQs.find((q) => errs[q.key]) || form?.questions.find((q) => errs[q.key]);
    if (first) document.getElementById(`q-${first.key}`)?.focus?.();
    setTimeout(() => document.querySelector("[aria-invalid='true']")?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  const next = () => {
    if (!form || !section) return;
    const errs = validateAnswers(form.questions, answers, section.id);
    setErrors(errs);
    if (Object.keys(errs).length) { focusFirstError(errs); return; }
    setSectionIdx((i) => i + 1);
    scrollTop();
  };
  const back = () => { setErrors({}); setSectionIdx((i) => Math.max(0, i - 1)); scrollTop(); };

  const submit = async () => {
    if (!form) return;
    const errs = validateAnswers(form.questions, answers);
    setErrors(errs);
    if (Object.keys(errs).length) {
      const firstSection = sections.findIndex((s) => form.questions.some((q) => q.section_id === s.id && errs[q.key]));
      if (firstSection >= 0 && firstSection !== sectionIdx) setSectionIdx(firstSection);
      focusFirstError(errs);
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await submitForm(slug, answers);
      clearDraft(slug);
      setDone(answers);
      scrollTop();
    } catch (e) {
      const err = e as Error & { detail?: { errors?: Record<string, string> } };
      if (err.detail && typeof err.detail === "object" && err.detail.errors) {
        setErrors(err.detail.errors);
        focusFirstError(err.detail.errors);
      } else {
        setSubmitError(err.message || "Could not submit. Check your connection and try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const startOver = (keep: Answers) => {
    setAnswers(keep);
    setErrors({});
    setSubmitError(null);
    setDone(null);
    // With the project kept, section 1 is already filled in -- go straight to the item.
    setSectionIdx(Object.keys(keep).length && sections.length > 1 ? 1 : 0);
    scrollTop();
  };

  const header = form && (
    <section className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
      <div className="h-2.5" style={{ backgroundColor: "rgb(var(--ll-brand))" }} />
      <div className="px-5 py-5 sm:px-6">
        <h1 className="text-[26px] leading-tight text-stone-900" style={{ fontFamily: "'Sora', system-ui, sans-serif" }}>
          {form.title}
        </h1>
        <Paragraphs text={form.description} className="mt-3 space-y-0.5 text-sm text-stone-700" />
        {!done && <p className="mt-4 border-t border-stone-100 pt-3 text-xs text-red-600">* Indicates required question</p>}
      </div>
    </section>
  );

  return (
    <div className="min-h-screen px-3 pb-24 pt-2 sm:px-4 sm:pt-4" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
      <div ref={topRef} className="mx-auto max-w-[640px] space-y-3">
        <Link to={appHome()} className="inline-flex items-center gap-1 px-1 py-2 text-xs font-medium text-emerald-800 hover:underline sm:py-0">
          <ArrowLeft size={12} /> Leaf &amp; Ledger
        </Link>

        {loadError && <div className="rounded-lg border border-red-200 bg-white p-5 text-sm text-red-700">{loadError}</div>}
        {!form && !loadError && (
          <div className="flex justify-center py-20"><Loader2 size={22} className="animate-spin text-emerald-700" /></div>
        )}

        {form && !form.is_accepting && !done && (
          <>
            {header}
            <section className="rounded-lg border border-stone-200 bg-white px-6 py-5 text-sm text-stone-700 shadow-sm">
              This form is no longer accepting responses. / Este formulario ya no acepta respuestas.
            </section>
          </>
        )}

        {form && form.is_accepting && done && (
          <>
            {header}
            <section className="rounded-lg border border-stone-200 bg-white px-6 py-6 shadow-sm">
              <p className="flex items-center gap-2 text-[15px] text-stone-900">
                <CheckCircle2 size={20} className="text-emerald-700" />
                Your response has been recorded.
              </p>
              <p className="mt-1 pl-7 text-sm text-stone-500">Su respuesta ha sido registrada.</p>
              <div className="mt-5 flex flex-col gap-3 pl-7 sm:flex-row sm:flex-wrap">
                <button
                  type="button"
                  onClick={() => startOver(carryOver(done))}
                  className="rounded-md px-4 py-2.5 text-sm font-semibold text-white"
                  style={{ backgroundColor: "rgb(var(--ll-brand))" }}
                >
                  Submit another for the same project
                </button>
                <button type="button" onClick={() => startOver({})} className="text-left text-sm font-medium text-emerald-800 underline underline-offset-2 sm:self-center">
                  Submit another response
                </button>
              </div>
              {done.client_name && (
                <p className="mt-4 pl-7 text-xs text-stone-500">
                  "Same project" keeps {[done.requestor, done.client_name, done.project_name].filter(Boolean).join(" · ")} and the location.
                </p>
              )}
            </section>
          </>
        )}

        {form && form.is_accepting && !done && section && (
          <>
            {header}
            <div className="px-1">
              <div className="flex items-center justify-between text-xs text-stone-600">
                <span>Section {sectionIdx + 1} of {sections.length}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/70">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${((sectionIdx + 1) / sections.length) * 100}%`, backgroundColor: "rgb(var(--ll-brand))" }}
                />
              </div>
            </div>
            {sectionIdx > 0 && (
              <section className="overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
                <div className="px-5 py-3 text-sm font-semibold text-white sm:px-6" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
                  {section.title}
                </div>
                <Paragraphs text={section.description} className="space-y-1 px-5 py-4 text-sm text-stone-700 sm:px-6" />
              </section>
            )}
            {sectionQs.map((q) => (
              <QuestionCard
                key={q.key}
                q={q}
                value={answers[q.key]}
                error={errors[q.key]}
                suggestions={SUGGEST_KEYS.has(q.key) ? suggestions[q.key] : undefined}
                onChange={(v) => setAnswer(q.key, v)}
              />
            ))}
            {submitError && <p className="px-1 text-sm text-red-700">{submitError}</p>}
            <div className="flex items-center gap-3 px-1 pt-1">
              {sectionIdx > 0 && (
                <button type="button" onClick={back} className="rounded-md border border-stone-300 bg-white px-5 py-2.5 text-sm font-semibold text-emerald-800">
                  Back
                </button>
              )}
              {!last ? (
                <button type="button" onClick={next} className="rounded-md px-6 py-2.5 text-sm font-semibold text-white" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
                  Next
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void submit()}
                  disabled={submitting}
                  className="rounded-md px-6 py-2.5 text-sm font-semibold text-white disabled:opacity-60"
                  style={{ backgroundColor: "rgb(var(--ll-brand))" }}
                >
                  {submitting ? "Submitting…" : "Submit"}
                </button>
              )}
              <button
                type="button"
                onClick={() => { setAnswers({}); setErrors({}); setSectionIdx(0); clearDraft(slug); }}
                className="ml-auto py-2 text-sm font-medium text-emerald-800 hover:underline"
              >
                Clear form
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
