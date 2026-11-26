import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { en } from "./i18n/resources/en";
import { ur } from "./i18n/resources/ur";
import { bootHandlers, jsonResponse, makeUser, mockApi } from "./test/http";
import { renderApp } from "./test/renderApp";

const READY = { "GET /api/v1/health/ready/": jsonResponse({ status: "ok", checks: { database: "ok" } }) };

describe("routes", () => {
  it("renders the Urdu landing page with demo label for anonymous visitors", async () => {
    mockApi({ ...bootHandlers(), ...READY });
    renderApp("/", "ur");
    expect(await screen.findByRole("heading", { level: 1, name: ur["landing.title"] })).toBeInTheDocument();
    expect(screen.getByText(ur["demo.banner"])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: ur["landing.needWork"] })).toHaveAttribute("href", "/signup?role=worker");
    expect(screen.getByRole("link", { name: ur["landing.needWorker"] })).toHaveAttribute("href", "/signup?role=customer");
    expect(await screen.findByText(ur["status.ready"])).toBeInTheDocument();
  });

  it("renders a not-found page for unknown routes", async () => {
    mockApi(bootHandlers());
    renderApp("/does/not/exist", "ur");
    expect(await screen.findByRole("heading", { level: 1, name: ur["notFound.title"] })).toBeInTheDocument();
  });

  it("sends signed-in users from the landing page to their role home", async () => {
    mockApi(bootHandlers(makeUser({ role: "customer", preferred_language: "en" })));
    const { router } = renderApp("/", "ur");
    expect(await screen.findByRole("heading", { level: 1, name: en["home.customer.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/customer");
  });
});
