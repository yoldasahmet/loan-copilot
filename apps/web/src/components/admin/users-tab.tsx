"use client";

import { KeyRound, Loader2, UserPlus, Users } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/states";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useUser } from "@/components/user-provider";
import { api, type User } from "@/lib/api";
import { useApi } from "@/lib/use-api";

function RoleSelect({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className="w-32">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="advisor">Advisor</SelectItem>
        <SelectItem value="admin">Admin</SelectItem>
      </SelectContent>
    </Select>
  );
}

export function UsersTab() {
  const { user: me } = useUser();
  const { data, error, reload } = useApi<User[]>("/admin/users");
  const [creating, setCreating] = useState(false);
  const [resetting, setResetting] = useState<User | null>(null);
  const [role, setRole] = useState("advisor");
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    const f = Object.fromEntries(new FormData(event.currentTarget));
    try {
      await api("/admin/users", {
        method: "POST",
        body: JSON.stringify({ ...f, role }),
      });
      toast.success(`${f.name} can now log in`);
      setCreating(false);
      void reload();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(user: User, newRole: string) {
    try {
      await api(`/admin/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: newRole }),
      });
      toast.success(
        `${user.name} is now ${newRole === "admin" ? "an admin" : "an advisor"}`,
      );
      void reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function resetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resetting) return;
    const password = new FormData(event.currentTarget).get("password");
    try {
      await api(`/admin/users/${resetting.id}`, {
        method: "PATCH",
        body: JSON.stringify({ password }),
      });
      toast.success(`Password for ${resetting.name} was reset`);
      setResetting(null);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Advisors see only their own cases. Admins see everything.
        </p>
        <Button onClick={() => setCreating(true)}>
          <UserPlus /> Add user
        </Button>
      </div>
      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : !data ? (
        <TableSkeleton rows={3} />
      ) : data.length === 0 ? (
        <EmptyState icon={Users} title="No users" />
      ) : (
        <div className="rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="pr-4" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="pl-4 font-medium">
                    {u.name}
                    {u.id === me.id && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        (you)
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {u.email}
                  </TableCell>
                  <TableCell>
                    <RoleSelect
                      value={u.role}
                      disabled={u.id === me.id}
                      onChange={(r) => void changeRole(u, r)}
                    />
                  </TableCell>
                  <TableCell className="pr-4 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setResetting(u)}
                    >
                      <KeyRound /> Reset password
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent>
          <form onSubmit={create} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Add user</DialogTitle>
              <DialogDescription>
                Share the initial password with the user securely.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="new-name">Full name</Label>
              <Input id="new-name" name="name" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-email">Email</Label>
              <Input id="new-email" name="email" type="email" required />
            </div>
            <div className="space-y-2">
              <Label>Role</Label>
              <RoleSelect value={role} onChange={setRole} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password">Initial password</Label>
              <Input
                id="new-password"
                name="password"
                type="password"
                minLength={8}
                required
                autoComplete="new-password"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setCreating(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={busy}>
                {busy && <Loader2 className="animate-spin" />}
                Add user
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={resetting !== null}
        onOpenChange={(open) => !open && setResetting(null)}
      >
        <DialogContent>
          <form onSubmit={resetPassword} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Reset password</DialogTitle>
              <DialogDescription>
                Set a new password for {resetting?.name}.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="reset-password">New password</Label>
              <Input
                id="reset-password"
                name="password"
                type="password"
                minLength={8}
                required
                autoComplete="new-password"
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setResetting(null)}
              >
                Cancel
              </Button>
              <Button type="submit">Reset password</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
