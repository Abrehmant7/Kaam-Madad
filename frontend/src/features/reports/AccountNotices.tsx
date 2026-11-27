import { FileWarning } from "lucide-react";

import { useAuth } from "../../auth/context";
import { Alert } from "../../components/ui/Alert";
import { ButtonLink } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";

/** Dashboard notices (M10): a staff restriction, and the way to "My reports". */
export function AccountNotices() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <>
      {user?.restricted && <Alert tone="warning" title={t("restricted.title")}>{t("restricted.body")}</Alert>}
      <ButtonLink to="/reports" variant="ghost" fullWidth icon={<FileWarning className="size-5" aria-hidden />}>
        {t("report.mine")}
      </ButtonLink>
    </>
  );
}
