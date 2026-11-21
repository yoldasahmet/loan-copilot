import { Info } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Ratio } from "@/lib/api";
import { formatRatio } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS = {
  green: { dot: "bg-success", text: "text-success", label: "Within threshold" },
  amber: {
    dot: "bg-warning",
    text: "text-amber-700 dark:text-warning",
    label: "Close to threshold",
  },
  red: {
    dot: "bg-destructive",
    text: "text-destructive",
    label: "Breaches threshold",
  },
  neutral: {
    dot: "bg-muted-foreground/40",
    text: "text-foreground",
    label: "No threshold",
  },
};

function thresholdText(r: Ratio): string {
  if (r.threshold === null) return "No threshold";
  return `${r.higher_is_better ? "≥" : "≤"} ${formatRatio(r.threshold, r.kind)}`;
}

export function RatioCards({ ratios }: { ratios: Ratio[] }) {
  return (
    <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      {ratios.map((r) => {
        const s = STATUS[r.status];
        return (
          <Card key={r.key} className="gap-0 py-4">
            <CardContent className="space-y-2 px-4">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span
                    aria-hidden
                    className={cn("size-2 rounded-full", s.dot)}
                  />
                  <span className="sr-only">{s.label}:</span>
                  {r.label}
                </span>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info
                      className="size-3.5 text-muted-foreground"
                      aria-label={`How ${r.label} is calculated`}
                    />
                  </TooltipTrigger>
                  <TooltipContent>{r.formula}</TooltipContent>
                </Tooltip>
              </div>
              <p className={cn("text-2xl font-semibold tabular-nums", s.text)}>
                {formatRatio(r.value, r.kind)}
              </p>
              <p className="text-xs text-muted-foreground">
                {thresholdText(r)}
                {r.previous !== null &&
                  ` · ${r.year - 1}: ${formatRatio(r.previous, r.kind)}`}
              </p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
