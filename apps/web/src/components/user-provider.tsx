"use client";

import { Landmark } from "lucide-react";
import { useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { ErrorState } from "@/components/states";
import { ApiError, api, type User } from "@/lib/api";

type UserContextValue = { user: User; logout: () => Promise<void> };
const UserContext = createContext<UserContextValue | null>(null);

export function UserProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const load = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        const setup = await api<{ needed: boolean }>("/auth/setup").catch(
          () => null,
        );
        router.replace(setup?.needed ? "/setup" : "/login");
      } else {
        setError(e as Error);
      }
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }, [router]);

  if (error) {
    return (
      <div className="mx-auto mt-24 max-w-md">
        <ErrorState error={error} onRetry={load} />
      </div>
    );
  }
  if (!user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Landmark className="size-6 animate-pulse text-muted-foreground" />
      </div>
    );
  }
  return (
    <UserContext.Provider value={{ user, logout }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser(): UserContextValue {
  const value = useContext(UserContext);
  if (!value) throw new Error("useUser must be used inside UserProvider");
  return value;
}
