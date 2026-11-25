import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { type I18nContextValue, interpolate, useI18n } from "./context";
import { I18nProvider } from "./I18nProvider";
import { en } from "./resources/en";
import { ur } from "./resources/ur";

let captured: I18nContextValue | null = null;

function Probe() {
  captured = useI18n();
  return <p>{captured.t("app.name")}</p>;
}

describe("I18nProvider", () => {
  it("defaults to Urdu with right-to-left document direction", () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByText(ur["app.name"])).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("lang", "ur");
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
  });

  it("switches to English left-to-right and remembers the choice", () => {
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    act(() => captured?.setLanguage("en"));
    expect(screen.getByText(en["app.name"])).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("lang", "en");
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    expect(window.localStorage.getItem("rr.language")).toBe("en");
  });

  it("restores a stored language and ignores invalid stored values", () => {
    window.localStorage.setItem("rr.language", "en");
    const { unmount } = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(document.documentElement).toHaveAttribute("dir", "ltr");
    unmount();

    window.localStorage.setItem("rr.language", "fr");
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
  });

  it("has the same keys and no empty strings in Urdu and English", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(ur).sort());
    for (const value of [...Object.values(ur), ...Object.values(en)]) {
      expect(value.trim()).not.toBe("");
    }
  });

  it("interpolates named placeholders", () => {
    expect(interpolate("{count} workers in {area}", { count: 3, area: "G-9" })).toBe("3 workers in G-9");
    expect(interpolate("missing {x}", {})).toBe("missing {x}");
  });
});
