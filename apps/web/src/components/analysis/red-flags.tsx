import { CheckCircle2, CircleAlert, CircleX, ShieldCheck } from "lucide-react";
import type { MissingDocument, RedFlag } from "@/lib/api";
import { cn } from "@/lib/utils";

export function RedFlagList({ flags }: { flags: RedFlag[] }) {
  if (flags.length === 0)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <ShieldCheck className="size-4 text-success" /> No red flags against the
        configured thresholds.
      </p>
    );
  return (
    <ul className="space-y-3">
      {flags.map((f) => (
        <li key={f.code} className="flex gap-3">
          <CircleAlert
            className={cn(
              "mt-0.5 size-4 shrink-0",
              f.severity === "high"
                ? "text-destructive"
                : "text-amber-600 dark:text-warning",
            )}
          />
          <div>
            <p className="text-sm font-medium">{f.title}</p>
            <p className="text-sm text-muted-foreground">{f.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function MissingDocumentList({ items }: { items: MissingDocument[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((d) => (
        <li key={d.document} className="flex items-start gap-3 text-sm">
          {d.present ? (
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
          ) : (
            <CircleX className="mt-0.5 size-4 shrink-0 text-destructive" />
          )}
          <div>
            <p className={cn(d.present && "text-muted-foreground")}>
              {d.document}
            </p>
            {!d.present && (
              <p className="text-xs text-muted-foreground">{d.reason}</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
