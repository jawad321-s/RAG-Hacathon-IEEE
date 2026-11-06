"use client";

import * as React from "react";
import { toast } from "sonner";
import { FileUp, Loader2, RefreshCw, Trash2 } from "lucide-react";

import { useApp } from "@/components/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";

type Doc = { source: string; chunks: number; pages: number; category: string };

export function DocumentsTab() {
  const { t } = useApp();
  const [docs, setDocs] = React.useState<Doc[]>([]);
  const [total, setTotal] = React.useState(0);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const [category, setCategory] = React.useState("");
  const fileRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(() => {
    api<{ total_chunks: number; documents: Doc[] }>("/api/documents").then((r) => {
      setDocs(r.documents);
      setTotal(r.total_chunks);
    });
  }, []);
  React.useEffect(load, [load]);

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    for (const file of Array.from(files)) {
      setBusy(file.name);
      const fd = new FormData();
      fd.append("file", file);
      fd.append("category", category);
      try {
        const r = await api<{ chunks: number; pages: number; seconds: number }>("/api/documents/upload", { method: "POST", body: fd });
        toast.success(file.name, { description: `${r.chunks} ${t("chunks")} · ${r.pages} ${t("pages")} · ${r.seconds}s` });
      } catch (e) {
        toast.error(file.name, { description: (e as Error).message });
      }
    }
    setBusy(null);
    load();
  }

  async function remove(source: string) {
    if (!confirm(`${t("delete")}: ${source}?`)) return;
    await api(`/api/documents/${encodeURIComponent(source)}`, { method: "DELETE" });
    load();
  }

  async function reindex() {
    setBusy("reindex");
    try {
      const r = await api<{ total_chunks: number }>("/api/documents/reindex", { method: "POST" });
      toast.success(`${r.total_chunks} ${t("chunks")}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
    setBusy(null);
    load();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("upload")}</CardTitle>
          <CardDescription>PDF · DOCX · TXT · MD · HTML · CSV · JSON</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              upload(e.dataTransfer.files);
            }}
            onClick={() => fileRef.current?.click()}
            className={`grid cursor-pointer place-items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center text-sm transition-colors ${
              dragging ? "border-primary bg-accent" : "hover:border-primary/50"
            }`}
          >
            {busy && busy !== "reindex" ? <Loader2 className="size-6 animate-spin text-primary" /> : <FileUp className="size-6 text-primary" />}
            <span className="text-muted-foreground">{busy && busy !== "reindex" ? busy : "Drop files / اسحب الملفات هنا"}</span>
            <input ref={fileRef} type="file" multiple hidden onChange={(e) => upload(e.target.files)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="cat">{t("category")}</Label>
            <Input id="cat" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="policies, faq, 2026 …" />
          </div>
          <Button variant="outline" onClick={reindex} disabled={!!busy}>
            {busy === "reindex" ? <Loader2 className="animate-spin" /> : <RefreshCw />}
            {t("reindex")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("documents")} <span className="font-mono text-sm text-muted-foreground">({docs.length} · {total} {t("chunks")})</span>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>{t("category")}</TableHead>
                <TableHead className="text-end">{t("pages")}</TableHead>
                <TableHead className="text-end">{t("chunks")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {docs.map((d) => (
                <TableRow key={d.source}>
                  <TableCell dir="auto" className="max-w-[280px] truncate font-medium">
                    {d.source}
                  </TableCell>
                  <TableCell>{d.category ? <Badge variant="secondary">{d.category}</Badge> : null}</TableCell>
                  <TableCell className="text-end font-mono">{d.pages || "—"}</TableCell>
                  <TableCell className="text-end font-mono">{d.chunks}</TableCell>
                  <TableCell className="text-end">
                    <Button variant="ghost" size="icon-sm" onClick={() => remove(d.source)} aria-label={t("delete")}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
