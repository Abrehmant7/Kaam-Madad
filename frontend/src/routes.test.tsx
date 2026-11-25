import { render, screen } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "./i18n/I18nProvider";
import { ur } from "./i18n/resources/ur";
import { routes } from "./routes";
import { jsonResponse } from "./test/http";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <I18nProvider initialLanguage="ur">
      <RouterProvider router={router} />
    </I18nProvider>,
  );
}

describe("routes", () => {
  it("renders the Urdu landing page inside the app shell", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ status: "ok", checks: { database: "ok" } })));
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1, name: ur["landing.title"] })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: ur["nav.home"] })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(await screen.findByText(ur["status.ready"])).toBeInTheDocument();
  });

  it("renders a not-found page for unknown routes", () => {
    renderAt("/does/not/exist");
    expect(screen.getByRole("heading", { level: 1, name: ur["notFound.title"] })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: ur["notFound.home"] })).toHaveAttribute("href", "/");
  });
});
