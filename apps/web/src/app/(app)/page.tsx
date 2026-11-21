"use client";

import { FolderOpen } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const [apiStatus, setApiStatus] = useState<string>("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d: { status: string }) => setApiStatus(d.status))
      .catch(() => setApiStatus("unreachable"));
  }, []);

  return (
    <div
      data-ready={apiStatus !== "checking"}
      className="mx-auto max-w-6xl space-y-8"
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">API status: {apiStatus}</p>
      </div>
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed py-16 text-center">
        <FolderOpen className="size-8 text-muted-foreground" />
        <p className="font-medium">No cases yet</p>
        <Button asChild>
          <Link href="/cases/new">New case</Link>
        </Button>
      </div>
    </div>
  );
}
