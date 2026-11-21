"use client";

import { notFound } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";

export default function SetupPage() {
  const [needed, setNeeded] = useState<boolean | null>(null);

  useEffect(() => {
    api<{ needed: boolean }>("/auth/setup")
      .then((s) => setNeeded(s.needed))
      .catch(() => setNeeded(true));
  }, []);

  if (needed === false) notFound(); // setup is only available while no users exist
  if (needed === null) return null;
  return (
    <AuthForm
      title="Create the first admin"
      description="No users exist yet. This account can add advisors, lenders and history."
      endpoint="/auth/setup"
      submitLabel="Create admin account"
      fields={[
        {
          name: "name",
          label: "Full name",
          type: "text",
          autoComplete: "name",
        },
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password (min. 8 characters)",
          type: "password",
          autoComplete: "new-password",
        },
      ]}
    />
  );
}
