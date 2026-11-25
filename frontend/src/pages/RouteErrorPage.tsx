import { RefreshIcon, WarningIcon } from "../components/icons";
import { useI18n } from "../i18n/context";

/** Shown when a route fails to render. Never displays internal error details. */
export function RouteErrorPage() {
  const { t } = useI18n();

  return (
    <main className="mx-auto w-full max-w-lg space-y-4 px-4 py-10">
      <div className="flex items-center gap-3 text-danger-strong">
        <WarningIcon className="size-8" />
        <h1 className="text-2xl font-bold">{t("error.title")}</h1>
      </div>
      <p>{t("error.body")}</p>
      <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
        <RefreshIcon className="size-5" />
        <span>{t("error.reload")}</span>
      </button>
    </main>
  );
}
