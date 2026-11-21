export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Fetch JSON from the API (same origin, proxied to FastAPI). Throws ApiError on failure. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: isForm
      ? init.headers
      : { "Content-Type": "application/json", ...init.headers },
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : (body.detail?.[0]?.msg ?? message);
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, message);
  }
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}

export type Role = "admin" | "advisor";
export type User = { id: string; email: string; name: string; role: Role };

export type LegalForm = "bv" | "eenmanszaak" | "vof" | "other";
export type Purpose =
  | "working_capital"
  | "equipment"
  | "real_estate"
  | "refinancing"
  | "growth"
  | "other";
export type CaseStatus =
  | "intake"
  | "analysing"
  | "waiting_review"
  | "ready"
  | "closed";

export type Company = {
  id: string;
  name: string;
  kvk_number: string | null;
  legal_form: LegalForm;
  sbi_code: string | null;
  sector_group: string | null;
  founded_year: number | null;
  employees: number | null;
  city: string | null;
  contact_name: string | null;
  contact_email: string | null;
};

export type Case = {
  id: string;
  status: CaseStatus;
  loan_amount: string;
  loan_purpose: Purpose;
  loan_term_months: number;
  notes: string | null;
  applied_on: string;
  created_at: string;
  updated_at: string;
  company: Company;
  advisor: { id: string; name: string } | null;
};

export type CaseList = {
  items: Case[];
  stats: {
    open_cases: number;
    waiting_review: number;
    memos_approved_this_month: number;
    avg_days_to_ready: number | null;
  };
};

export type DocumentKind =
  | "annual_report"
  | "bank_statement"
  | "lender_criteria"
  | "other";
export type Doc = {
  id: string;
  case_id: string | null;
  kind: DocumentKind;
  filename: string;
  mime: string;
  size_bytes: number;
  year: number | null;
  page_count: number | null;
  status: "uploaded" | "parsing" | "indexed" | "failed";
  error: string | null;
  injection_flag: boolean;
  injection_allowed: boolean;
  created_at: string;
};

export type FinancialYear = {
  year: number;
  values: Record<string, number | null>;
  sources: Record<string, { document_id: string; page: number }>;
  warnings: { field: string; message: string }[];
  unit: string | null;
  edited_fields: string[];
  edited_by: string | null;
  edited_at: string | null;
};

export type Ratio = {
  key: string;
  label: string;
  kind: "percent" | "multiple";
  value: number | null;
  previous: number | null;
  threshold: number | null;
  higher_is_better: boolean;
  status: "green" | "amber" | "red" | "neutral";
  formula: string;
  year: number;
};

export type CashflowMonth = {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
  end_balance: number | null;
};

export type Cashflow = {
  period_start: string;
  period_end: string;
  months: CashflowMonth[];
  avg_monthly_inflow: number;
  months_negative_net: number;
  negative_balance_days: number | null;
  top_customer: string | null;
  top_customer_share: number | null;
  existing_annual_debt_service: number;
  tax_per_quarter: { quarter: string; amount: number }[];
  categories: { category: string; in: number; out: number }[];
};

export type RedFlag = {
  code: string;
  title: string;
  detail: string;
  severity: "high" | "medium";
};
export type MissingDocument = {
  document: string;
  present: boolean;
  reason: string;
};

export type AnalysisData = {
  running: boolean;
  computed_at: string | null;
  financials: FinancialYear[];
  ratios: {
    year: number | null;
    items: Ratio[];
    errors: string[];
    assumptions: {
      interest_rate: number;
      loan_amount: number;
      term_months: number;
      new_annual_debt_service: number;
      existing_annual_debt_service: number;
      existing_debt_service_from_statements: boolean;
    };
  } | null;
  cashflow: Cashflow | null;
  red_flags: RedFlag[];
  missing_documents: MissingDocument[];
};

export type SourceRef = {
  id: string;
  chunk_id: string;
  document_id: string | null;
  filename: string | null;
  section: string | null;
  page_from: number | null;
  page_to: number | null;
  text: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: SourceRef[];
  created_at: string;
};

/** POST and read a server-sent event stream, calling onEvent for each event. */
export async function postEventStream(
  path: string,
  body: unknown,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const detail = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, detail.detail ?? response.statusText);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf("\n\n");
    while (end !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1] ?? "message";
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (data !== undefined) onEvent(event, JSON.parse(data));
      end = buffer.indexOf("\n\n");
    }
  }
}
