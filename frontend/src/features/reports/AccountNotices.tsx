import { FileWarning } from "lucide-react";

import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { ButtonLink } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";

/** Dashboard notice (M10): a staff restriction, with the way to "My reports" (which a restricted account can still use).
 * "My reports" is otherwise always reachable from the navigation. */
export function AccountNotices() {
  const { t } = useI18n();
  const { user } = useAuth();
  if (!user?.restricted) return null;
  return (
    <Alert tone="warning" title={t("restricted.title")}>
      <p>{t("restricted.body")}</p>
      <ButtonLink to="/reports" variant="ghost" className="min-h-11 px-0" icon={<FileWarning className="size-5" aria-hidden />}>
        {t("report.mine")}
      </ButtonLink>
    </Alert>
  );
}
