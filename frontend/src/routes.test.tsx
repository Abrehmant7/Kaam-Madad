import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { en } from "./i18n/resources/en";
import { ur } from "./i18n/resources/ur";
import { bootHandlers, jsonResponse, makeUser, mockApi } from "./test/http";
import { renderApp } from "./test/renderApp";

const READY = { "GET /api/v1/health/ready/": jsonResponse({ status: "ok", checks: { database: "ok" } }) };
const DEMO_WORDS = /demo|ڈیمو/i;

describe("routes", () => {
  it("renders the Urdu landing page for anonymous visitors without demo branding or server diagnostics", async () => {
    const calls = mockApi({ ...bootHandlers(), ...READY });
    renderApp("/", "ur");
    expect(await screen.findByRole("heading", { level: 1, name: ur["landing.title"] })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: ur["landing.needWork"] })[0]).toHaveAttribute("href", "/signup?role=worker");
    expect(screen.getAllByRole("link", { name: ur["landing.needWorker"] })[0]).toHaveAttribute("href", "/signup?role=customer");
    expect(document.body.textContent).not.toMatch(DEMO_WORDS);
    expect(screen.queryByText(ur["status.heading"])).not.toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/v1/health/ready/")).toBe(false);
  });

  it("keeps the server status for developers on /diagnostics, outside the navigation", async () => {
    mockApi({ ...bootHandlers(), ...READY });
    renderApp("/diagnostics", "en");
    expect(await screen.findByRole("heading", { level: 1, name: "Diagnostics" })).toBeInTheDocument();
    expect(await screen.findByText(en["status.ready"])).toBeInTheDocument();
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
