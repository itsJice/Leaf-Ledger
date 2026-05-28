import { RouterProvider } from "react-router-dom";
import { Head } from "./internal-components/Head";
import { OuterErrorBoundary } from "./prod-components/OuterErrorBoundary";
import { router } from "./router";
import { ThemeProvider } from "./internal-components/ThemeProvider";
import { DEFAULT_THEME } from "./constants/default-theme";
import { StackProvider} from "@stackframe/react";
import { stackClientApp } from "app/auth";


export const AppWrapper = () => {
  return (
    <OuterErrorBoundary>
      <StackProvider app={stackClientApp}>
      <ThemeProvider defaultTheme={DEFAULT_THEME}>
        <RouterProvider router={router} />
        <Head />
      </ThemeProvider>
      </StackProvider>
    </OuterErrorBoundary>
  );
};