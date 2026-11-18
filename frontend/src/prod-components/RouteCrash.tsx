import { useEffect } from "react";
import { useRouteError } from "react-router-dom";
import { CrashScreen } from "components/CrashScreen";
import { errorDetail, isChunkLoadErrorMessage, reportEvent } from "utils/eventLog";

/**
 * The router's error screen for every route. Before this, a page that threw
 * while drawing showed React Router's built-in "Unexpected Application
 * Error!" text, and nothing was written down.
 */
export default function RouteCrash() {
  const error = useRouteError();
  const message = error instanceof Error ? error.message : String((error as { statusText?: string })?.statusText ?? error ?? "");
  const newVersion = isChunkLoadErrorMessage(message);
  useEffect(() => {
    reportEvent({
      kind: "crash",
      message: newVersion ? `Couldn't load the new version: ${message}` : message || "The page crashed",
      detail: errorDetail(error),
    });
  }, [error, message, newVersion]);
  return <CrashScreen newVersion={newVersion} />;
}
