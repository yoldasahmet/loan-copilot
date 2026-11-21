import { Badge } from "@/components/ui/badge";
import { STATUSES } from "@/lib/format";
import { cn } from "@/lib/utils";

const STYLES: Record<string, string> = {
  intake: "bg-secondary text-secondary-foreground",
  analysing: "bg-chart-4/15 text-chart-4",
  waiting_review: "bg-warning/20 text-amber-700 dark:text-warning",
  ready: "bg-success/15 text-success",
  closed: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge className={cn("font-medium", STYLES[status])}>
      {STATUSES[status] ?? status}
    </Badge>
  );
}
