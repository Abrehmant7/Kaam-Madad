import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { en } from "../../i18n/resources/en";
import { ur } from "../../i18n/resources/ur";
import { KNOWN_ICON_IDS } from "../catalogIcons";
import { AudioButton } from "./AudioButton";
import { IconTileGroup } from "./IconTile";
import { PasswordField } from "./TextField";

const wrap = (node: React.ReactNode) => render(<I18nProvider initialLanguage="en">{node}</I18nProvider>);

describe("AudioButton", () => {
  it("renders nothing when there is no audio", () => {
    const { container } = wrap(<AudioButton label="Instructions" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("plays through a handler with an accessible label", async () => {
    const onPlay = vi.fn().mockResolvedValue(undefined);
    wrap(<AudioButton label="Instructions" onPlay={onPlay} />);
    await userEvent.click(screen.getByRole("button", { name: `${en["audio.play"]}: Instructions` }));
    expect(onPlay).toHaveBeenCalledOnce();
  });

  it("shows a readable fallback when playback fails", async () => {
    wrap(<AudioButton label="Instructions" onPlay={() => Promise.reject(new Error("no voice"))} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent(en["audio.failed"]);
    expect(screen.getByRole("button")).toBeEnabled(); // retry stays possible
  });
});

describe("IconTileGroup", () => {
  function Single() {
    const [value, setValue] = useState<string[]>([]);
    return (
      <IconTileGroup
        label="Role"
        mode="single"
        value={value}
        onChange={setValue}
        options={[
          { value: "a", label: "Alpha", icon: <span /> },
          { value: "b", label: "Beta", icon: <span /> },
        ]}
      />
    );
  }

  function Multiple() {
    const [value, setValue] = useState<string[]>(["a"]);
    return (
      <IconTileGroup
        label="Services"
        mode="multiple"
        value={value}
        onChange={setValue}
        options={[
          { value: "a", label: "Alpha", icon: <span /> },
          { value: "b", label: "Beta", icon: <span /> },
        ]}
      />
    );
  }

  it("behaves as a labelled radio group with a visible selected label", async () => {
    wrap(<Single />);
    expect(screen.getByRole("radiogroup", { name: "Role" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /Beta/ }));
    expect(screen.getByRole("radio", { name: /Beta/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Alpha/ })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(en["common.selected"])).toBeInTheDocument();
  });

  it("supports multiple selection with toggle buttons", async () => {
    wrap(<Multiple />);
    await userEvent.click(screen.getByRole("button", { name: /Beta/ }));
    await userEvent.click(screen.getByRole("button", { name: /Alpha/ }));
    expect(screen.getByRole("button", { name: /Beta/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /Alpha/ })).toHaveAttribute("aria-pressed", "false");
  });
});

describe("PasswordField", () => {
  it("toggles visibility with an accessible button", async () => {
    wrap(<PasswordField label="Password" value="secret" onChange={() => {}} />);
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");
    expect(input).toHaveAttribute("dir", "ltr");
    await userEvent.click(screen.getByRole("button", { name: en["password.show"] }));
    expect(input).toHaveAttribute("type", "text");
  });

  it.each(["en", "ur"] as const)("keeps descriptions and keyboard toggling accessible in %s", async (language) => {
    const user = userEvent.setup();
    const messages = language === "ur" ? ur : en;
    const password = "Long-Sample-Password-2026-".repeat(4);
    render(
      <I18nProvider initialLanguage={language}>
        <PasswordField
          label={messages["signup.passwordLabel"]}
          value={password}
          onChange={() => {}}
          hint={messages["signup.passwordHint"]}
          hintPosition="after"
          errors={[messages["fieldErrors.password_too_common"]]}
          autoComplete="new-password"
        />
      </I18nProvider>,
    );
    const input = screen.getByLabelText(messages["signup.passwordLabel"]);
    expect(input).toHaveAccessibleDescription(
      `${messages["signup.passwordHint"]} ${messages["fieldErrors.password_too_common"]}`,
    );
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("autocomplete", "new-password");
    expect(input).toHaveValue(password);

    await user.tab();
    expect(input).toHaveFocus();
    await user.tab();
    const toggle = screen.getByRole("button", { name: messages["password.show"] });
    expect(toggle).toHaveFocus();
    await user.keyboard(" ");
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("dir", "ltr");
    expect(input).toHaveValue(password);
    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAccessibleName(messages["password.hide"]);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await user.keyboard(" ");
    expect(input).toHaveAttribute("type", "password");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
  });
});

describe("catalog icons", () => {
  it("covers every backend icon identifier", () => {
    // Keep in sync with backend/apps/catalog/icons.py.
    const backend = [
      "zap", "wrench", "snowflake", "cable", "plug", "lightbulb", "fan", "battery", "toggle", "droplet",
      "shower", "waves", "cylinder", "cog", "flame", "bath", "spray", "gauge", "thermometer",
      "circuit_board", "truck", "wind", "hammer", "map_pin", "building",
    ];
    expect([...KNOWN_ICON_IDS].sort()).toEqual([...backend].sort());
  });
});
