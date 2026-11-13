"use client";

import * as React from "react";
import { toast } from "sonner";
import { Check, FlaskConical, Loader2, X } from "lucide-react";

import { G2Chart } from "@/components/admin/g2-chart";
import { PALETTE } from "@/components/admin/analytics-tab";
import { useApp } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

type Row = {
  id: string;
  type: string;
  question: string;
  hit?: number;
  precision?: number;
  mrr?: number;
  faithfulness?: number | null;
  correctness?: number | null;
  refusal_correct: boolean;
  latency_ms: number;
  answer?: string;
};
type Report = { summary: Record<string, unknown> & { config: Record<string, unknown> }; rows: Row[]; created_at: string };

const METRICS: [string, string][] = [
  ["hit_rate@k", "Hit@k"],
  ["precision@k", "Precision@k"],
  ["mrr", "MRR"],
  ["faithfulness", "Faithfulness"],
  ["correctness", "Correctness"],
  ["citation_rate", "Citation rate"],
  ["refusal_accuracy", "Refusal accuracy"],
];

export function EvalTab() {
  const { t } = useApp();
  const [report, setReport] = React.useState<Report | null>(null);
  const [running, setRunning] = React.useState(false);

  React.useEffect(() => {
    api<Report>("/api/eval/latest").then(setReport).catch(() => setReport(null));
  }, []);

  async function run(withGeneration: boolean) {
    setRunning(true);
    try {
      setReport(await api<Report>(`/api/eval/run?with_generation=${withGeneration}`, { method: "POST" }));
      toast.success("Evaluation finished");
    } catch (e) {
      toast.error((e as Error).message);
    }
    setRunning(false);
  }

  const chart = React.useMemo(() => {
    if (!report) return null;
    const data = METRICS.filter(([k]) => typeof report.summary[k] === "number").map(([k, label]) => ({
      metric: label,
      value: report.summary[k] as number,
    }));
    return {
      type: "interval",
      data,
      encode: { x: "metric", y: "value" },
      scale: { y: { domain: [0, 1] } },
      style: { fill: PALETTE.primary, maxWidth: 56 },
      axis: { x: { title: false }, y: { title: false } },
      labels: [{ text: (d: { value: number }) => d.value.toFixed(2), position: "top", dy: -4 }],
    };
  }, [report]);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">{t("evaluation")}</CardTitle>
            <CardDescription>
              data/eval/eval_set.json · {report ? `${report.summary.n_questions} Q · k=${report.summary.k} · ${report.created_at}` : t("noRun")}
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" disabled={running} onClick={() => run(false)}>
              {t("retrievalOnly")}
            </Button>
            <Button disabled={running} onClick={() => run(true)}>
              {running ? <Loader2 className="animate-spin" /> : <FlaskConical />}
              {t("runEval")}
            </Button>
          </div>
        </CardHeader>
        {report ? (
          <CardContent className="grid gap-6 lg:grid-cols-[1fr_320px]">
            {chart ? <G2Chart options={chart} height={280} /> : null}
            <div className="flex flex-col gap-3">
              {METRICS.map(([k, label]) => {
                const v = report.summary[k] as number | null;
                return (
                  <div key={k} className="grid gap-1">
                    <div className="flex justify-between text-sm">
                      <span>{label}</span>
                      <span className="font-semibold">{v === null || v === undefined ? "—" : v.toFixed(3)}</span>
                    </div>
                    <Progress value={(v ?? 0) * 100} />
                  </div>
                );
              })}
              <pre dir="ltr" className="mt-2 overflow-x-auto border bg-muted p-3 text-[11px] leading-5">
                {JSON.stringify(report.summary.config, null, 2)}
              </pre>
            </div>
          </CardContent>
        ) : null}
      </Card>

      {report ? (
        <Card>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>id</TableHead>
                  <TableHead>type</TableHead>
                  <TableHead>question</TableHead>
                  <TableHead className="text-end">hit</TableHead>
                  <TableHead className="text-end">MRR</TableHead>
                  <TableHead className="text-end">faithful</TableHead>
                  <TableHead className="text-end">correct</TableHead>
                  <TableHead className="text-end">refusal ok</TableHead>
                  <TableHead className="text-end">ms</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.rows.map((r) => (
                  <TableRow key={r.id} title={r.answer}>
                    <TableCell className="text-xs">{r.id}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">{r.type}</Badge>
                    </TableCell>
                    <TableCell dir="auto" className="max-w-[360px] truncate">
                      {r.question}
                    </TableCell>
                    <TableCell className="text-end">{fmt(r.hit)}</TableCell>
                    <TableCell className="text-end">{fmt(r.mrr)}</TableCell>
                    <TableCell className="text-end">{fmt(r.faithfulness)}</TableCell>
                    <TableCell className="text-end">{fmt(r.correctness)}</TableCell>
                    <TableCell className="text-end">{r.refusal_correct ? <Check className="ms-auto size-4 text-primary" aria-label="ok" /> : <X className="ms-auto size-4" aria-label="wrong" />}</TableCell>
                    <TableCell className="text-end text-xs">{r.latency_ms}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function fmt(v: number | null | undefined) {
  return v === null || v === undefined ? "—" : v.toFixed(2);
}
