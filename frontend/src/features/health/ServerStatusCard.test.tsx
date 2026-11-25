import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { en } from "../../i18n/resources/en";
import { ur } from "../../i18n/resources/ur";
import type { Language } from "../../i18n/types";
import { errorEnvelope, jsonResponse } from "../../test/http";
import { ServerStatusCard } from "./ServerStatusCard";

function renderCard(language: Language = "ur") {
  return render(
    <I18nProvider initialLanguage={language}>
      <ServerStatusCard />
    </I18nProvider>,
  );
}

describe("ServerStatusCard", () => {
  it("shows a loading state, then success in Urdu", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => (resolve = r))));

    renderCard("ur");
    expect(screen.getByRole("status")).toHaveTextContent(ur["status.checking"]);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();

    resolve(jsonResponse({ status: "ok", checks: { database: "ok" } }));
    expect(await screen.findByText(ur["status.ready"])).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("explains a database outage and shows the reference number", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(errorEnvelope("service_not_ready", "4f0c-req", { checks: { database: "unavailable" } }), 503),
      ),
    );

    renderCard("en");
    expect(await screen.findByText(en["status.notReady"])).toBeInTheDocument();
    expect(screen.getByText("4f0c-req")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["status.retry"] })).toBeInTheDocument();
  });

  it("reports a connection failure and recovers after retry", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse({ status: "ok", checks: { database: "ok" } }));
    vi.stubGlobal("fetch", fetchMock);

    renderCard("en");
    expect(await screen.findByText(en["status.unreachable"])).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: en["status.retry"] }));
    expect(await screen.findByText(en["status.ready"])).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not claim success for an unexpected response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ something: "else" })));
    renderCard("en");
    expect(await screen.findByText(en["status.unexpected"])).toBeInTheDocument();
    expect(screen.queryByText(en["status.ready"])).not.toBeInTheDocument();
  });
});
