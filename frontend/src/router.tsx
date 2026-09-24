import { lazy, type ReactNode, Suspense, useEffect, useState } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { userRoutes } from "./user-routes";
import { AppProvider } from "components/AppProvider";
import Layout from "components/Layout";
import { UserGuard } from "app/auth/UserGuard";
import { preloadPagesWhenIdle } from "./utils/preloadPages";

export const SuspenseWrapper = ({ children }: { children: ReactNode }) => {
  return <Suspense>{children}</Suspense>;
};

/**
 * What a signed-in user sees while a page chunk is still downloading (first
 * visit to a tab). Without this the router rendered nothing at all: the
 * sidebar vanished and the whole screen flashed white for the length of the
 * download, because every page brings its own <Layout>. Keeping the shell on
 * screen turns that into "the content area is empty for a moment". The
 * spinner only appears if the wait passes 200ms, so a fast load shows
 * nothing rather than a flash of spinner.
 */
function PageLoading() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setSlow(true), 200);
    return () => window.clearTimeout(t);
  }, []);
  return (
    <div className="flex h-full items-center justify-center" aria-busy="true">
      {slow && <Loader2 size={22} className="animate-spin text-stone-300" />}
    </div>
  );
}

function PageShell() {
  return (
    <Layout>
      <PageLoading />
    </Layout>
  );
}

/** Fetches every page chunk in the background once the shell is up. */
function PagePreloader() {
  useEffect(() => {
    preloadPagesWhenIdle();
  }, []);
  return null;
}

const NotFoundPage = lazy(() => import("./pages/NotFoundPage"));
const SomethingWentWrongPage = lazy(
  () => import("./pages/SomethingWentWrongPage"),
);
const Login = lazy(() => import("./pages/Login"));

export const router = createBrowserRouter([
  // The only page reachable without signing in.
  {
    path: "/login",
    element: (
      <SuspenseWrapper>
        <Login />
      </SuspenseWrapper>
    ),
  },
  {
    // Everything below requires a signed-in user.
    element: (
      <AppProvider>
        <UserGuard>
          <PagePreloader />
          <Suspense fallback={<PageShell />}>
            <Outlet />
          </Suspense>
        </UserGuard>
      </AppProvider>
    ),
    children: userRoutes,
  },
  {
    path: "*",
    element: (
      <SuspenseWrapper>
        <NotFoundPage />
      </SuspenseWrapper>
    ),
    errorElement: (
      <SuspenseWrapper>
        <SomethingWentWrongPage />
      </SuspenseWrapper>
    ),
  },
]);
