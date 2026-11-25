import { StatusBadge } from "../../components/ui/StatusBadge";
import { useI18n } from "../../i18n/context";

/** Visible label for fixture (simulated) results — never shown as real AI output. */
export function SimulatedBadge({ show }: { show: boolean }) {
  const { t } = useI18n();
  if (!show) return null;
  return <StatusBadge tone="warning">{t("voice.simulated")}</StatusBadge>;
}
