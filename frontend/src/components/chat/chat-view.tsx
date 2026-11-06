"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  ArrowUp,
  BookOpenText,
  Check,
  Copy,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  ShieldAlert,
  ShieldCheck,
  Square,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";

import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { useApp } from "@/components/providers";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { api, streamChat, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

type Msg = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  cited?: number[];
  refused?: boolean;
  rewritten?: string;
  streaming?: boolean;
  latency?: number;
};

type ConvSummary = { id: number; title: string; updated_at: string };
type Doc = { source: string; chunks: number; pages: number };

/**
 * Chat layout (Swiss anchor): one centered conversation column, history rail on the start side,
 * and a sources rail that opens only when a folio citation is clicked.
 */
export function ChatView() {
  const { t, user, config, lang } = useApp();
  const [messages, setMessages] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [conversationId, setConversationId] = React.useState<number | null>(null);
  const [selected, setSelected] = React.useState<number | null>(null);
  const [activeCite, setActiveCite] = React.useState<number | null>(null);
  const [sourcesOpen, setSourcesOpen] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(true);
  const [history, setHistory] = React.useState<ConvSummary[]>([]);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [library, setLibrary] = React.useState<Doc[]>([]);
  const [facets, setFacets] = React.useState<string[]>([]);
  const [category, setCategory] = React.useState("");
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const askedFromUrl = React.useRef(false);

  const loadHistory = React.useCallback(() => {
    if (!user) return setHistory([]);
    api<ConvSummary[]>("/api/conversations").then(setHistory).catch(() => {});
  }, [user]);

  React.useEffect(loadHistory, [loadHistory]);

  React.useEffect(() => {
    api<Record<string, string[]>>("/api/documents/facets")
      .then((f) => setFacets(f.category ?? []))
      .catch(() => {});
    api<{ documents: Doc[] }>("/api/documents")
      .then((r) => setLibrary(r.documents))
      .catch(() => {});
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => setIsDesktop(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const shown = selected !== null ? messages[selected] : [...messages].reverse().find((m) => m.role === "assistant");

  function newChat() {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(null);
    setSelected(null);
    setActiveCite(null);
    setSourcesOpen(false);
    setHistoryOpen(false);
  }

  async function openConversation(id: number) {
    const c = await api<{ id: number; messages: (Msg & { sources: Source[] })[] }>(`/api/conversations/${id}`);
    setMessages(c.messages.map((m) => ({ ...m, cited: [] })));
    setConversationId(c.id);
    setSelected(null);
    setHistoryOpen(false);
  }

  const ask = React.useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      setInput("");
      setBusy(true);
      setActiveCite(null);
      setSelected(null);
      setMessages((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", streaming: true }]);
      const controller = new AbortController();
      abortRef.current = controller;

      const patchLast = (fn: (m: Msg) => Msg) =>
        setMessages((all) => {
          const copy = [...all];
          copy[copy.length - 1] = fn(copy[copy.length - 1]);
          return copy;
        });

      try {
        await streamChat(
          { question: q, conversation_id: conversationId, filters: category ? { category } : null },
          (ev) => {
            if (ev.type === "sources") {
              setConversationId(ev.conversation_id);
              patchLast((m) => ({ ...m, sources: ev.sources, rewritten: ev.rewritten_query }));
            } else if (ev.type === "token") {
              patchLast((m) => ({ ...m, content: m.content + ev.text }));
            } else if (ev.type === "done") {
              patchLast((m) => ({
                ...m,
                id: ev.message_id,
                cited: ev.cited,
                refused: ev.refused,
                streaming: false,
                latency: ev.timings_ms?.total,
              }));
            } else if (ev.type === "error") {
              throw new Error(ev.message);
            }
          },
          controller.signal
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          toast.error(t("error"), { description: (err as Error).message });
          patchLast((m) => ({ ...m, content: m.content || (err as Error).message, refused: true }));
        }
      } finally {
        patchLast((m) => ({ ...m, streaming: false }));
        setBusy(false);
        loadHistory();
      }
    },
    [busy, category, conversationId, loadHistory, t]
  );

  // Landing page links to /chat?q=... — ask that question once on arrival.
  React.useEffect(() => {
    if (askedFromUrl.current) return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      askedFromUrl.current = true;
      window.history.replaceState(null, "", window.location.pathname);
      ask(q);
    }
  }, [ask]);

  async function sendFeedback(m: Msg, rating: 1 | -1) {
    if (!m.id) return;
    await api("/api/feedback", { method: "POST", body: JSON.stringify({ message_id: m.id, rating }) }).catch(() => {});
    toast.success(t("thanks"));
  }

  function openSources(msgIndex: number, n: number) {
    setSelected(msgIndex);
    setActiveCite(n);
    setSourcesOpen(true);
  }

  const sourcesPanel = (
    <SourcesPanel sources={shown?.sources ?? []} cited={shown?.cited ?? []} active={activeCite} onSelect={setActiveCite} />
  );

  const rail = (
    <div className="flex flex-col">
      <button
        onClick={newChat}
        className="flex items-center gap-2 border-b px-4 py-3 text-start text-sm font-semibold text-primary hover:bg-background"
      >
        <MessageSquarePlus className="size-4" />
        {t("newChat")}
      </button>
      {user ? (
        history.map((c) => (
          <button
            key={c.id}
            onClick={() => openConversation(c.id)}
            className={cn(
              "truncate border-b px-4 py-3 text-start text-sm hover:bg-background",
              c.id === conversationId && "border-s-2 border-s-primary bg-background font-semibold"
            )}
            dir="auto"
          >
            {c.title}
          </button>
        ))
      ) : (
        <>
          <div className="border-b px-4 py-3 text-xs font-semibold">{t("library")}</div>
          {library.map((d) => (
            <div key={d.source} className="border-b px-4 py-3">
              <div className="truncate text-sm" dir="auto">
                {d.source}
              </div>
              <div className="text-xs text-muted-foreground">
                {d.pages ? `${d.pages} ${t("pages")} · ` : ""}
                {d.chunks} {t("chunks")}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );

  const composer = (
    <Composer
      value={input}
      onChange={setInput}
      onSubmit={() => ask(input)}
      busy={busy}
      onStop={() => abortRef.current?.abort()}
      facets={facets}
      category={category}
      onCategory={setCategory}
      large={messages.length === 0}
    />
  );

  return (
    <div className="flex h-dvh flex-col">
      <SiteHeader>
        <Button variant="ghost" size="icon-sm" className="xl:hidden" onClick={() => setHistoryOpen(true)} aria-label={t("history")}>
          <PanelLeft />
        </Button>
      </SiteHeader>

      <div
        className={cn(
          "grid min-h-0 w-full flex-1 grid-cols-1",
          sourcesOpen && isDesktop ? "lg:grid-cols-[minmax(0,1fr)_420px] xl:grid-cols-[260px_minmax(0,1fr)_420px]" : "xl:grid-cols-[260px_minmax(0,1fr)]"
        )}
      >
        <aside className="hidden min-h-0 border-e bg-muted xl:block">
          <ScrollArea className="h-full">{rail}</ScrollArea>
        </aside>

        <section className="flex min-h-0 flex-col">
          {messages.length === 0 ? (
            <ScrollArea className="swiss-grid min-h-0 flex-1">
              <div className="mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-3xl flex-col justify-center px-5 py-10 sm:px-8">
                <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">{config?.product_name}</h1>
                {config?.tagline ? <p className="mt-3 text-lg text-muted-foreground">{config.tagline}</p> : null}
                <div className="mt-8">{composer}</div>
                {config?.sample_questions?.length ? (
                  <ol className="mt-8 grid border-t sm:grid-cols-2">
                    {config.sample_questions.map((q, i) => (
                      <li key={q} className="border-b sm:odd:border-e">
                        <button
                          onClick={() => ask(q)}
                          dir="auto"
                          className="grid w-full grid-cols-[2.5rem_1fr] items-baseline gap-2 bg-background px-3 py-4 text-start text-sm transition-colors hover:text-primary"
                        >
                          <span className="folio text-2xl">{String(i + 1).padStart(2, "0")}</span>
                          <span>{q}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                ) : null}
              </div>
            </ScrollArea>
          ) : (
            <>
              <ScrollArea className="min-h-0 flex-1">
                <div className="mx-auto flex max-w-3xl flex-col gap-8 px-5 py-8 sm:px-8">
                  {messages.map((m, i) =>
                    m.role === "user" ? (
                      <div key={i} className="flex justify-end">
                        <div dir="auto" className="max-w-[85%] bg-primary px-4 py-3 leading-7 text-primary-foreground">
                          {m.content}
                        </div>
                      </div>
                    ) : (
                      <AssistantMessage
                        key={i}
                        m={m}
                        question={messages[i - 1]?.content}
                        activeCite={selected === i ? activeCite : null}
                        onCite={(n) => openSources(i, n)}
                        onFeedback={(r) => sendFeedback(m, r)}
                      />
                    )
                  )}
                  <div ref={bottomRef} />
                </div>
              </ScrollArea>
              <div className="border-t-2 border-rule px-4 py-3 sm:px-8">
                <div className="mx-auto max-w-3xl">{composer}</div>
                {config?.disclaimer ? (
                  <p className="mx-auto mt-2 max-w-3xl text-[11px] text-muted-foreground">{config.disclaimer}</p>
                ) : null}
              </div>
            </>
          )}
        </section>

        {sourcesOpen && isDesktop ? (
          <aside className="hidden min-h-0 flex-col border-s bg-muted lg:flex">
            <div className="flex h-12 items-center border-b px-5 text-sm font-bold">
              {t("sources")}
              <Button variant="ghost" size="icon-sm" className="ms-auto" onClick={() => setSourcesOpen(false)} aria-label={t("close")}>
                <X />
              </Button>
            </div>
            <div className="min-h-0 flex-1">{sourcesPanel}</div>
          </aside>
        ) : null}
      </div>

      <Sheet open={sourcesOpen && !isDesktop} onOpenChange={setSourcesOpen}>
        <SheetContent side={lang === "ar" ? "left" : "right"} className="w-[92vw] bg-muted p-0 sm:max-w-md">
          <SheetHeader className="border-b">
            <SheetTitle>{t("sources")}</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1">{sourcesPanel}</div>
        </SheetContent>
      </Sheet>

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side={lang === "ar" ? "right" : "left"} className="w-72 bg-muted p-0">
          <SheetHeader className="border-b">
            <SheetTitle>{user ? t("history") : t("library")}</SheetTitle>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">{rail}</ScrollArea>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function AssistantMessage({
  m,
  question,
  activeCite,
  onCite,
  onFeedback,
}: {
  m: Msg;
  question?: string;
  activeCite: number | null;
  onCite: (n: number) => void;
  onFeedback: (rating: 1 | -1) => void;
}) {
  const { t } = useApp();
  const sources = m.sources ?? [];
  const cited = m.cited ?? [];
  return (
    <article className="flex gap-3">
      <span className="grid size-8 shrink-0 place-items-center bg-foreground text-background" aria-hidden>
        <BookOpenText className="size-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {m.streaming ? (
            <span className="flex items-center gap-1.5 text-primary">
              <Loader2 className="size-3.5 animate-spin" />
              {sources.length ? `${sources.length} ${t("sources")}` : t("searching")}
            </span>
          ) : m.refused ? (
            <span className="flex items-center gap-1.5 font-semibold text-foreground">
              <ShieldAlert className="size-3.5" />
              {t("refused")}
            </span>
          ) : (
            <span className="flex items-center gap-1.5 font-semibold text-primary">
              <ShieldCheck className="size-3.5" />
              {t("grounded")}
            </span>
          )}
          {m.rewritten && m.rewritten !== question ? (
            <span className="truncate" dir="auto" title={m.rewritten}>
              {t("searchedAs")}: «{m.rewritten}»
            </span>
          ) : null}
          {m.latency ? (
            <span className="ms-auto">
              <bdi>{(m.latency / 1000).toFixed(1)}</bdi> s
            </span>
          ) : null}
        </div>

        <div dir="auto">
          <AnswerMarkdown text={m.content} streaming={m.streaming} activeCite={activeCite} onCite={onCite} />
        </div>

        {/* Folio strip: the sources behind this answer, cited ones in blue. */}
        {!m.streaming && sources.length && !m.refused ? (
          <div className="mt-4 border-t">
            <div className="flex flex-wrap">
              {sources.map((s) => {
                const isCited = cited.includes(s.index);
                return (
                  <button
                    key={s.id}
                    onClick={() => onCite(s.index)}
                    title={s.source}
                    className={cn(
                      "flex max-w-[15rem] items-baseline gap-2 border-b border-e px-3 py-2 text-start text-xs transition-colors hover:bg-muted",
                      activeCite === s.index && "bg-muted"
                    )}
                  >
                    <span className={cn("folio text-xl", !isCited && "text-muted-foreground/60")}>{s.index}</span>
                    <span className="min-w-0 truncate" dir="auto">
                      {s.source}
                      {s.page ? ` · ${t("page")} ${s.page}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {!m.streaming && m.content ? (
          <div className="mt-2 flex items-center gap-1 text-muted-foreground">
            <CopyButton text={m.content} />
            <Button variant="ghost" size="icon-sm" aria-label={t("helpful")} onClick={() => onFeedback(1)}>
              <ThumbsUp />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={t("notHelpful")} onClick={() => onFeedback(-1)}>
              <ThumbsDown />
            </Button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  onStop,
  facets,
  category,
  onCategory,
  large,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
  onStop: () => void;
  facets: string[];
  category: string;
  onCategory: (v: string) => void;
  large?: boolean;
}) {
  const { t } = useApp();
  return (
    <form
      className={cn("flex items-end gap-2 border bg-background p-2 focus-within:border-primary", large ? "border-2 border-rule" : "border-input")}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <Textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder={t("askPlaceholder")}
        dir="auto"
        rows={large ? 2 : 1}
        autoFocus
        className={cn("max-h-48 resize-none border-0 bg-transparent focus-visible:ring-0", large ? "min-h-16 text-base" : "min-h-10")}
      />
      {facets.length > 1 ? (
        <select
          value={category}
          onChange={(e) => onCategory(e.target.value)}
          aria-label={t("category")}
          className="h-9 max-w-36 shrink-0 border bg-background px-2 text-xs"
        >
          <option value="">{t("allCategories")}</option>
          {facets.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      ) : null}
      {busy ? (
        <Button type="button" size="icon" variant="outline" onClick={onStop} aria-label={t("stop")}>
          <Square className="size-3.5 fill-current" />
        </Button>
      ) : (
        <Button type="submit" size="icon" disabled={!value.trim()} aria-label={t("send")}>
          <ArrowUp />
        </Button>
      )}
    </form>
  );
}

function CopyButton({ text }: { text: string }) {
  const { t } = useApp();
  const [done, setDone] = React.useState(false);
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={t("copy")}
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check /> : <Copy />}
    </Button>
  );
}
