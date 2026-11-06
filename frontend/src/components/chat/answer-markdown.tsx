"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/** Renders the answer and turns [1], [2] citations into clickable evidence chips. */
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
                    "mx-0.5 inline-flex h-5 min-w-5 -translate-y-0.5 items-center justify-center rounded-full px-1.5 align-middle font-mono text-[11px] font-semibold transition-colors",
                    activeCite === n
                      ? "bg-evidence text-evidence-foreground"
                      : "bg-evidence-soft text-evidence-foreground hover:bg-evidence"
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
