"use client";

import * as React from "react";
import { Activity, Ban, Clock, Coins, Database, MessagesSquare, Smile } from "lucide-react";

import { G2Chart } from "@/components/admin/g2-chart";
import { useApp } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

type Analytics = {
  kpis: {
    questions: number;
    users: number;
    conversations: number;
    refusal_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    total_cost_usd: number;
    cost_per_answer_usd: number;
    satisfaction: number | null;
    chunks_indexed: number;
  };
  by_day: { date: string; questions: number; refused: number; cost_usd: number }[];
  top_sources: { source: string; count: number }[];
  recent_questions: { question: string; refused: boolean; score: number; at: string }[];
  unanswered: string[];
};

// Chart palette mirrors the CSS tokens (G2 needs concrete colors).
export const PALETTE = { primary: "#002FA7", ink: "#111111", muted: "#B4B4BA" };

export function AnalyticsTab() {
  const { t } = useApp();
  const [data, setData] = React.useState<Analytics | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    api<Analytics>("/api/analytics?days=30").then(setData).catch((e) => setError(e.message));
  }, []);

  const dayOptions = React.useMemo(() => {
    if (!data) return null;
    const rows = data.by_day.flatMap((d) => [
      { date: d.date, kind: t("answered"), value: d.questions - d.refused },
      { date: d.date, kind: t("refusedSeries"), value: d.refused },
    ]);
    return {
      type: "interval",
      data: rows,
      encode: { x: "date", y: "value", color: "kind" },
      transform: [{ type: "stackY" }],
      scale: { color: { range: [PALETTE.primary, PALETTE.muted] } },
      axis: { x: { title: false }, y: { title: false } },
      style: { maxWidth: 48 },
    };
  }, [data, t]);

  const sourceOptions = React.useMemo(() => {
    if (!data) return null;
    return {
      type: "interval",
      data: data.top_sources,
      encode: { x: "source", y: "count" },
      coordinate: { transform: [{ type: "transpose" }] },
      scale: { color: { range: [PALETTE.primary] } },
      style: { fill: PALETTE.primary, maxWidth: 28 },
      axis: { x: { title: false }, y: { title: false } },
      labels: [{ text: "count", position: "right", dx: 4 }],
    };
  }, [data]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data)
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );

  const k = data.kpis;
  const kpis = [
    { icon: MessagesSquare, label: t("questions"), value: k.questions.toLocaleString() },
    { icon: Ban, label: t("refusalRate"), value: `${(k.refusal_rate * 100).toFixed(1)}%` },
    { icon: Clock, label: t("avgLatency"), value: `${(k.avg_latency_ms / 1000).toFixed(2)}s`, sub: `p95 ${(k.p95_latency_ms / 1000).toFixed(2)}s` },
    { icon: Coins, label: t("costPerAnswer"), value: `$${k.cost_per_answer_usd.toFixed(4)}`, sub: `total $${k.total_cost_usd.toFixed(2)}` },
    { icon: Smile, label: t("satisfaction"), value: k.satisfaction === null ? "—" : `${(k.satisfaction * 100).toFixed(0)}%` },
    { icon: Activity, label: t("usersConversations"), value: `${k.users} / ${k.conversations}` },
    { icon: Database, label: t("chunks"), value: k.chunks_indexed.toLocaleString() },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {kpis.map(({ icon: Icon, label, value, sub }) => (
          <Card key={label} className="gap-2 py-4">
            <CardHeader className="px-4">
              <CardDescription className="flex items-center gap-1.5 text-xs">
                <Icon className="size-3.5" />
                {label}
              </CardDescription>
            </CardHeader>
            <CardContent className="px-4">
              <div className="folio text-4xl">{value}</div>
              {sub ? <div className="mt-2 text-[11px] text-muted-foreground">{sub}</div> : null}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="text-base">{t("perDay")}</CardTitle>
          </CardHeader>
          <CardContent>
            {data.by_day.length && dayOptions ? <G2Chart options={dayOptions} /> : <Empty />}
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">{t("topSources")}</CardTitle>
          </CardHeader>
          <CardContent>
            {data.top_sources.length && sourceOptions ? <G2Chart options={sourceOptions} /> : <Empty />}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("unanswered")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {data.unanswered.length ? (
              data.unanswered.map((q, i) => (
                <div key={i} dir="auto" className="border-b py-2 text-sm">
                  {q}
                </div>
              ))
            ) : (
              <Empty />
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("recent")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col divide-y">
            {data.recent_questions.map((q, i) => (
              <div key={i} className="flex items-center gap-3 py-2 text-sm">
                <span dir="auto" className="min-w-0 flex-1 truncate">
                  {q.question}
                </span>
                {q.refused ? <Badge variant="outline">{t("refusedSeries")}</Badge> : null}
                <span className="text-xs text-muted-foreground">{q.score.toFixed(2)}</span>
              </div>
            ))}
            {!data.recent_questions.length && <Empty />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Empty() {
  const { t } = useApp();
  return <div className="py-10 text-sm text-muted-foreground">{t("noData")}</div>;
}
