"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { AnalysisTab } from "@/components/analysis/analysis-tab";
import { CaseHeader } from "@/components/case/case-header";
import { DocumentsTab } from "@/components/case/documents-tab";
import { NaturalPersonBanner } from "@/components/case/natural-person-banner";
import { OverviewTab } from "@/components/case/overview-tab";
import { ChatSheet } from "@/components/chat/chat-sheet";
import { LendersTab } from "@/components/matching/lenders-tab";
import { SimilarTab } from "@/components/matching/similar-tab";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { Case } from "@/lib/api";
import { useApi } from "@/lib/use-api";

const TABS = {
  overview: "Overview",
  documents: "Documents",
  analysis: "Analysis",
  similar: "Similar cases",
  lenders: "Lenders",
} as const;

function CasePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const tab = search.get("tab") ?? "overview";
  const chatOpen = search.get("chat") === "1";
  const setChat = (open: boolean) => {
    const params = new URLSearchParams(search);
    if (open) params.set("chat", "1");
    else params.delete("chat");
    router.replace(`/cases/${id}?${params}`, { scroll: false });
  };
  const { data: c, error, reload } = useApi<Case>(`/cases/${id}`);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!c)
    return (
      <div className="space-y-6">
        <Skeleton className="h-14 w-1/2" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-64 w-full" />
      </div>
    );

  return (
    <div data-ready="true" className="mx-auto max-w-6xl space-y-6">
      <CaseHeader c={c} onOpenChat={() => setChat(true)} />
      {(c.company.legal_form === "eenmanszaak" ||
        c.company.legal_form === "vof") && <NaturalPersonBanner />}
      <Tabs
        value={tab}
        onValueChange={(t) =>
          router.replace(`/cases/${id}?tab=${t}`, { scroll: false })
        }
      >
        <TabsList>
          {Object.entries(TABS).map(([value, label]) => (
            <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview" className="pt-4">
          <OverviewTab c={c} />
        </TabsContent>
        <TabsContent value="documents" className="pt-4">
          <DocumentsTab caseId={c.id} />
        </TabsContent>
        <TabsContent value="analysis" className="pt-4">
          <AnalysisTab caseId={c.id} />
        </TabsContent>
        <TabsContent value="similar" className="pt-4">
          <SimilarTab caseId={c.id} />
        </TabsContent>
        <TabsContent value="lenders" className="pt-4">
          <LendersTab caseId={c.id} />
        </TabsContent>
      </Tabs>
      <ChatSheet caseId={c.id} open={chatOpen} onOpenChange={setChat} />
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <CasePage />
    </Suspense>
  );
}
