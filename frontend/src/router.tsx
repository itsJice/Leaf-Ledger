import { lazy, type ReactNode, Suspense } from "react";
import { createBrowserRouter, Outlet } from "react-router-dom";
import { userRoutes } from "./user-routes";
import { AppProvider } from "components/AppProvider";
import { UserGuard } from "app/auth/UserGuard";

export const SuspenseWrapper = ({ children }: { children: ReactNode }) => {
  return <Suspense>{children}</Suspense>;
};

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
          <SuspenseWrapper>
            <Outlet />
          </SuspenseWrapper>
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
