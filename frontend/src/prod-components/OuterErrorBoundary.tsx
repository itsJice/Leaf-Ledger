import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { CrashScreen } from "components/CrashScreen";
import { errorDetail, reportEvent } from "utils/eventLog";

interface Props {
  children: ReactNode;
}

/**
 * The last line of defence around the whole app. It used to render nothing
 * (a blank screen) and write the error only to that person's browser
 * console, where it was lost when they closed the tab. Now the crash goes to
 * the error log and they get the crash screen.
 */
export const OuterErrorBoundary = ({ children }: Props) => {
  return (
    <ErrorBoundary
      fallback={<CrashScreen />}
      onError={(error, info) => {
        console.error("Caught error in AppWrapper", error.message, error.stack);
        reportEvent({
          kind: "crash",
          message: error.message || "The app crashed",
          detail: { ...errorDetail(error), component_stack: (info?.componentStack || "").slice(0, 1500) },
        });
      }}
    >
      {children}
    </ErrorBoundary>
  );
};
