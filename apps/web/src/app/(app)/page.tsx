"use client";

import {
  CheckCircle2,
  Clock,
  FolderOpen,
  Hourglass,
  Plus,
  Search,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useUser } from "@/components/user-provider";
import type { CaseList } from "@/lib/api";
import {
  formatDate,
  LEGAL_FORMS,
  moneyFull,
  PURPOSES,
  STATUSES,
} from "@/lib/format";
import { useApi } from "@/lib/use-api";

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon: typeof Clock;
}) {
  return (
    <Card className="py-5">
      <CardContent className="flex items-center justify-between px-5">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tabular-nums">{value}</p>
        </div>
        <span className="flex size-10 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <Icon className="size-5" />
        </span>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useUser();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (status !== "all") params.set("status", status);
  const { data, error, loading, reload } = useApi<CaseList>(`/cases?${params}`);
  const filtered = q.trim() !== "" || status !== "all";

  return (
    <div data-ready={!loading} className="mx-auto max-w-6xl space-y-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            {user.role === "admin"
              ? "All open loan applications"
              : "Your loan applications"}
          </p>
        </div>
        <Button asChild>
          <Link href="/cases/new">
            <Plus /> New case
          </Link>
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {data ? (
          <>
            <StatCard
              label="Open cases"
              value={data.stats.open_cases}
              icon={FolderOpen}
            />
            <StatCard
              label="Waiting for review"
              value={data.stats.waiting_review}
              icon={Hourglass}
            />
            <StatCard
              label="Memos approved this month"
              value={data.stats.memos_approved_this_month}
              icon={CheckCircle2}
            />
            <StatCard
              label="Avg. days intake → ready"
              value={data.stats.avg_days_to_ready ?? "—"}
              icon={Clock}
            />
          </>
        ) : (
          Array.from({ length: 4 }, (_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholders
            <Skeleton key={i} className="h-[94px] rounded-xl" />
          ))
        )}
      </div>

      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-72">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search company"
              className="pl-9"
            />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {Object.entries(STATUSES).map(([value, label]) => (
                <SelectItem key={value} value={value}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {error ? (
          <ErrorState error={error} onRetry={reload} />
        ) : !data ? (
          <TableSkeleton />
        ) : data.items.length === 0 ? (
          filtered ? (
            <EmptyState
              icon={Search}
              title="No matching cases"
              description="Try another search or status."
            />
          ) : (
            <EmptyState
              icon={FolderOpen}
              title="No cases yet"
              description="Start a case to upload annual reports and bank statements for a company."
            >
              <Button asChild>
                <Link href="/cases/new">
                  <Plus /> New case
                </Link>
              </Button>
              {user.role === "admin" && (
                <Button variant="outline" asChild>
                  <Link href="/admin?tab=history">
                    <Upload /> Import history
                  </Link>
                </Button>
              )}
            </EmptyState>
          )
        ) : (
          <div className="rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Company</TableHead>
                  <TableHead>Legal form</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Advisor</TableHead>
                  <TableHead className="pr-4">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((c) => (
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/cases/${c.id}`)}
                  >
                    <TableCell className="pl-4 font-medium">
                      <Link
                        href={`/cases/${c.id}`}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {c.company.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {LEGAL_FORMS[c.company.legal_form]}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moneyFull(c.loan_amount)}
                    </TableCell>
                    <TableCell>{PURPOSES[c.loan_purpose]}</TableCell>
                    <TableCell>
                      <StatusBadge status={c.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.advisor?.name ?? "—"}
                    </TableCell>
                    <TableCell className="pr-4 text-muted-foreground">
                      {formatDate(c.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}
