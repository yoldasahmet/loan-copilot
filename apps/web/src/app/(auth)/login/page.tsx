import { AuthForm } from "@/components/auth-form";

export default function LoginPage() {
  return (
    <AuthForm
      title="Log in"
      description="Use the account your administrator created for you."
      endpoint="/auth/login"
      submitLabel="Log in"
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        {
          name: "password",
          label: "Password",
          type: "password",
          autoComplete: "current-password",
        },
      ]}
    />
  );
}
