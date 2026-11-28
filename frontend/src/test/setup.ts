import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// The first (cold) run transforms every module; 1 s for findBy*/waitFor was too tight on slower machines.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  document.documentElement.removeAttribute("lang");
  document.documentElement.removeAttribute("dir");
});
