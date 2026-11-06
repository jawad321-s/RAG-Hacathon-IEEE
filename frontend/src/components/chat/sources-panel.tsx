"use client";

import * as React from "react";
import { FileText, Table2 } from "lucide-react";

import { useApp } from "@/components/providers";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Source } from "@/lib/api";
import { cn } from "@/lib/utils";

export function SourcesPanel({
  sources,
  cited,
  active,
  onSelect,
}: {
  sources: Source[];
  cited: number[];
  active: number | null;
  onSelect: (n: number) => void;
}) {
  const { t } = useApp();
  const refs = React.useRef<Record<number, HTMLDivElement | null>>({});

  React.useEffect(() => {
    if (active) refs.current[active]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [active]);

  if (!sources.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center text-sm text-muted-foreground">
        <div className="grid size-12 place-items-center rounded-full border border-dashed">
          <FileText className="size-5" />
        </div>
        {t("noSources")}
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-3 p-4">
        {sources.map((s) => {
          const isCited = cited.includes(s.index);
          const isTable = s.text.includes("[جدول / Table]");
          const rel = s.scores.rerank ?? s.scores.dense ?? s.score;
          return (
            <div
              key={s.id}
              ref={(el) => {
                refs.current[s.index] = el;
              }}
              onClick={() => onSelect(s.index)}
              className={cn(
                "group cursor-pointer rounded-lg border bg-card p-3 text-sm transition-all",
                active === s.index ? "border-evidence ring-2 ring-evidence/40" : "hover:border-foreground/20",
                !isCited && cited.length > 0 && "opacity-60 hover:opacity-100"
              )}
            >
              <div className="mb-2 flex items-start gap-2">
                <span
                  className={cn(
                    "grid size-6 shrink-0 place-items-center rounded-full font-mono text-[11px] font-semibold",
                    isCited ? "bg-evidence text-evidence-foreground" : "bg-muted text-muted-foreground"
                  )}
                >
                  {s.index}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 font-medium">
                    {isTable ? <Table2 className="size-3.5 shrink-0" /> : <FileText className="size-3.5 shrink-0" />}
                    <span className="truncate" dir="auto">
                      {s.source}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground" dir="auto">
                    {s.page ? `${t("page")} ${s.page}` : null}
                    {s.page && s.section ? " · " : null}
                    {s.section}
                  </div>
                </div>
                <span className="font-mono text-[10px] text-muted-foreground" title={t("relevance")}>
                  {(rel * 100).toFixed(0)}%
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-primary/60" style={{ width: `${Math.min(100, rel * 100)}%` }} />
              </div>
              <p
                dir="auto"
                className={cn(
                  "mt-2 whitespace-pre-wrap text-[13px] leading-6 text-muted-foreground",
                  active === s.index ? "" : "line-clamp-4"
                )}
              >
                {s.text}
              </p>
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
}
