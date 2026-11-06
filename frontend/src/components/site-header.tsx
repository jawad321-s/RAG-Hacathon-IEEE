"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { BookOpenText, Languages, LayoutDashboard, LogIn, LogOut, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useApp } from "@/components/providers";
import { cn } from "@/lib/utils";

export function SiteHeader({ children }: { children?: React.ReactNode }) {
  const { t, lang, setLang, user, setUser, config } = useApp();
  const { resolvedTheme, setTheme } = useTheme();
  const pathname = usePathname();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-3 px-4">
        {children}
        <Link href="/" className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <BookOpenText className="size-4" />
          </span>
          <span className="flex flex-col leading-tight">
            <span className="font-semibold tracking-tight">{config?.product_name ?? "…"}</span>
            {config?.tagline ? (
              <span className="hidden text-[11px] text-muted-foreground sm:block">{config.tagline}</span>
            ) : null}
          </span>
        </Link>

        <nav className="ms-auto flex items-center gap-1">
          {user?.role === "admin" && (
            <Button asChild variant="ghost" size="sm" className={cn(pathname.startsWith("/admin") && "bg-accent")}>
              <Link href="/admin">
                <LayoutDashboard />
                <span className="hidden sm:inline">{t("admin")}</span>
              </Link>
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Language"
            onClick={() => setLang(lang === "ar" ? "en" : "ar")}
            title={lang === "ar" ? "English" : "العربية"}
          >
            <Languages />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label="Theme"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          >
            <Sun className="dark:hidden" />
            <Moon className="hidden dark:block" />
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
