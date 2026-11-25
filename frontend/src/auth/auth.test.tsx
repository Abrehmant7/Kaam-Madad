import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { en } from "../i18n/resources/en";
import { ur } from "../i18n/resources/ur";
import { bootHandlers, DEMO_CONFIG, errorEnvelope, jsonResponse, makeUser, mockApi } from "../test/http";
import { renderApp } from "../test/renderApp";

describe("route guards", () => {
  it("redirects anonymous visitors from a protected page to login with next", async () => {
    mockApi(bootHandlers());
    const { router } = renderApp("/worker", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["login.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("?next=%2Fworker");
  });

  it("sends a worker who opens the customer home back to the worker home (no loop)", async () => {
    mockApi(bootHandlers(makeUser({ role: "worker", preferred_language: "en" })));
    const { router } = renderApp("/customer", "en");
    expect(await screen.findByRole("heading", { level: 1, name: en["home.worker.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker");
    // The home lists future features as unavailable rather than showing fake data.
    expect(screen.getAllByText(en["common.notAvailableYet"])).toHaveLength(4);
  });

  it("applies the account language after session restore", async () => {
    mockApi(bootHandlers(makeUser({ role: "customer", preferred_language: "en" })));
    renderApp("/customer", "ur");
    expect(await screen.findByRole("heading", { level: 1, name: en["home.customer.title"] })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
  });

  it("shows a session-expired message when the server rejects the session", async () => {
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse(errorEnvelope("not_authenticated", "r1"), 401),
    });
    const { router } = renderApp("/account/phone", "en");
    expect(await screen.findByText(en["auth.sessionExpired"])).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toContain("expired=1");
  });

  it("logging out from a protected page lands on the landing page, not login", async () => {
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "POST /api/v1/auth/logout/": new Response(null, { status: 204 }),
      "GET /api/v1/health/ready/": jsonResponse({ status: "ok", checks: { database: "ok" } }),
    });
    const { router } = renderApp("/worker", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["nav.logout"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["landing.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(screen.queryByText(en["auth.sessionExpired"])).not.toBeInTheDocument();
  });

  it("explains a failed start-up check and recovers on retry", async () => {
    let fail = true;
    mockApi({
      ...bootHandlers(),
      "GET /api/v1/auth/me/": () => {
        if (fail) throw new TypeError("Failed to fetch");
        return jsonResponse({ authenticated: false, user: null });
      },
      "GET /api/v1/health/ready/": jsonResponse({ status: "ok", checks: { database: "ok" } }),
    });
    renderApp("/", "en");
    expect(await screen.findByText(en["auth.checkFailed"])).toBeInTheDocument();
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: en["common.retry"] }));
    await waitFor(() => expect(screen.queryByText(en["auth.checkFailed"])).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { level: 1, name: en["landing.title"] })).toBeInTheDocument();
  });
});

describe("login and signup", () => {
  it("shows translated invalid-credential errors, then logs in and goes home", async () => {
    let attempts = 0;
    const calls = mockApi({
      ...bootHandlers(),
      "POST /api/v1/auth/login/": () =>
        ++attempts === 1
          ? jsonResponse(errorEnvelope("invalid_credentials", "r2"), 400)
          : jsonResponse({ authenticated: true, user: makeUser({ preferred_language: "ur" }) }),
    });
    const { router } = renderApp("/login", "ur");
    await userEvent.type(await screen.findByLabelText(ur["signup.phoneLabel"]), "0300 1234567");
    await userEvent.type(screen.getByLabelText(ur["signup.passwordLabel"]), "Wrong-Pass-1");
    await userEvent.click(screen.getByRole("button", { name: ur["login.submit"] }));
    expect(await screen.findByText(ur["errors.invalid_credentials"])).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: ur["login.submit"] }));
    expect(await screen.findByRole("heading", { level: 1, name: ur["home.worker.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker");

    const login = calls.find((call) => call.method === "POST" && call.path === "/api/v1/auth/login/");
    expect(login?.headers["X-CSRFToken"]).toBe("test-csrf-token");
  });

  it("shows server field errors on signup and sends only allowed fields", async () => {
    const calls = mockApi({
      ...bootHandlers(),
      "POST /api/v1/auth/signup/": jsonResponse(
        errorEnvelope("validation_error", "r3", undefined, {
          phone_number: [{ code: "phone_taken", message: "exists" }],
          password: [{ code: "password_too_common", message: "common" }],
        }),
        400,
      ),
    });
    renderApp("/signup?role=customer", "en");
    await userEvent.type(await screen.findByLabelText(en["signup.phoneLabel"]), "03001234567");
    await userEvent.type(screen.getByLabelText(en["signup.passwordLabel"]), "password123");
    await userEvent.type(screen.getByLabelText(en["signup.passwordConfirmLabel"]), "password123");
    await userEvent.click(screen.getByRole("button", { name: en["signup.submit"] }));

    expect(await screen.findByText(en["fieldErrors.phone_taken"])).toBeInTheDocument();
    expect(screen.getByText(en["fieldErrors.password_too_common"])).toBeInTheDocument();
    expect(screen.getByLabelText(en["signup.phoneLabel"])).toHaveAttribute("aria-invalid", "true");

    const sent = calls.find((call) => call.path === "/api/v1/auth/signup/")?.body as Record<string, unknown>;
    expect(Object.keys(sent).sort()).toEqual(["password", "password_confirm", "phone_number", "preferred_language", "role"]);
    expect(sent.role).toBe("customer");
    expect(sent.preferred_language).toBe("en");
  });

  it("goes to phone confirmation after a successful signup (guard does not race the form)", async () => {
    mockApi({
      ...bootHandlers(),
      "POST /api/v1/auth/signup/": jsonResponse({ authenticated: true, user: makeUser({ preferred_language: "en" }) }, 201),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse({
        status: "unconfirmed", method: null, confirmed_at: null, provider: DEMO_CONFIG.phone_verification, active_code: null,
      }),
    });
    const { router } = renderApp("/signup?role=worker", "en");
    await userEvent.type(await screen.findByLabelText(en["signup.phoneLabel"]), "03001234567");
    await userEvent.type(screen.getByLabelText(en["signup.passwordLabel"]), "Strong-Pass-2026");
    await userEvent.type(screen.getByLabelText(en["signup.passwordConfirmLabel"]), "Strong-Pass-2026");
    await userEvent.click(screen.getByRole("button", { name: en["signup.submit"] }));
    expect(await screen.findByText(en["signup.success"])).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account/phone");
  });

  it("returns to ?next= after login", async () => {
    mockApi({
      ...bootHandlers(),
      "POST /api/v1/auth/login/": jsonResponse({ authenticated: true, user: makeUser({ preferred_language: "en" }) }),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse({
        status: "unconfirmed", method: null, confirmed_at: null, provider: DEMO_CONFIG.phone_verification, active_code: null,
      }),
    });
    const { router } = renderApp("/login?next=%2Faccount%2Fphone", "en");
    await userEvent.type(await screen.findByLabelText(en["signup.phoneLabel"]), "03001234567");
    await userEvent.type(screen.getByLabelText(en["signup.passwordLabel"]), "Strong-Pass-2026");
    await userEvent.click(screen.getByRole("button", { name: en["login.submit"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["phone.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/account/phone");
  });

  it("ignores an external ?next= target", async () => {
    mockApi({
      ...bootHandlers(),
      "POST /api/v1/auth/login/": jsonResponse({ authenticated: true, user: makeUser({ preferred_language: "en" }) }),
    });
    const { router } = renderApp("/login?next=%2F%2Fevil.example", "en");
    await userEvent.type(await screen.findByLabelText(en["signup.phoneLabel"]), "03001234567");
    await userEvent.type(screen.getByLabelText(en["signup.passwordLabel"]), "Strong-Pass-2026");
    await userEvent.click(screen.getByRole("button", { name: en["login.submit"] }));
    expect(await screen.findByRole("heading", { level: 1, name: en["home.worker.title"] })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/worker");
  });

  it("validates locally before calling the server", async () => {
    const calls = mockApi(bootHandlers());
    renderApp("/signup", "en");
    await userEvent.click(await screen.findByRole("button", { name: en["signup.submit"] }));
    expect(screen.getByText(en["errors.validation_error"])).toBeInTheDocument();
    expect(calls.some((call) => call.path === "/api/v1/auth/signup/")).toBe(false);
  });
});

describe("language switch", () => {
  it("saves the language to the account when signed in", async () => {
    const calls = mockApi({
      ...bootHandlers(makeUser({ preferred_language: "ur" })),
      "PATCH /api/v1/auth/me/language/": jsonResponse({ authenticated: true, user: makeUser({ preferred_language: "en" }) }),
    });
    renderApp("/worker", "ur");
    await screen.findByRole("heading", { level: 1, name: ur["home.worker.title"] });
    await userEvent.click(screen.getByRole("button", { name: ur["nav.changeLanguage"].replace("{language}", "English") }));
    expect(await screen.findByRole("heading", { level: 1, name: en["home.worker.title"] })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(window.localStorage.getItem("rr.language")).toBe("en");
    await waitFor(() =>
      expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ preferred_language: "en" }),
    );
  });

  it("only changes the device setting for anonymous visitors", async () => {
    const calls = mockApi({ ...bootHandlers(), "GET /api/v1/health/ready/": jsonResponse({ status: "ok", checks: {} }) });
    renderApp("/", "ur");
    await userEvent.click(await screen.findByRole("button", { name: ur["nav.changeLanguage"].replace("{language}", "English") }));
    expect(await screen.findByRole("heading", { level: 1, name: en["landing.title"] })).toBeInTheDocument();
    expect(calls.some((call) => call.method === "PATCH")).toBe(false);
  });
});

describe("phone confirmation", () => {
  const unconfirmed = {
    status: "unconfirmed",
    method: null,
    confirmed_at: null,
    provider: DEMO_CONFIG.phone_verification,
    active_code: null,
  };
  const activeCode = {
    id: "c1",
    method: "demo",
    expires_at: "2026-11-25T10:10:00+00:00",
    expires_in_seconds: 600,
    attempts_remaining: 5,
    resend_available_in_seconds: 60,
  };

  it("runs the labelled demo flow and never presents it as real verification", async () => {
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse(unconfirmed),
      "POST /api/v1/auth/phone-confirmation/": jsonResponse(
        { ...unconfirmed, active_code: activeCode, demo: { code: "482913", notice: "DEMO ONLY" } },
        201,
      ),
      "POST /api/v1/auth/phone-confirmation/verify/": jsonResponse({
        authenticated: true,
        user: makeUser({ preferred_language: "en", phone_confirmation: { status: "confirmed", method: "demo", confirmed_at: "x" } }),
      }),
    });
    renderApp("/account/phone", "en");
    expect(await screen.findByText(en["phone.demoExplainer"])).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["phone.sendDemoCode"] }));
    expect(await screen.findByText(en["phone.demoCodeLabel"])).toBeInTheDocument();
    expect(screen.getByText("482913")).toBeInTheDocument();

    // Confirmation state comes from the server after verifying.
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "POST /api/v1/auth/phone-confirmation/verify/": jsonResponse({
        authenticated: true,
        user: makeUser({ preferred_language: "en", phone_confirmation: { status: "confirmed", method: "demo", confirmed_at: "x" } }),
      }),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse({ ...unconfirmed, status: "confirmed", method: "demo", confirmed_at: "x" }),
    });
    await userEvent.type(screen.getByLabelText(en["phone.codeLabel"]), "482913");
    await userEvent.click(screen.getByRole("button", { name: en["phone.verify"] }));
    expect(await screen.findByText(en["phone.confirmedSuccess"])).toBeInTheDocument();
    expect(screen.getByText(en["phone.status.confirmedDemo"])).toBeInTheDocument();
    expect(screen.queryByText(en["phone.status.confirmedSms"])).not.toBeInTheDocument();
  });

  it("is honest when no SMS provider is configured", async () => {
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse({
        ...unconfirmed,
        provider: { provider: "unconfigured", available: false, simulated: false },
      }),
    });
    renderApp("/account/phone", "en");
    expect(await screen.findByText(en["phone.unavailable"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["phone.sendCode"] })).not.toBeInTheDocument();
  });

  it("translates a wrong code with attempts left", async () => {
    mockApi({
      ...bootHandlers(makeUser({ preferred_language: "en" })),
      "GET /api/v1/auth/phone-confirmation/": jsonResponse({ ...unconfirmed, active_code: { ...activeCode, attempts_remaining: 4 } }),
      "POST /api/v1/auth/phone-confirmation/verify/": jsonResponse(
        errorEnvelope("code_incorrect", "r4", { attempts_remaining: 4 }),
        400,
      ),
    });
    renderApp("/account/phone", "en");
    await userEvent.type(await screen.findByLabelText(en["phone.codeLabel"]), "000000");
    await userEvent.click(screen.getByRole("button", { name: en["phone.verify"] }));
    expect(await screen.findByText(en["errors.code_incorrect"].replace("{attempts}", "4"))).toBeInTheDocument();
  });
});
