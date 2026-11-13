"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/** Renders the answer; [1], [2] become folio citations that open the matching source. */
export function AnswerMarkdown({
  text,
  onCite,
  activeCite,
  streaming,
}: {
  text: string;
  onCite?: (n: number) => void;
  activeCite?: number | null;
  streaming?: boolean;
}) {
  const withLinks = text.replace(/\[(\d{1,2})\](?!\()/g, "[$1](#cite-$1)");
  return (
    <div className={cn("prose-answer", streaming && "caret")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              return (
                <button
                  type="button"
                  onClick={() => onCite?.(n)}
                  className={cn(
                    "mx-0.5 inline-grid h-[1.15em] min-w-[1.15em] -translate-y-[0.35em] place-items-center px-0.5 align-baseline text-[11px] font-bold leading-none transition-colors",
                    activeCite === n
                      ? "bg-primary text-primary-foreground"
                      : "text-primary underline decoration-1 underline-offset-2 hover:bg-primary hover:text-primary-foreground"
                  )}
                  aria-label={`source ${n}`}
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-4">
                {children}
              </a>
            );
          },
        }}
      >
        {withLinks}
      </ReactMarkdown>
    </div>
  );
}
