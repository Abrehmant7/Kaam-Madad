import { Link } from "react-router";

import { PATHS } from "../auth/paths";
import { useAuth } from "../auth/context";
import { ServerStatusCard } from "../features/health/ServerStatusCard";

/**
 * Developer diagnostics, outside the normal navigation (open /diagnostics directly): server and database readiness,
 * the deployment mode and AI provider configuration the server reports, and the voice test page. Plain English only:
 * this is for the people running the app, not for customers or workers.
 */
export function DiagnosticsPage() {
  const { config, user } = useAuth();
  const providers = { ...(config?.ai ?? {}), ...(config?.identity_verification ? { identity_verification: config.identity_verification } : {}) };
  return (
    <div lang="en" dir="ltr" className="max-w-3xl space-y-4 font-sans">
      <h1 className="text-2xl font-bold">Diagnostics</h1>
      <p className="text-muted">For developers. Not linked from the app.</p>
      <ServerStatusCard />
      <section className="card space-y-2 p-4">
        <h2 className="text-lg font-bold">Configuration reported by the server</h2>
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted">Deployment mode</dt>
          <dd className="font-bold">{config?.deployment_mode ?? "unknown"}</dd>
          {Object.entries(providers).map(([name, value]) => (
            <div key={name} className="contents">
              <dt className="text-muted">{name}</dt>
              <dd className="font-bold">{value?.provider ?? "—"}{value?.simulated ? " (simulated)" : ""}{value?.available === false ? " (unavailable)" : ""}</dd>
            </div>
          ))}
        </dl>
      </section>
      {user ? (
        <Link to={PATHS.voiceTest} className="inline-flex min-h-11 items-center font-bold text-primary underline-offset-4 hover:underline">Voice test page</Link>
      ) : (
        <p className="text-sm text-muted">Log in to open the voice test page ({PATHS.voiceTest}).</p>
      )}
    </div>
  );
}
