import type { User } from "@supabase/supabase-js";
import type * as React from "react";
import { createContext, useContext } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";

type UserGuardContextType = {
  user: User;
};

const UserGuardContext = createContext<UserGuardContextType | undefined>(
  undefined,
);

/**
 * Hook to access the logged in user from within a <UserGuard> component.
 */
export const useUserGuardContext = () => {
  const context = useContext(UserGuardContext);

  if (context === undefined) {
    throw new Error("useUserGuardContext must be used within a <UserGuard>");
  }

  return context;
};

/**
 * Blocks everything behind it until someone is signed in.
 *
 * While the session is still being restored we render a loader rather than
 * redirecting — otherwise refreshing a page would bounce a signed-in user out
 * to the login screen for a moment.
 */
export const UserGuard = (props: {
  children: React.ReactNode;
}) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#f7f6f2]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[#1f3d2b] border-t-transparent" />
          <p className="text-sm text-[#1f3d2b]/70">Loading…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    // Remember where they were headed so we can return them there after login.
    const next = `${location.pathname}${location.search}`;
    const params =
      next && next !== "/" ? `?next=${encodeURIComponent(next)}` : "";
    return <Navigate to={`/login${params}`} replace />;
  }

  return (
    <UserGuardContext.Provider value={{ user }}>
      {props.children}
    </UserGuardContext.Provider>
  );
};
