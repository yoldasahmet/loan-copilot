"use client";

import { ExternalLink } from "lucide-react";
import { type ReactNode, useState } from "react";
import { type PdfTarget, PdfViewer } from "@/components/case/pdf-viewer";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { SourceRef } from "@/lib/api";

/** Replace [S1] markers in text with clickable chips. */
export function withCitations(
  text: string,
  sources: SourceRef[],
  onCite: (s: SourceRef) => void,
): ReactNode[] {
  return text.split(/(\[S\d+\])/g).map((part, i) => {
    const match = /^\[(S\d+)\]$/.exec(part);
    const source = match && sources.find((s) => s.id === match[1]);
    if (!match) return part;
    if (!source) return part;
    return (
      <button
        // biome-ignore lint/suspicious/noArrayIndexKey: parts of one immutable string
        key={i}
        type="button"
        onClick={() => onCite(source)}
        className="mx-0.5 inline-flex h-5 items-center rounded-md bg-accent px-1.5 align-baseline text-[11px] font-semibold text-accent-foreground hover:bg-primary hover:text-primary-foreground"
      >
        {source.id}
      </button>
    );
  });
}

function pagesLabel(s: SourceRef): string {
  if (!s.page_from) return "";
  return s.page_to && s.page_to !== s.page_from
    ? `pages ${s.page_from}–${s.page_to}`
    : `page ${s.page_from}`;
}

/** Side panel with the cited passage and a link to its page. */
export function SourcePanel({
  source,
  onClose,
}: {
  source: SourceRef | null;
  onClose: () => void;
}) {
  const [pdf, setPdf] = useState<PdfTarget | null>(null);
  return (
    <>
      <Sheet open={source !== null} onOpenChange={(open) => !open && onClose()}>
        <SheetContent className="flex flex-col gap-0 data-[side=right]:w-[min(520px,92vw)] data-[side=right]:sm:max-w-none">
          <SheetHeader className="border-b">
            <SheetTitle>
              {source?.id} · {source?.filename ?? "Source"}
            </SheetTitle>
            <SheetDescription>
              {[source?.section, source && pagesLabel(source)]
                .filter(Boolean)
                .join(" · ")}
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto p-4">
            <pre className="font-sans text-sm leading-relaxed whitespace-pre-wrap">
              {source?.text}
            </pre>
          </div>
          {source?.document_id && (
            <div className="border-t p-4">
              <Button
                className="w-full"
                variant="outline"
                onClick={() =>
                  source.document_id &&
                  setPdf({
                    id: source.document_id,
                    filename: source.filename ?? "Document",
                    page: source.page_from ?? 1,
                  })
                }
              >
                <ExternalLink /> Open page {source.page_from}
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>
      <PdfViewer target={pdf} onClose={() => setPdf(null)} />
    </>
  );
}
