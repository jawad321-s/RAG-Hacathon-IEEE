"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Languages, LayoutDashboard, LogIn, LogOut, MessagesSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useApp } from "@/components/providers";
import { cn } from "@/lib/utils";

/** Swiss masthead: product name set large, tagline beside it, a 2px rule underneath. */
export function SiteHeader({ children }: { children?: React.ReactNode }) {
  const { t, lang, setLang, user, setUser, config } = useApp();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-30 border-b-2 border-rule bg-background">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        {children}
        <Link href="/" className="flex items-baseline gap-3">
          <span className="text-xl font-bold tracking-tight">{config?.product_name ?? ""}</span>
          {config?.tagline ? (
            <span className="hidden text-xs text-muted-foreground md:inline">{config.tagline}</span>
          ) : null}
        </Link>

        <nav className="ms-auto flex items-center gap-1">
          {!pathname.startsWith("/chat") && (
            <Button asChild variant="ghost" size="sm">
              <Link href="/chat">
                <MessagesSquare />
                <span className="hidden sm:inline">{t("chat")}</span>
              </Link>
            </Button>
          )}
          {user?.role === "admin" && (
            <Button asChild variant="ghost" size="sm" className={cn(pathname.startsWith("/admin") && "underline underline-offset-8")}>
              <Link href="/admin">
                <LayoutDashboard />
                <span className="hidden sm:inline">{t("admin")}</span>
              </Link>
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label="Language">
            <Languages />
            <span className="hidden sm:inline">{lang === "ar" ? "English" : "العربية"}</span>
          </Button>
          {user ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setUser(null, null);
                router.push("/");
              }}
            >
              <LogOut />
              <span className="hidden sm:inline">{t("logout")}</span>
            </Button>
          ) : (
            <Button asChild size="sm" variant="outline">
              <Link href="/login">
                <LogIn />
                <span className="hidden sm:inline">{t("login")}</span>
              </Link>
            </Button>
          )}
        </nav>
      </div>
    </header>
  );
}
