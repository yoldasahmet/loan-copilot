"use client";

import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export type PdfTarget = { id: string; filename: string; page?: number };

export function PdfViewer({
  target,
  onClose,
}: {
  target: PdfTarget | null;
  onClose: () => void;
}) {
  const src = target
    ? `/api/documents/${target.id}/file#page=${target.page ?? 1}`
    : "";
  return (
    <Sheet open={target !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex flex-col gap-0 p-0 data-[side=right]:w-[min(900px,90vw)] data-[side=right]:sm:max-w-none">
        <SheetHeader className="flex-row items-center justify-between border-b pr-12">
          <div>
            <SheetTitle>{target?.filename}</SheetTitle>
            <SheetDescription>Page {target?.page ?? 1}</SheetDescription>
          </div>
          <Button variant="outline" size="sm" asChild>
            <a href={src} target="_blank" rel="noreferrer">
              <ExternalLink /> Open in new tab
            </a>
          </Button>
        </SheetHeader>
        {target && (
          <iframe
            key={src}
            title={target.filename}
            src={src}
            className="flex-1"
          />
        )}
      </SheetContent>
    </Sheet>
  );
}
