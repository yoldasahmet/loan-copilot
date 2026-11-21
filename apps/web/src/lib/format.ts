const full = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

/** Full amount for tables: €1,234,567 */
export function moneyFull(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return full.format(Number(value));
}

/** Compact amount for cards: €1.2M, €450k */
export function moneyCompact(
  value: number | string | null | undefined,
): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1_000_000)
    return `${sign}€${(abs / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (abs >= 1_000) return `${sign}€${Math.round(abs / 1_000)}k`;
  return `${sign}€${Math.round(abs)}`;
}

/** 12 Nov 2026 */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const LEGAL_FORMS: Record<string, string> = {
  bv: "BV",
  eenmanszaak: "Eenmanszaak",
  vof: "VOF",
  other: "Other",
};

export const PURPOSES: Record<string, string> = {
  working_capital: "Working capital",
  equipment: "Equipment",
  real_estate: "Real estate",
  refinancing: "Refinancing",
  growth: "Growth",
  other: "Other",
};

export const STATUSES: Record<string, string> = {
  intake: "Intake",
  analysing: "Analysing",
  waiting_review: "Waiting for review",
  ready: "Ready",
  closed: "Closed",
};

export const DOCUMENT_KINDS: Record<string, string> = {
  annual_report: "Annual report",
  bank_statement: "Bank statement",
  lender_criteria: "Lender criteria",
  other: "Other",
};

export const SECTORS: Record<string, string> = {
  construction: "Construction",
  hospitality: "Hospitality",
  retail: "Retail",
  wholesale: "Wholesale",
  manufacturing: "Manufacturing",
  transport_logistics: "Transport & logistics",
  it_services: "IT services",
  professional_services: "Professional services",
  healthcare_practices: "Healthcare practices",
  agriculture: "Agriculture",
};
