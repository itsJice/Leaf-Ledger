import { RouterProvider } from "react-router-dom";
import { Head } from "./internal-components/Head";
import { OuterErrorBoundary } from "./prod-components/OuterErrorBoundary";
import { router } from "./router";
import { ThemeProvider } from "./internal-components/ThemeProvider";
import { DEFAULT_THEME } from "./constants/default-theme";
import { AuthProvider } from "app/auth/AuthProvider";
import { startEventLog } from "utils/eventLog";
import { handleFrameMessage } from "utils/scheduleFrameWatch";

// The error log and "last minute" trail (utils/eventLog.ts): errors, clicks,
// page changes, freezes. Started once, before the first render.
startEventLog(router);
// Errors and server calls reported by the Install Schedule's frame.
window.addEventListener("message", handleFrameMessage);

export const AppWrapper = () => {
  return (
    <OuterErrorBoundary>
      <AuthProvider>
        <ThemeProvider defaultTheme={DEFAULT_THEME}>
          <RouterProvider router={router} />
          <Head />
        </ThemeProvider>
      </AuthProvider>
    </OuterErrorBoundary>
  );
};
