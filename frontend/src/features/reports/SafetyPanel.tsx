import { Ban, Flag, ShieldCheck } from "lucide-react";
import { useState } from "react";

import * as reportsApi from "../../api/reports";
import { Alert } from "../../components/ui/Alert";
import { Button, ButtonLink } from "../../components/ui/Button";
import { useI18n } from "../../i18n/context";
import { describeError } from "../../i18n/errors";

type Target = { invitation_id: string } | { booking_id: string };

/** "Report a concern" and "Block further contact" for an existing interaction (M10, REP-01 / REP-03). */
export function SafetyPanel({ target, block, onChanged }: { target: Target; block: reportsApi.ContactBlockState; onChanged: () => void }) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const query = "invitation_id" in target ? `invitation=${target.invitation_id}` : `booking=${target.booking_id}`;

  async function run(action: () => Promise<unknown>) {
    setFailure(null);
    setBusy(true);
    try {
      await action();
      setConfirming(false);
      onChanged();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="safety-heading" className="space-y-3 card p-4">
      <h2 id="safety-heading" className="flex items-center gap-2 font-bold">
        <ShieldCheck className="size-5" aria-hidden />
        {t("safety.title")}
      </h2>
      <ButtonLink to={`/reports/new?${query}`} variant="secondary" fullWidth icon={<Flag className="size-5" aria-hidden />}>
        {t("safety.report")}
      </ButtonLink>
      {block.blocked ? (
        <div className="space-y-2">
          <Alert tone="info">{block.by_me ? t("safety.blockedByMe") : t("safety.blockedOther")}</Alert>
          {block.by_me && block.block_id && (
            <Button variant="ghost" fullWidth loading={busy} loadingLabel={t("onboarding.saving")}
              onClick={() => void run(() => reportsApi.unblockContact(block.block_id!))}>
              {t("safety.unblock")}
            </Button>
          )}
        </div>
      ) : confirming ? (
        <div className="space-y-2 rounded-xl border border-warning bg-warning-soft p-3">
          <p className="text-sm">{t("safety.blockExplain")}</p>
          <Button variant="danger" fullWidth loading={busy} loadingLabel={t("onboarding.saving")} icon={<Ban className="size-5" aria-hidden />}
            onClick={() => void run(() => reportsApi.blockContact(target))}>
            {t("safety.blockConfirm")}
          </Button>
          <Button variant="ghost" fullWidth onClick={() => setConfirming(false)}>{t("accept.cancel")}</Button>
        </div>
      ) : (
        <Button variant="ghost" fullWidth icon={<Ban className="size-5" aria-hidden />} onClick={() => setConfirming(true)}>
          {t("safety.block")}
        </Button>
      )}
      {failure !== null && <Alert tone="danger">{describeError(failure, t)}</Alert>}
      <p className="text-xs text-muted">{t("safety.note")}</p>
    </section>
  );
}
