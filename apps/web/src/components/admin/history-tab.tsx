"use client";

import { CheckCircle2, FileJson, Loader2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api } from "@/lib/api";

type ImportResult = {
  imported: number;
  errors: { line: number; message: string }[];
  total_historical: number;
};

export function HistoryTab() {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function importFile(files: FileList | null) {
    if (!files?.[0]) return;
    const form = new FormData();
    form.append("file", files[0]);
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api<ImportResult>("/admin/history/import", {
          method: "POST",
          body: form,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
      <Card>
        <CardHeader>
          <CardTitle>Import historical cases</CardTitle>
          <CardDescription>
            A JSONL file with one past application per line, including lender
            decisions. The format has no name fields; cases get pseudonymous IDs
            like H-0042. See the import format in the repository docs
            (docs/import-format.md).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button onClick={() => input.current?.click()} disabled={busy}>
            {busy ? <Loader2 className="animate-spin" /> : <FileJson />}
            {busy ? "Importing…" : "Upload JSONL"}
          </Button>
          <input
            ref={input}
            type="file"
            accept=".jsonl,.json,.txt"
            className="hidden"
            onChange={(e) => void importFile(e.target.files)}
          />
          <p className="text-xs text-muted-foreground">
            Lender names must match lenders in{" "}
            <Link href="/admin?tab=lenders" className="underline">
              Admin → Lenders
            </Link>
            .
          </p>
        </CardContent>
      </Card>
      <div className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Import failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {result && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {result.errors.length === 0 ? (
                  <CheckCircle2 className="size-5 text-success" />
                ) : (
                  <XCircle className="size-5 text-destructive" />
                )}
                {result.imported} imported, {result.errors.length} line
                {result.errors.length === 1 ? "" : "s"} with errors
              </CardTitle>
              <CardDescription>
                {result.total_historical} historical cases in total.
              </CardDescription>
            </CardHeader>
            {result.errors.length > 0 && (
              <CardContent>
                <ul className="max-h-80 space-y-1.5 overflow-y-auto text-sm">
                  {result.errors.map((e) => (
                    <li key={e.line}>
                      <span className="font-mono text-xs text-muted-foreground">
                        line {e.line}
                      </span>{" "}
                      {e.message}
                    </li>
                  ))}
                </ul>
              </CardContent>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
