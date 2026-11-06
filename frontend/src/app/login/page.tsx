"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

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
      router.push(res.user.role === "admin" ? "/admin" : "/chat");
    } catch (err) {
      toast.error(t("error"), { description: (err as Error).message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main className="swiss-grid grid flex-1 place-items-center p-4">
        <Card className="w-full max-w-sm">
          <CardHeader className="border-b-2 border-rule pb-4">
            <CardTitle className="text-2xl font-bold">{config?.product_name}</CardTitle>
            <CardDescription>{mode === "login" ? t("login") : t("createAccount")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="flex flex-col gap-4">
              {mode === "register" && (
                <div className="grid gap-2">
                  <Label htmlFor="name">{t("name")}</Label>
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
                {mode === "login" ? t("login") : t("register")}
              </Button>
              <button
                type="button"
                className="text-start text-xs text-primary underline-offset-4 hover:underline"
                onClick={() => setMode(mode === "login" ? "register" : "login")}
              >
                {mode === "login" ? t("noAccount") : t("haveAccount")}
              </button>
            </form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
