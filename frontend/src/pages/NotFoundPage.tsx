import { Link } from "react-router";

import { HomeIcon } from "../components/icons";
import { useI18n } from "../i18n/context";

export function NotFoundPage() {
  const { t } = useI18n();

  return (
    <section aria-labelledby="not-found-title" className="space-y-4">
      <h1 id="not-found-title" className="text-2xl font-bold text-primary">
        {t("notFound.title")}
      </h1>
      <p>{t("notFound.body")}</p>
      <Link to="/" className="btn-primary">
        <HomeIcon className="size-5" />
        <span>{t("notFound.home")}</span>
      </Link>
    </section>
  );
}
