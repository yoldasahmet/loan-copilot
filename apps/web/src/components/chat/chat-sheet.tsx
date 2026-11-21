"use client";

import {
  Loader2,
  MessageSquareText,
  SendHorizonal,
  Sparkles,
} from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { SourcePanel, withCitations } from "@/components/citations";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { type ChatMessage, postEventStream, type SourceRef } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What explains the change in revenue last year?",
  "What is the DSCR and how is it calculated?",
  "Which risks does the directors' report mention?",
];

export function ChatSheet({
  caseId,
  open,
  onOpenChange,
}: {
  caseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const history = useApi<ChatMessage[]>(open ? `/cases/${caseId}/chat` : null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<SourceRef | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (history.data) setMessages(history.data);
  }, [history.data]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  });

  async function ask(question: string) {
    if (!question.trim() || busy) return;
    setBusy(true);
    setDraft("");
    const now = new Date().toISOString();
    const answer: ChatMessage = {
      id: `pending-${now}`,
      role: "assistant",
      content: "",
      sources: [],
      created_at: now,
    };
    setMessages((m) => [
      ...m,
      {
        id: `q-${now}`,
        role: "user",
        content: question,
        sources: [],
        created_at: now,
      },
      answer,
    ]);
    const update = (patch: Partial<ChatMessage>) =>
      setMessages((m) =>
        m.map((msg) => (msg.id === answer.id ? { ...msg, ...patch } : msg)),
      );
    let text = "";
    try {
      await postEventStream(
        `/cases/${caseId}/chat`,
        { message: question },
        (event, data) => {
          if (event === "token") {
            text += (data as { text: string }).text;
            update({ content: text });
          } else if (event === "sources") {
            update({ sources: data as SourceRef[] });
          } else if (event === "error") {
            update({
              content: `${text}\n\n⚠ ${(data as { message: string }).message}`,
            });
          }
        },
      );
    } catch (e) {
      update({ content: `⚠ ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          data-ready={open && !history.loading}
          className="flex flex-col gap-0 p-0 data-[side=right]:w-[min(560px,94vw)] data-[side=right]:sm:max-w-none"
        >
          <SheetHeader className="border-b">
            <SheetTitle className="flex items-center gap-2">
              <MessageSquareText className="size-4" /> Ask the case documents
            </SheetTitle>
            <SheetDescription>
              Answers cite the documents. Names are pseudonymised before they
              reach the AI.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 space-y-5 overflow-y-auto px-4 py-5">
            {history.loading ? (
              <div className="space-y-3">
                <Skeleton className="ml-auto h-10 w-2/3" />
                <Skeleton className="h-24 w-5/6" />
              </div>
            ) : messages.length === 0 ? (
              <div className="space-y-3 pt-6 text-center">
                <Sparkles className="mx-auto size-6 text-primary" />
                <p className="font-medium">Ask about this application</p>
                <div className="flex flex-col gap-2 pt-2">
                  {SUGGESTIONS.map((s) => (
                    <Button
                      key={s}
                      variant="outline"
                      className="h-auto justify-start whitespace-normal py-2 text-left"
                      onClick={() => void ask(s)}
                    >
                      {s}
                    </Button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  className={cn(
                    "flex",
                    m.role === "user" ? "justify-end" : "justify-start",
                  )}
                >
                  <div
                    className={cn(
                      "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
                      m.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted",
                    )}
                  >
                    {m.role === "assistant" && m.content === "" ? (
                      <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    ) : m.role === "assistant" ? (
                      withCitations(m.content, m.sources, setSource)
                    ) : (
                      m.content
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={end} />
          </div>

          <form onSubmit={submit} className="flex items-end gap-2 border-t p-4">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask(draft);
                }
              }}
              placeholder="Ask a question about the documents…"
              rows={2}
              className="min-h-0 resize-none"
              aria-label="Question"
            />
            <Button
              type="submit"
              size="icon"
              disabled={busy || !draft.trim()}
              aria-label="Send"
            >
              {busy ? <Loader2 className="animate-spin" /> : <SendHorizonal />}
            </Button>
          </form>
        </SheetContent>
      </Sheet>
      <SourcePanel source={source} onClose={() => setSource(null)} />
    </>
  );
}
