import type { PhoneConfirmation } from "../../api/auth";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useI18n } from "../../i18n/context";

/** Confirmation status badge. A demo confirmation is never shown as real verification. */
export function PhoneConfirmationBadge({ confirmation }: { confirmation: Pick<PhoneConfirmation, "status" | "method"> }) {
  const { t } = useI18n();
  if (confirmation.status !== "confirmed") return <StatusBadge tone="neutral">{t("phone.status.unconfirmed")}</StatusBadge>;
  if (confirmation.method === "demo") return <StatusBadge tone="warning">{t("phone.status.confirmedDemo")}</StatusBadge>;
  return <StatusBadge tone="success">{t("phone.status.confirmedSms")}</StatusBadge>;
}
