"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, type ReactNode, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useUser } from "@/components/user-provider";
import { api, type Case, type User } from "@/lib/api";
import { LEGAL_FORMS, PURPOSES } from "@/lib/format";
import { useApi } from "@/lib/use-api";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  // Wrapping the control in <label> links text and input without ids.
  return (
    <Label className="flex flex-col items-stretch gap-2">
      <span>{label}</span>
      {children}
      {hint && (
        <span className="text-xs font-normal text-muted-foreground">
          {hint}
        </span>
      )}
    </Label>
  );
}

function Choice({
  name,
  options,
  defaultValue,
}: {
  name: string;
  options: Record<string, string>;
  defaultValue: string;
}) {
  return (
    <Select name={name} defaultValue={defaultValue}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(options).map(([value, label]) => (
          <SelectItem key={value} value={value}>
            {label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const orNull = (v: FormDataEntryValue | null) =>
  v === null || v === "" ? null : String(v);
const intOrNull = (v: FormDataEntryValue | null) =>
  orNull(v) === null ? null : Number(v);

export default function NewCasePage() {
  const router = useRouter();
  const { user } = useUser();
  const users = useApi<User[]>(user.role === "admin" ? "/admin/users" : null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toISOString().slice(0, 10);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const f = new FormData(event.currentTarget);
    const body = {
      company: {
        name: f.get("name"),
        kvk_number: orNull(f.get("kvk_number")),
        legal_form: f.get("legal_form"),
        sbi_code: orNull(f.get("sbi_code")),
        founded_year: intOrNull(f.get("founded_year")),
        employees: intOrNull(f.get("employees")),
        city: orNull(f.get("city")),
        contact_name: orNull(f.get("contact_name")),
        contact_email: orNull(f.get("contact_email")),
      },
      loan_amount: f.get("loan_amount"),
      loan_purpose: f.get("loan_purpose"),
      loan_term_months: Number(f.get("loan_term_months")),
      applied_on: orNull(f.get("applied_on")),
      notes: orNull(f.get("notes")),
      advisor_id: orNull(f.get("advisor_id")),
    };
    try {
      const created = await api<Case>("/cases", {
        method: "POST",
        body: JSON.stringify(body),
      });
      router.push(`/cases/${created.id}?tab=documents`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <form
      data-ready="true"
      onSubmit={submit}
      className="mx-auto max-w-4xl space-y-6"
    >
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">New case</h1>
        <p className="text-sm text-muted-foreground">
          Company details and the loan request. You can upload documents in the
          next step.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Company</CardTitle>
          <CardDescription>
            As registered with the Chamber of Commerce.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-5">
          <div className="col-span-2">
            <Field label="Company name">
              <Input name="name" required maxLength={300} />
            </Field>
          </div>
          <Field label="KvK number">
            <Input
              name="kvk_number"
              inputMode="numeric"
              pattern="\d{8}"
              placeholder="8 digits"
            />
          </Field>
          <Field label="Legal form">
            <Choice name="legal_form" options={LEGAL_FORMS} defaultValue="bv" />
          </Field>
          <Field label="SBI code" hint="Used to determine the sector group.">
            <Input
              name="sbi_code"
              inputMode="numeric"
              pattern="\d{2,5}"
              placeholder="e.g. 4322"
            />
          </Field>
          <Field label="City">
            <Input name="city" maxLength={100} />
          </Field>
          <Field label="Founded (year)">
            <Input name="founded_year" type="number" min={1850} max={2100} />
          </Field>
          <Field label="Employees">
            <Input name="employees" type="number" min={0} />
          </Field>
          <Field label="Contact person">
            <Input name="contact_name" maxLength={200} />
          </Field>
          <Field label="Contact email">
            <Input name="contact_email" type="email" />
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Loan request</CardTitle>
          <CardDescription>What the company wants to finance.</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-5">
          <Field label="Amount (EUR)">
            <Input name="loan_amount" type="number" min={1} required />
          </Field>
          <Field label="Purpose">
            <Choice
              name="loan_purpose"
              options={PURPOSES}
              defaultValue="working_capital"
            />
          </Field>
          <Field label="Term (months)">
            <Input
              name="loan_term_months"
              type="number"
              min={1}
              max={360}
              defaultValue={60}
              required
            />
          </Field>
          <Field label="Application date">
            <Input name="applied_on" type="date" defaultValue={today} />
          </Field>
          {user.role === "admin" && users.data && (
            <Field label="Advisor">
              <Choice
                name="advisor_id"
                defaultValue={user.id}
                options={Object.fromEntries(
                  users.data.map((u) => [u.id, u.name]),
                )}
              />
            </Field>
          )}
          <div className="col-span-2">
            <Field label="Notes">
              <Textarea
                name="notes"
                rows={3}
                placeholder="Context for the application"
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex justify-end gap-3">
        <Button type="button" variant="outline" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button type="submit" disabled={busy}>
          {busy && <Loader2 className="animate-spin" />}
          Create case
        </Button>
      </div>
    </form>
  );
}
