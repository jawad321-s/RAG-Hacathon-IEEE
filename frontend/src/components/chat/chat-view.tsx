"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  ArrowUp,
  BookMarked,
  Check,
  Copy,
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
import { Badge } from "@/components/ui/badge";
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
    <div className="flex flex-col gap-1 p-2">
      <Button variant="outline" className="mb-2 justify-start" onClick={newChat}>
        <MessageSquarePlus />
        {t("newChat")}
      </Button>
      {history.map((c) => (
        <button
          key={c.id}
          onClick={() => openConversation(c.id)}
          className={cn(
            "truncate rounded-md px-3 py-2 text-start text-sm hover:bg-accent",
            c.id === conversationId && "bg-accent font-medium"
          )}
          dir="auto"
        >
          {c.title}
        </button>
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

      <div className="mx-auto grid min-h-0 w-full max-w-[1400px] flex-1 grid-cols-1 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[240px_minmax(0,1fr)_400px]">
        {/* conversation history (logged-in users) */}
        <aside className="hidden min-h-0 border-e xl:block">
          {user ? <ScrollArea className="h-full">{historyList}</ScrollArea> : (
            <div className="p-4 text-xs leading-6 text-muted-foreground">{t("poweredBy")}</div>
          )}
        </aside>

        {/* chat column */}
        <section className="paper flex min-h-0 flex-col">
          <ScrollArea className="min-h-0 flex-1">
            <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8">
              {messages.length === 0 ? (
                <EmptyState onPick={ask} />
              ) : (
                messages.map((m, i) =>
                  m.role === "user" ? (
                    <div key={i} className="flex justify-end">
                      <div dir="auto" className="max-w-[85%] rounded-2xl rounded-se-sm bg-primary px-4 py-2.5 text-primary-foreground shadow-sm">
                        {m.content}
                      </div>
                    </div>
                  ) : (
                    <article
                      key={i}
                      className={cn(
                        "group rounded-2xl border bg-card p-5 shadow-sm transition-shadow",
                        selected === i && "ring-2 ring-primary/30"
                      )}
                      onClick={() => setSelected(i)}
                    >
                      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                        {m.streaming ? (
                          <Badge variant="secondary" className="gap-1.5">
                            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                            {m.sources ? `${m.sources.length} ${t("sources")}` : "…"}
                          </Badge>
                        ) : m.refused ? (
                          <Badge variant="outline" className="border-destructive/40 text-destructive">
                            <ShieldAlert />
                            {t("refused")}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="border-primary/30 text-primary">
                            <ShieldCheck />
                            {t("grounded")} · {m.cited?.length ?? 0}/{m.sources?.length ?? 0}
                          </Badge>
                        )}
                        {m.rewritten && m.rewritten !== messages[i - 1]?.content ? (
                          <span className="truncate text-muted-foreground" dir="auto" title={m.rewritten}>
                            {t("searchedAs")}: «{m.rewritten}»
                          </span>
                        ) : null}
                        {m.latency ? (
                          <span className="ms-auto font-mono text-muted-foreground">{(m.latency / 1000).toFixed(1)}s</span>
                        ) : null}
                      </div>
                      <div dir="auto">
                        <AnswerMarkdown
                          text={m.content}
                          streaming={m.streaming}
                          activeCite={selected === i ? activeCite : null}
                          onCite={(n) => cite(i, n)}
                        />
                      </div>
                      {!m.streaming && m.content ? (
                        <div className="mt-4 flex items-center gap-1 border-t pt-3 opacity-70 transition-opacity group-hover:opacity-100">
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
                )
              )}
              <div ref={bottomRef} />
            </div>
          </ScrollArea>

          {/* composer */}
          <div className="border-t bg-background/80 p-3 backdrop-blur">
            <form
              className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring/40"
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
                className="max-h-40 min-h-10 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
              />
              {facets.length > 1 ? (
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  aria-label={t("category")}
                  className="h-9 max-w-36 shrink-0 rounded-md border bg-background px-2 text-xs text-muted-foreground"
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
                <Button type="button" size="icon" variant="secondary" onClick={() => abortRef.current?.abort()} aria-label={t("stop")}>
                  <Square className="size-3.5 fill-current" />
                </Button>
              ) : (
                <Button type="submit" size="icon" disabled={!input.trim()} aria-label={t("send")}>
                  <ArrowUp />
                </Button>
              )}
            </form>
            {config?.disclaimer ? (
              <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-muted-foreground">{config.disclaimer}</p>
            ) : null}
          </div>
        </section>

        {/* sources column */}
        <aside className="hidden min-h-0 flex-col border-s bg-muted/30 lg:flex">
          <div className="flex h-11 items-center gap-2 border-b px-4 text-sm font-medium">
            <BookMarked className="size-4 text-evidence-foreground dark:text-evidence" />
            {t("sources")}
            {shown?.sources?.length ? (
              <span className="ms-auto font-mono text-xs text-muted-foreground">{shown.sources.length}</span>
            ) : null}
          </div>
          <div className="min-h-0 flex-1">{sourcesPanel}</div>
        </aside>
      </div>

      <Sheet open={mobileSources} onOpenChange={setMobileSources}>
        <SheetContent side={lang === "ar" ? "left" : "right"} className="w-[90vw] p-0 sm:max-w-md">
          <SheetHeader className="border-b">
            <SheetTitle>{t("sources")}</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 flex-1">{sourcesPanel}</div>
        </SheetContent>
      </Sheet>

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent side={lang === "ar" ? "right" : "left"} className="w-72 p-0">
          <SheetHeader className="border-b">
            <SheetTitle>{t("history")}</SheetTitle>
          </SheetHeader>
          <ScrollArea className="min-h-0 flex-1">{historyList}</ScrollArea>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const { t, config } = useApp();
  return (
    <div className="flex flex-col items-center pt-[8vh] text-center">
      <div className="mb-6 grid size-14 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-md">
        <BookMarked className="size-6" />
      </div>
      <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{config?.product_name}</h1>
      {config?.tagline ? <p className="mt-3 max-w-md text-muted-foreground">{config.tagline}</p> : null}
      {config?.sample_questions?.length ? (
        <div className="mt-10 w-full max-w-xl">
          <div className="mb-3 text-xs font-medium tracking-wide text-muted-foreground">{t("tryAsking")}</div>
          <div className="grid gap-2 sm:grid-cols-2">
            {config.sample_questions.map((q) => (
              <button
                key={q}
                onClick={() => onPick(q)}
                dir="auto"
                className="rounded-xl border bg-card px-4 py-3 text-start text-sm shadow-xs transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-sm"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : null}
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
        await navigator.clipboard.writeText(text.replace(/\[(\d+)\]/g, "[$1]"));
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
    >
      {done ? <Check /> : <Copy />}
    </Button>
  );
}
