"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, FileText } from "lucide-react";

import { useApp } from "@/components/providers";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

type Doc = { source: string; chunks: number; pages: number; category: string };

/**
 * Swiss landing page: start-aligned type on a visible 12-column grid, numerals as composition.
 * Everything here is either authored copy (i18n) or real data from the API / domain.yaml —
 * no invented stats or testimonials.
 */
export function Landing() {
  const { t, config, lang } = useApp();
  const [docs, setDocs] = React.useState<Doc[] | null>(null);
  const [chunks, setChunks] = React.useState(0);
  const Arrow = lang === "ar" ? ArrowLeft : ArrowRight;

  React.useEffect(() => {
    api<{ total_chunks: number; documents: Doc[] }>("/api/documents")
      .then((r) => {
        setDocs(r.documents);
        setChunks(r.total_chunks);
      })
      .catch(() => setDocs([]));
  }, []);

  const steps = [
    [t("step1Title"), t("step1Body")],
    [t("step2Title"), t("step2Body")],
    [t("step3Title"), t("step3Body")],
    [t("step4Title"), t("step4Body")],
  ];
  const principles = [
    [t("p1Title"), t("p1Body")],
    [t("p2Title"), t("p2Body")],
    [t("p3Title"), t("p3Body")],
  ];

  return (
    <div className="min-h-dvh">
      <SiteHeader />

      {/* Hero */}
      <section className="swiss-grid border-b-2 border-rule">
        <div className="mx-auto grid max-w-[1440px] gap-10 px-4 py-16 sm:px-6 lg:grid-cols-12 lg:py-24">
          <div className="lg:col-span-7">
            <h1 className="text-6xl font-bold leading-[0.95] tracking-tight sm:text-8xl">{config?.product_name}</h1>
            {config?.tagline ? <p className="mt-6 max-w-xl text-xl leading-9 sm:text-2xl">{config.tagline}</p> : null}
            {config?.audience ? (
              <p className="mt-6 text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">{t("forWhom")}:</span> {config.audience}
              </p>
            ) : null}
            <div className="mt-10 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/chat">
                  {t("startChat")}
                  <Arrow />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <a href="#how">{t("howItWorks")}</a>
              </Button>
            </div>
          </div>

          {config?.sample_questions?.length ? (
            <div className="bg-background lg:col-span-5">
              <div className="border-b-2 border-rule pb-2 text-xs font-bold">{t("tryAQuestion")}</div>
              <ol>
                {config.sample_questions.map((q, i) => (
                  <li key={q} className="border-b">
                    <Link
                      href={`/chat?q=${encodeURIComponent(q)}`}
                      dir="auto"
                      className="grid grid-cols-[3rem_1fr_auto] items-baseline gap-3 py-4 transition-colors hover:text-primary"
                    >
                      <span className="folio text-3xl">{String(i + 1).padStart(2, "0")}</span>
                      <span>{q}</span>
                      <Arrow className="size-4 text-primary" />
                    </Link>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      </section>

      {/* Problem (from domain.yaml) */}
      {config?.problem_statement ? (
        <section className="border-b">
          <div className="mx-auto grid max-w-[1440px] gap-6 px-4 py-14 sm:px-6 lg:grid-cols-12">
            <h2 className="text-sm font-bold lg:col-span-3">{t("theProblem")}</h2>
            <p className="text-2xl leading-[1.6] lg:col-span-8">{config.problem_statement}</p>
          </div>
        </section>
      ) : null}

      {/* How it works */}
      <section id="how" className="scroll-mt-16 border-b">
        <div className="mx-auto max-w-[1440px] px-4 py-14 sm:px-6">
          <h2 className="mb-8 text-sm font-bold">{t("howItWorks")}</h2>
          <ol className="grid border-t-2 border-rule md:grid-cols-2 lg:grid-cols-4">
            {steps.map(([title, body], i) => (
              <li key={title} className="border-b py-6 md:border-e md:px-6 md:first:ps-0 lg:border-b-0">
                <span className="folio text-6xl">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="mt-6 text-lg font-bold">{title}</h3>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* What it relies on: live from the API */}
      <section className="border-b bg-muted">
        <div className="mx-auto grid max-w-[1440px] gap-10 px-4 py-14 sm:px-6 lg:grid-cols-12">
          <div className="lg:col-span-4">
            <h2 className="text-sm font-bold">{t("whatItKnows")}</h2>
            {docs ? (
              <div className="mt-8 flex gap-10">
                <div>
                  <div className="folio text-7xl">{docs.length}</div>
                  <div className="mt-2 text-sm">{t("documentsLabel")}</div>
                </div>
                <div>
                  <div className="folio text-7xl">{chunks}</div>
                  <div className="mt-2 text-sm">{t("chunksLabel")}</div>
                </div>
              </div>
            ) : null}
          </div>
          <ul className="border-t-2 border-rule lg:col-span-8">
            {(docs ?? []).map((d) => (
              <li key={d.source} className="flex items-center gap-3 border-b py-3 text-sm">
                <FileText className="size-4 shrink-0 text-primary" />
                <span className="min-w-0 flex-1 truncate" dir="auto">
                  {d.source}
                </span>
                {d.category ? <span className="text-xs text-muted-foreground">{d.category}</span> : null}
                <span className="text-xs text-muted-foreground">
                  {d.pages ? `${d.pages} ${t("pages")} · ` : ""}
                  {d.chunks} {t("chunks")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* Principles */}
      <section className="border-b">
        <div className="mx-auto max-w-[1440px] px-4 py-14 sm:px-6">
          <h2 className="mb-8 text-sm font-bold">{t("principles")}</h2>
          <div className="grid border-t-2 border-rule md:grid-cols-3">
            {principles.map(([title, body]) => (
              <div key={title} className="border-b py-6 md:border-b-0 md:border-e md:px-6 md:first:ps-0 md:last:border-e-0">
                <h3 className="text-2xl font-bold">{title}</h3>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing call to action */}
      <section className="bg-primary text-primary-foreground">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-end justify-between gap-6 px-4 py-14 sm:px-6">
          <p className="max-w-2xl text-3xl font-bold leading-snug sm:text-4xl">{config?.tagline || config?.product_name}</p>
          <Button asChild size="lg" variant="outline" className="border-primary-foreground bg-primary text-primary-foreground hover:bg-primary-foreground hover:text-primary">
            <Link href="/chat">
              {t("startChat")}
              <Arrow />
            </Link>
          </Button>
        </div>
      </section>

      <footer className="mx-auto flex max-w-[1440px] flex-wrap justify-between gap-2 px-4 py-6 text-xs text-muted-foreground sm:px-6">
        <span>{t("builtFor")}</span>
        {config?.disclaimer ? <span>{config.disclaimer}</span> : null}
      </footer>
    </div>
  );
}
