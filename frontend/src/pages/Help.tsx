import { useCallback, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, HelpCircle } from "components/icons";
import Layout from "components/Layout";
import { HOWTO_VIDEOS } from "../data/howtoVideos";
import { DISPLAY_HOME, FIELD_HOME, currentMe } from "utils/me";
import type { CategoryFilter } from "utils/howto";
import { HowToVideosView } from "./help/HowToVideosView";

/**
 * Help > How-to videos: short videos of the app's own screens, from the list
 * in data/howtoVideos.ts. Open to every signed-in role, field logins and the
 * display included (app/auth/RoleGate.tsx). `?v=<id>` opens one straight away,
 * so a video can be sent as a link.
 */
export default function Help() {
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  // True once a card is clicked: YouTube embeds may autoplay then, not from a ?v= link.
  const [clicked, setClicked] = useState(false);
  const openId = params.get("v");
  const me = currentMe();
  // Field and display logins have no sidebar: give them the way back.
  const back = me?.fieldOnly
    ? { to: FIELD_HOME, label: "My shifts" }
    : me?.viewOnly
      ? { to: DISPLAY_HOME, label: "Schedule" }
      : null;

  const onOpen = useCallback(
    (id: string) => {
      setClicked(true);
      setParams((p) => { const n = new URLSearchParams(p); n.set("v", id); return n; }, { replace: true });
    },
    [setParams],
  );
  const onClose = useCallback(() => {
    setClicked(false);
    setParams((p) => { const n = new URLSearchParams(p); n.delete("v"); return n; }, { replace: true });
  }, [setParams]);

  return (
    <Layout>
      <header
        className="sticky top-0 z-10 border-b border-stone-200 px-4 py-3 sm:px-10 sm:py-5"
        style={{ backgroundColor: "rgb(var(--ll-page))" }}
      >
        <div className="flex items-center gap-2">
          {back && (
            <Link
              to={back.to}
              className="-ml-2 flex h-10 flex-none items-center gap-1 rounded-lg px-2 text-sm font-semibold text-emerald-700 hover:bg-emerald-50"
            >
              <ArrowLeft size={16} /> {back.label}
            </Link>
          )}
          <h1
            className="flex min-w-0 flex-1 items-center gap-2 text-lg font-semibold text-stone-800 sm:text-xl"
            style={{ fontFamily: "'Sora', system-ui, sans-serif" }}
          >
            <HelpCircle size={18} className="flex-none text-emerald-700" />
            <span className="truncate">How-to videos</span>
          </h1>
        </div>
        <p className="mt-0.5 hidden text-xs text-stone-500 sm:block">
          Short videos that show how to do things in Leaf &amp; Ledger.
        </p>
      </header>
      <HowToVideosView
        videos={HOWTO_VIDEOS}
        query={query}
        category={category}
        openId={openId}
        autoplay={clicked}
        onQuery={setQuery}
        onCategory={setCategory}
        onOpen={onOpen}
        onClose={onClose}
      />
    </Layout>
  );
}
