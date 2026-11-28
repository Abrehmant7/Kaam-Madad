import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

import { clearDrafts } from "../features/drafts";

// The first (cold) run transforms every module; 1 s for findBy*/waitFor was too tight on slower machines.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  clearDrafts(); // unsent input is kept in memory between screens; each test starts empty
  window.localStorage.clear();
  document.documentElement.removeAttribute("lang");
  document.documentElement.removeAttribute("dir");
});
