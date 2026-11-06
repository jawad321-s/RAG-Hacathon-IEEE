"use client";

import * as React from "react";

import { useApp } from "@/components/providers";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Source } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * The differentiator: sources set like a book margin. Each passage gets an oversized
 * blue folio numeral (the same number used in the answer) and its page as a folio marker.
 */
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
    return <p className="p-6 text-sm text-muted-foreground">{t("noSources")}</p>;
  }

  return (
    <ScrollArea className="h-full">
      <ol className="divide-y">
        {sources.map((s) => {
          const isCited = cited.includes(s.index);
          const rel = s.scores.rerank ?? s.scores.dense ?? s.score;
          const isActive = active === s.index;
          return (
            <li key={s.id}>
              <div
                ref={(el) => {
                  refs.current[s.index] = el;
                }}
                onClick={() => onSelect(s.index)}
                className={cn(
                  "grid cursor-pointer grid-cols-[3.25rem_1fr] gap-x-3 px-5 py-5 transition-colors",
                  isActive ? "bg-background" : "hover:bg-background/60",
                  cited.length > 0 && !isCited && "text-muted-foreground"
                )}
              >
                <span className={cn("folio text-5xl", cited.length > 0 && !isCited && "text-muted-foreground/50")}>
                  {s.index}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold" dir="auto">
                    {s.source}
                  </div>
                  <div className="mt-0.5 flex gap-3 text-xs text-muted-foreground">
                    {s.page ? (
                      <span>
                        {t("page")} <bdi>{s.page}</bdi>
                      </span>
                    ) : null}
                    <span>
                      {t("relevance")} <bdi dir="ltr">{(rel * 100).toFixed(0)}%</bdi>
                    </span>
                  </div>
                  {s.section ? (
                    <div className="mt-1 truncate text-xs" dir="auto">
                      {s.section}
                    </div>
                  ) : null}
                </div>
                <p
                  dir="auto"
                  className={cn(
                    "col-span-2 mt-3 whitespace-pre-wrap border-s-2 ps-3 text-[13px] leading-6",
                    isActive ? "border-primary text-foreground" : "border-border line-clamp-4"
                  )}
                >
                  {s.text}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </ScrollArea>
  );
}
