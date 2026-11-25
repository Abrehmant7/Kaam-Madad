import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { AuthProvider } from "../auth/AuthProvider";
import { I18nProvider } from "../i18n/I18nProvider";
import type { Language } from "../i18n/types";
import { routes } from "../routes";

/** Render the real route tree at `path` with real providers (network is stubbed by mockApi). */
export function renderApp(path: string, language?: Language) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const utils = render(
    <I18nProvider initialLanguage={language}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </I18nProvider>,
  );
  return { ...utils, router };
}
