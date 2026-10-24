import { useEffect } from "react";
import { withSiteName } from "./routes";

/** Keeps the browser tab, history and screen-reader page title in step with the route. */
export function useDocumentTitle(title: string | undefined): void {
  useEffect(() => {
    if (title) document.title = withSiteName(title);
  }, [title]);
}
