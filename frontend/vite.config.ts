import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// Paths the dev server forwards to Django so the browser sees ONE origin
// (http://localhost:5173), exactly like production where Django serves both
// the built frontend and the API. Session/CSRF cookies therefore behave the same.
const BACKEND_PATHS = ["/api", "/admin", "/static"];

export default defineConfig(({ mode }) => {
  // Loads frontend/.env* files. DEV_BACKEND_URL has no VITE_ prefix, so it is
  // never exposed to browser code.
  const env = loadEnv(mode, import.meta.dirname, "");
  const backendUrl = env.DEV_BACKEND_URL || "http://127.0.0.1:8000";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      // Keep the browser's Host header so Django sees the same origin as the page.
      proxy: Object.fromEntries(BACKEND_PATHS.map((path) => [path, { target: backendUrl, changeOrigin: false }])),
    },
    preview: {
      port: 4173,
      strictPort: true,
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      sourcemap: false,
    },
  };
});
