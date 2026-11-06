"use client";

import * as React from "react";
import Link from "next/link";
import { BarChart3, FlaskConical, Library, Microscope } from "lucide-react";

import { AnalyticsTab } from "@/components/admin/analytics-tab";
import { DocumentsTab } from "@/components/admin/documents-tab";
import { EvalTab } from "@/components/admin/eval-tab";
import { PlaygroundTab } from "@/components/admin/playground-tab";
import { useApp } from "@/components/providers";
import { SiteHeader } from "@/components/site-header";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function AdminPage() {
  const { t, user } = useApp();

  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-[1400px] flex-1 p-4 sm:p-6">
        {user?.role !== "admin" ? (
          <div className="grid place-items-center gap-4 py-24 text-center text-muted-foreground">
            <p>Admin only · للمسؤول فقط</p>
            <Button asChild>
              <Link href="/login">{t("login")}</Link>
            </Button>
          </div>
        ) : (
          <Tabs defaultValue="analytics" className="gap-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold tracking-tight">{t("admin")}</h1>
                <p className="text-sm text-muted-foreground">{user.email}</p>
              </div>
              <TabsList className="h-10 max-w-full overflow-x-auto">
                <TabsTrigger value="analytics" className="px-3">
                  <BarChart3 />
                  {t("analytics")}
                </TabsTrigger>
                <TabsTrigger value="documents" className="px-3">
                  <Library />
                  {t("documents")}
                </TabsTrigger>
                <TabsTrigger value="eval" className="px-3">
                  <FlaskConical />
                  {t("evaluation")}
                </TabsTrigger>
                <TabsTrigger value="playground" className="px-3">
                  <Microscope />
                  {t("playground")}
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="analytics">
              <AnalyticsTab />
            </TabsContent>
            <TabsContent value="documents">
              <DocumentsTab />
            </TabsContent>
            <TabsContent value="eval">
              <EvalTab />
            </TabsContent>
            <TabsContent value="playground">
              <PlaygroundTab />
            </TabsContent>
          </Tabs>
        )}
      </main>
    </div>
  );
}
