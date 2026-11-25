import { LoaderCircle } from "lucide-react";

import { useI18n } from "../../i18n/context";

/** Loading state with text. Requests time out (10 s), so this never spins forever. */
export function PageLoader() {
  const { t } = useI18n();
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-3 py-16 text-muted">
      <LoaderCircle className="size-7 motion-safe:animate-spin" aria-hidden />
      <span>{t("common.loading")}</span>
    </div>
  );
}
