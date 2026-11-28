import { MapPin, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import * as catalogApi from "../api/catalog";
import { CatalogIcon } from "../components/catalogIcons";
import { Alert } from "../components/ui/Alert";
import { Button } from "../components/ui/Button";
import { IconTileGroup } from "../components/ui/IconTile";
import { PageLoader } from "../components/ui/PageLoader";
import { useI18n } from "../i18n/context";
import { describeError } from "../i18n/errors";

type Load<T> = { status: "loading" } | { status: "error"; error: unknown } | { status: "ready"; data: T };

/**
 * Small read-only view of the database catalog to verify the API integration.
 * Not worker onboarding: nothing is selected or saved here.
 */
export function CatalogPreviewPage() {
  const { t, language } = useI18n();
  const [attempt, setAttempt] = useState(0);
  const [base, setBase] = useState<Load<{ trades: catalogApi.Trade[]; areas: catalogApi.Area[] }>>({ status: "loading" });
  const [trade, setTrade] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Load<catalogApi.SpecialityQuestionSet> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setBase({ status: "loading" });
    Promise.all([catalogApi.fetchTrades(controller.signal), catalogApi.fetchAreas(controller.signal)])
      .then(([trades, areas]) => {
        if (controller.signal.aborted) return;
        setBase({ status: "ready", data: { trades: trades.results, areas: areas.results } });
        const first = trades.results[0];
        setTrade((current) => (current.length === 0 && first ? [first.code] : current));
      })
      .catch((error: unknown) => !controller.signal.aborted && setBase({ status: "error", error }));
    return () => controller.abort();
  }, [attempt]);

  const selectedTrade = trade[0];
  useEffect(() => {
    if (!selectedTrade) return;
    const controller = new AbortController();
    setQuestions({ status: "loading" });
    catalogApi
      .fetchSpecialityQuestions(selectedTrade, controller.signal)
      .then((data) => !controller.signal.aborted && setQuestions({ status: "ready", data }))
      .catch((error: unknown) => !controller.signal.aborted && setQuestions({ status: "error", error }));
    return () => controller.abort();
  }, [selectedTrade]);

  if (base.status === "loading") return <PageLoader />;
  if (base.status === "error") {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("catalog.title")}</h1>
        <Alert tone="danger">{describeError(base.error, t)}</Alert>
        <Button icon={<RefreshCw className="size-5" aria-hidden />} onClick={() => setAttempt((n) => n + 1)}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  const { trades, areas } = base.data;
  const set = questions?.status === "ready" ? questions.data : null;
  const cities = Array.from(new Map(areas.map((area) => [area.city.code, area.city])).values());

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-ink sm:text-3xl">{t("catalog.title")}</h1>
        <p className="text-sm text-muted">{t("catalog.intro")}</p>
      </div>

      {trades.length === 0 ? (
        <Alert tone="info">{t("catalog.empty")}</Alert>
      ) : (
        <IconTileGroup
          label={t("catalog.tradesHeading")}
          mode="single"
          options={trades.map((item) => ({
            value: item.code,
            label: item.labels[language],
            icon: <CatalogIcon id={item.icon} />,
          }))}
          value={trade}
          onChange={setTrade}
        />
      )}

      {questions?.status === "loading" && <PageLoader />}
      {questions?.status === "error" && <Alert tone="danger">{describeError(questions.error, t)}</Alert>}
      {set && (
        <>
          <section className="space-y-2">
            <h2 className="text-lg font-bold">{t("catalog.servicesHeading", { trade: set.trade.labels[language] })}</h2>
            <ul className="grid grid-cols-2 gap-2">
              {set.choices.map((service) => (
                <li key={service.code} className="flex min-h-14 items-center gap-2 rounded-xl border border-line bg-white p-2 text-sm">
                  <CatalogIcon id={service.icon} className="size-6 shrink-0 text-primary" />
                  <span>{service.labels[language]}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="space-y-2">
            <h2 className="text-lg font-bold">{t("catalog.questionsHeading")}</h2>
            <ol className="list-decimal space-y-2 ps-6">
              {set.questions.map((question) => (
                <li key={question.code}>
                  <p className="font-bold">{question.prompt[language]}</p>
                  {question.help[language] && <p className="text-sm text-muted">{question.help[language]}</p>}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-bold">{t("catalog.areasHeading")}</h2>
        {cities.map((city) => (
          <div key={city.code}>
            <h3 className="mb-1 font-bold">{city.labels[language]}</h3>
            <ul className="flex flex-wrap gap-2">
              {areas
                .filter((area) => area.city.code === city.code)
                .map((area) => (
                  <li key={area.code} className="inline-flex items-center gap-1 rounded-full border border-line bg-white px-3 py-1 text-sm">
                    <MapPin className="size-4 text-muted" aria-hidden />
                    {area.labels[language]}
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </section>
    </div>
  );
}
