"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { BookOpenText, Loader2 } from "lucide-react";

import { useApp } from "@/components/providers";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type User } from "@/lib/api";

export default function LoginPage() {
  const { t, setUser, config } = useApp();
  const router = useRouter();
  const [mode, setMode] = React.useState<"login" | "register">("login");
  const [loading, setLoading] = React.useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setLoading(true);
    try {
      const res = await api<{ token: string; user: User }>(`/api/auth/${mode}`, {
        method: "POST",
        body: JSON.stringify({ email: f.get("email"), password: f.get("password"), name: f.get("name") ?? "" }),
      });
      setUser(res.user, res.token);
      router.push(res.user.role === "admin" ? "/admin" : "/");
    } catch (err) {
      toast.error(t("error"), { description: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main className="paper grid flex-1 place-items-center p-4">
        <Card className="w-full max-w-sm">
          <CardHeader className="text-center">
            <div className="mx-auto mb-2 grid size-11 place-items-center rounded-xl bg-primary text-primary-foreground">
              <BookOpenText className="size-5" />
            </div>
            <CardTitle className="text-xl">{config?.product_name}</CardTitle>
            <CardDescription>{mode === "login" ? t("login") : "Create account / إنشاء حساب"}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="flex flex-col gap-4">
              {mode === "register" && (
                <div className="grid gap-2">
                  <Label htmlFor="name">Name / الاسم</Label>
                  <Input id="name" name="name" />
                </div>
              )}
              <div className="grid gap-2">
                <Label htmlFor="email">{t("email")}</Label>
                <Input id="email" name="email" type="email" dir="ltr" required autoComplete="email" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password">{t("password")}</Label>
                <Input id="password" name="password" type="password" dir="ltr" required minLength={mode === "register" ? 8 : 1} />
              </div>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="animate-spin" />}
                {mode === "login" ? t("login") : "Register / تسجيل"}
              </Button>
              <button
                type="button"
                className="text-xs text-muted-foreground underline-offset-4 hover:underline"
                onClick={() => setMode(mode === "login" ? "register" : "login")}
              >
                {mode === "login" ? "No account? Register / ليس لديك حساب؟" : "Have an account? Log in / لديك حساب؟"}
              </button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
