import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Case } from "@/lib/api";
import {
  formatDate,
  LEGAL_FORMS,
  moneyFull,
  PURPOSES,
  SECTORS,
} from "@/lib/format";

function Rows({
  rows,
}: {
  rows: [string, string | number | null | undefined][];
}) {
  return (
    <dl className="divide-y">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-4 py-2.5 text-sm">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="text-right font-medium">{value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export function OverviewTab({ c }: { c: Case }) {
  const company = c.company;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Company</CardTitle>
        </CardHeader>
        <CardContent>
          <Rows
            rows={[
              ["Legal form", LEGAL_FORMS[company.legal_form]],
              ["KvK number", company.kvk_number],
              [
                "Sector",
                company.sector_group ? SECTORS[company.sector_group] : null,
              ],
              ["SBI code", company.sbi_code],
              ["Founded", company.founded_year],
              ["Employees", company.employees],
              ["City", company.city],
              ["Contact", company.contact_name],
              ["Contact email", company.contact_email],
            ]}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Loan request</CardTitle>
        </CardHeader>
        <CardContent>
          <Rows
            rows={[
              ["Amount", moneyFull(c.loan_amount)],
              ["Purpose", PURPOSES[c.loan_purpose]],
              ["Term", `${c.loan_term_months} months`],
              ["Application date", formatDate(c.applied_on)],
              ["Advisor", c.advisor?.name],
            ]}
          />
          {c.notes && (
            <p className="mt-4 rounded-lg bg-muted p-3 text-sm">{c.notes}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
