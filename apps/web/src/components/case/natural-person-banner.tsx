import { UserRound } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function NaturalPersonBanner() {
  return (
    <Alert className="border-warning/50 bg-warning/10">
      <UserRound className="text-amber-700 dark:text-warning" />
      <AlertTitle>Natural person</AlertTitle>
      <AlertDescription>
        The owner is personally liable, so this assessment concerns a natural
        person. Take extra care under GDPR and the EU AI Act.
      </AlertDescription>
    </Alert>
  );
}
