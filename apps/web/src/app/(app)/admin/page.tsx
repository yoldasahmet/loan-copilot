"use client";

import { ShieldX } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { HistoryTab } from "@/components/admin/history-tab";
import { LendersTab } from "@/components/admin/lenders-tab";
import { UsersTab } from "@/components/admin/users-tab";
import { EmptyState } from "@/components/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useUser } from "@/components/user-provider";

const TABS = {
  users: "Users",
  lenders: "Lenders",
  history: "History import",
} as const;

function AdminPage() {
  const router = useRouter();
  const { user } = useUser();
  const search = useSearchParams();
  const requested = search.get("tab") ?? "users";
  const tab = requested in TABS ? requested : "users";

  if (user.role !== "admin")
    return (
      <EmptyState
        icon={ShieldX}
        title="Admins only"
        description="Ask an administrator for access."
      />
    );

  return (
    <div data-ready="true" className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Admin</h1>
        <p className="text-sm text-muted-foreground">
          Users, lenders, history and the AI audit log.
        </p>
      </div>
      <Tabs
        value={tab}
        onValueChange={(t) =>
          router.replace(`/admin?tab=${t}`, { scroll: false })
        }
      >
        <TabsList>
          {Object.entries(TABS).map(([value, label]) => (
            <TabsTrigger key={value} value={value}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="users" className="pt-4">
          <UsersTab />
        </TabsContent>
        <TabsContent value="lenders" className="pt-4">
          <LendersTab />
        </TabsContent>
        <TabsContent value="history" className="pt-4">
          <HistoryTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <AdminPage />
    </Suspense>
  );
}
