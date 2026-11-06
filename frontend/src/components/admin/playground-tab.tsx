"use client";

import * as React from "react";
import { Loader2, Search } from "lucide-react";

import { useApp } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Hit = { id: string; text: string; metadata: Record<string, string | number>; score: number; scores: Record<string, number> };
type Result = { query: string; rewritten: string; keywords: string[]; confident: boolean; timings_ms: Record<string, number>; hits: Hit[] };

/** Retrieval lab: shows exactly what the retriever returns and why (great for judges' questions). */
export function PlaygroundTab() {
  const { t } = useApp();
  const [q, setQ] = React.useState("");
  const [rewrite, setRewrite] = React.useState(true);
  const [res, setRes] = React.useState<Result | null>(null);
  const [loading, setLoading] = React.useState(false);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setLoading(true);
    try {
      setRes(await api<Result>("/api/documents/search", { method: "POST", body: JSON.stringify({ query: q, top_k: 8, rewrite }) }));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("playground")}</CardTitle>
          <CardDescription>dense (Chroma) + BM25 → RRF → cross-encoder rerank</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={run} className="flex flex-wrap items-center gap-3">
            <Input value={q} onChange={(e) => setQ(e.target.value)} dir="auto" className="min-w-64 flex-1" placeholder={t("askPlaceholder")} />
            <Label className="text-sm">
              <input type="checkbox" checked={rewrite} onChange={(e) => setRewrite(e.target.checked)} className="accent-primary" />
              {t("queryRewrite")}
            </Label>
            <Button type="submit" disabled={loading}>
              {loading ? <Loader2 className="animate-spin" /> : <Search />}
              {t("search")}
            </Button>
          </form>
          {res ? (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
              <Badge variant={res.confident ? "default" : "outline"}>{res.confident ? t("confident") : t("lowConfidence")}</Badge>
              <span dir="auto">«{res.rewritten}»</span>
              {res.keywords.map((k) => (
                <Badge key={k} variant="outline">
                  {k}
                </Badge>
              ))}
              <span className="ms-auto text-muted-foreground">
                {Object.entries(res.timings_ms)
                  .map(([k, v]) => `${k} ${v}ms`)
                  .join(" · ")}
              </span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-3">
        {res?.hits.map((h, i) => (
          <Card key={h.id} className="gap-3 py-4">
            <CardContent className="px-4">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className="folio w-8 text-3xl">{i + 1}</span>
                <span className="font-medium" dir="auto">
                  {String(h.metadata.source)}
                </span>
                {Number(h.metadata.page) > 0 ? <span className="text-muted-foreground">p.{h.metadata.page}</span> : null}
                {h.metadata.section ? (
                  <span className="text-muted-foreground" dir="auto">
                    · {String(h.metadata.section)}
                  </span>
                ) : null}
                <span className="ms-auto flex gap-1.5">
                  {Object.entries(h.scores).map(([k, v]) => (
                    <Badge key={k} variant="secondary">
                      {k} {v.toFixed(3)}
                    </Badge>
                  ))}
                </span>
              </div>
              <p dir="auto" className="whitespace-pre-wrap text-sm leading-7 text-muted-foreground">
                {h.text}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
