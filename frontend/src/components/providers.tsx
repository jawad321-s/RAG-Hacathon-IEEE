"use client";

import * as React from "react";
import { ThemeProvider } from "next-themes";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { api, getToken, setToken, type PublicConfig, type User } from "@/lib/api";
import { dict, type DictKey, type Lang } from "@/lib/i18n";

type AppState = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (k: DictKey) => string;
  user: User | null;
  setUser: (u: User | null, token?: string | null) => void;
  config: PublicConfig | null;
};

const AppContext = React.createContext<AppState | null>(null);

export function useApp() {
  const ctx = React.useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <Providers>");
  return ctx;
}

const FALLBACK_CONFIG: PublicConfig = {
  product_name: "RAG",
  tagline: "",
  language: "ar",
  sample_questions: [],
  disclaimer: "",
  metadata_filters: [],
  allow_anonymous_chat: true,
};

export function Providers({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = React.useState<Lang>("ar");
  const [user, setUserState] = React.useState<User | null>(null);
  const [config, setConfig] = React.useState<PublicConfig | null>(null);

  React.useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("rag_lang");
    } catch {
      /* ignore */
    }
    const storedLang: Lang | null = stored === "ar" || stored === "en" ? stored : null;
    api<PublicConfig>("/api/config/public")
      .then((c) => {
        setConfig(c);
        setLangState(storedLang ?? c.language);
      })
      .catch(() => {
        setConfig(FALLBACK_CONFIG);
        if (storedLang) setLangState(storedLang);
      });
    if (getToken()) {
      api<User>("/api/auth/me")
        .then(setUserState)
        .catch(() => setToken(null));
    }
  }, []);

  React.useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const value = React.useMemo<AppState>(
    () => ({
      lang,
      setLang: (l) => {
        setLangState(l);
        try {
          localStorage.setItem("rag_lang", l);
        } catch {
          /* ignore */
        }
      },
      t: (k) => dict[lang][k],
      user,
      setUser: (u, token) => {
        if (token !== undefined) setToken(token);
        setUserState(u);
      },
      config,
    }),
    [lang, user, config]
  );

  return (
    <ThemeProvider attribute="class" forcedTheme="light" disableTransitionOnChange>
      <AppContext.Provider value={value}>
        <TooltipProvider>
          {children}
          <Toaster position={lang === "ar" ? "bottom-left" : "bottom-right"} />
        </TooltipProvider>
      </AppContext.Provider>
    </ThemeProvider>
  );
}
