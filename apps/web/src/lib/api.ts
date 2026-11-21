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
