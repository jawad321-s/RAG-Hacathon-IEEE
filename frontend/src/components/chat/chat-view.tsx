"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  ArrowUp,
  BookMarked,
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

export function ChatView() {
  const { t, user, config, lang } = useApp();
  const [messages, setMessages] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [conversationId, setConversationId] = React.useState<number | null>(null);
  const [selected, setSelected] = React.useState<number | null>(null); // message index whose sources are shown
  const [activeCite, setActiveCite] = React.useState<number | null>(null);
  const [mobileSources, setMobileSources] = React.useState(false);
  const [history, setHistory] = React.useState<ConvSummary[]>([]);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const [library, setLibrary] = React.useState<{ source: string; chunks: number; pages: number }[]>([]);
  const [facets, setFacets] = React.useState<string[]>([]);
  const [category, setCategory] = React.useState("");
  const abortRef = React.useRef<AbortController | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const loadHistory = React.useCallback(() => {
    if (!user) return setHistory([]);
    api<ConvSummary[]>("/api/conversations").then(setHistory).catch(() => {});
  }, [user]);

  React.useEffect(loadHistory, [loadHistory]);

  React.useEffect(() => {
    api<Record<string, string[]>>("/api/documents/facets")
      .then((f) => setFacets(f.category ?? []))
      .catch(() => {});
    api<{ documents: { source: string; chunks: number; pages: number }[] }>("/api/documents")
      .then((r) => setLibrary(r.documents))
      .catch(() => {});
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
  }

  async function openConversation(id: number) {
    const c = await api<{ id: number; messages: (Msg & { sources: Source[] })[] }>(`/api/conversations/${id}`);
    setMessages(c.messages.map((m) => ({ ...m, cited: [] })));
    setConversationId(c.id);
    setSelected(null);
    setHistoryOpen(false);
  }

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setActiveCite(null);
    setSelected(null);
    const userMsg: Msg = { role: "user", content: q };
    const placeholder: Msg = { role: "assistant", content: "", streaming: true };
    setMessages((m) => [...m, userMsg, placeholder]);
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
        patchLast((m) => ({ ...m, content: m.content || `⚠️ ${(err as Error).message}`, refused: true }));
      }
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
      loadHistory();
    }
  }

  async function sendFeedback(m: Msg, rating: 1 | -1) {
    if (!m.id) return;
    await api("/api/feedback", { method: "POST", body: JSON.stringify({ message_id: m.id, rating }) }).catch(() => {});
    toast.success(t("thanks"));
  }

  function cite(msgIndex: number, n: number) {
    setSelected(msgIndex);
    setActiveCite(n);
    if (window.matchMedia("(max-width: 1023px)").matches) setMobileSources(true);
  }

  const sourcesPanel = (
    <SourcesPanel
      sources={shown?.sources ?? []}
      cited={shown?.cited ?? []}
      active={activeCite}
      onSelect={setActiveCite}
    />
  );

  const historyList = (
    <div className="flex flex-col">
      <button
        onClick={newChat}
        className="flex items-center gap-2 border-b px-4 py-3 text-start text-sm font-semibold text-primary hover:bg-background"
      >
        <MessageSquarePlus className="size-4" />
        {t("newChat")}
      </button>
      {history.map((c) => (
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
      ))}
    </div>
  );

  // For visitors without an account the left rail lists what the assistant actually knows.
  const libraryList = (
    <div className="flex flex-col">
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
    </div>
  );

  return (
    <div className="flex h-dvh flex-col">
      <SiteHeader>
        {user ? (
          <Button variant="ghost" size="icon-sm" className="xl:hidden" onClick={() => setHistoryOpen(true)} aria-label={t("history")}>
            <PanelLeft />
          </Button>
        ) : null}
      </SiteHeader>

      <div className="mx-auto grid min-h-0 w-full max-w-[1440px] flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_400px] xl:grid-cols-[260px_minmax(0,1fr)_420px]">
        <aside className="hidden min-h-0 border-e bg-muted xl:block">
          <ScrollArea className="h-full">{user ? historyList : libraryList}</ScrollArea>
        </aside>

        <section className="flex min-h-0 flex-col">
          <ScrollArea className={cn("min-h-0 flex-1", messages.length === 0 && "swiss-grid")}>
            {messages.length === 0 ? (
              <EmptyState onPick={ask} />
            ) : (
              <div className="mx-auto flex max-w-3xl flex-col px-5 py-6 sm:px-8">
                {messages.map((m, i) =>
                  m.role === "user" ? (
                    <h2 key={i} dir="auto" className="mt-8 border-t-2 border-rule pt-4 text-xl font-bold leading-snug first:mt-0">
                      {m.content}
                    </h2>
                  ) : (
                    <article key={i} className="group mt-3 pb-2" onClick={() => setSelected(i)}>
                      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        {m.streaming ? (
                          <span className="flex items-center gap-1.5 text-primary">
                            <Loader2 className="size-3.5 animate-spin" />
                            {m.sources ? `${m.sources.length} ${t("sources")}` : t("searching")}
                          </span>
                        ) : m.refused ? (
                          <span className="flex items-center gap-1.5 font-semibold text-foreground">
                            <ShieldAlert className="size-3.5" />
                            {t("refused")}
                          </span>
                        ) : (
                          <span className="flex items-center gap-1.5 font-semibold text-primary">
                            <ShieldCheck className="size-3.5" />
                            {t("grounded")} · {m.cited?.length ?? 0} / {m.sources?.length ?? 0}
                          </span>
                        )}
                        {m.rewritten && m.rewritten !== messages[i - 1]?.content ? (
                          <span className="truncate" dir="auto" title={m.rewritten}>
                            {t("searchedAs")}: «{m.rewritten}»
                          </span>
                        ) : null}
                        {m.latency ? <span className="ms-auto">{(m.latency / 1000).toFixed(1)} s</span> : null}
                      </div>
                      <div dir="auto">
                        <AnswerMarkdown
                          text={m.content}
                          streaming={m.streaming}
                          activeCite={selected === i || (selected === null && m === shown) ? activeCite : null}
                          onCite={(n) => cite(i, n)}
                        />
                      </div>
                      {!m.streaming && m.content ? (
                        <div className="mt-3 flex items-center gap-1 text-muted-foreground">
                          <CopyButton text={m.content} />
                          <Button variant="ghost" size="icon-sm" aria-label={t("helpful")} onClick={() => sendFeedback(m, 1)}>
                            <ThumbsUp />
                          </Button>
                          <Button variant="ghost" size="icon-sm" aria-label={t("notHelpful")} onClick={() => sendFeedback(m, -1)}>
                            <ThumbsDown />
                          </Button>
                          {m.sources?.length ? (
                            <Button variant="ghost" size="sm" className="ms-auto lg:hidden" onClick={() => cite(i, m.cited?.[0] ?? 1)}>
                              <BookMarked />
                              {t("sources")}
                            </Button>
                          ) : null}
                        </div>
                      ) : null}
                    </article>
                  )
                )}
                <div ref={bottomRef} />
              </div>
            )}
          </ScrollArea>

          <div className="border-t-2 border-rule px-4 py-3 sm:px-8">
            <form
              className="mx-auto flex max-w-3xl items-end gap-2 border border-input bg-background p-1.5 focus-within:border-primary"
              onSubmit={(e) => {
                e.preventDefault();
                ask(input);
              }}
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    ask(input);
                  }
                }}
                placeholder={t("askPlaceholder")}
                dir="auto"
                rows={1}
                className="max-h-40 min-h-10 resize-none border-0 bg-transparent focus-visible:ring-0"
              />
              {facets.length > 1 ? (
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
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
                <Button type="button" size="icon" variant="outline" onClick={() => abortRef.current?.abort()} aria-label={t("stop")}>
                  <Square className="size-3.5 fill-current" />
                </Button>
              ) : (
                <Button type="submit" size="icon" disabled={!input.trim()} aria-label={t("send")}>
                  <ArrowUp />
                </Button>
              )}
            </form>
            {config?.disclaimer ? (
              <p className="mx-auto mt-2 max-w-3xl text-[11px] text-muted-foreground">{config.disclaimer}</p>
            ) : null}
          </div>
        </section>

        <aside className="hidden min-h-0 flex-col border-s bg-muted lg:flex">
          <div className="flex h-12 items-center border-b px-5 text-sm font-bold">
            {t("sources")}
            {shown?.sources?.length ? <span className="ms-auto text-xs font-normal text-muted-foreground">{shown.sources.length}</span> : null}
          </div>
          <div className="min-h-0 flex-1">{sourcesPanel}</div>
        </aside>
      </div>

      <Sheet open={mobileSources} onOpenChange={setMobileSources}>
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
            <SheetTitle>{t("history")}</SheetTitle>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">{historyList}</ScrollArea>
        </SheetContent>
      </Sheet>
    </div>
  );
}

/** Start-aligned masthead on a visible 12-column grid; sample questions set as numbered folios. */
function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const { t, config } = useApp();
  return (
    <div>
      <div className="mx-auto max-w-3xl px-5 pb-16 pt-[10vh] sm:px-8">
        <h1 className="text-5xl font-bold leading-none tracking-tight sm:text-7xl">{config?.product_name}</h1>
        {config?.tagline ? <p className="mt-5 max-w-lg text-lg text-muted-foreground">{config.tagline}</p> : null}
        {config?.sample_questions?.length ? (
          <div className="mt-14">
            <div className="border-b-2 border-rule pb-2 text-xs font-bold">{t("tryAsking")}</div>
            <ol>
              {config.sample_questions.map((q, i) => (
                <li key={q} className="border-b">
                  <button
                    onClick={() => onPick(q)}
                    dir="auto"
                    className="grid w-full grid-cols-[3rem_1fr] items-baseline gap-3 bg-background py-4 text-start transition-colors hover:text-primary"
                  >
                    <span className="folio text-3xl">{String(i + 1).padStart(2, "0")}</span>
                    <span className="text-base">{q}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        ) : null}
      </div>
    </div>
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
      onClick={async (e) => {
        e.stopPropagation();
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check /> : <Copy />}
    </Button>
  );
}
