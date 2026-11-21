import { AppSidebar } from "@/components/app-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { UserProvider } from "@/components/user-provider";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <UserProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <header className="flex h-14 items-center justify-between border-b px-4">
            <SidebarTrigger />
            <ThemeToggle />
          </header>
          <main className="flex-1 px-8 py-8">{children}</main>
        </SidebarInset>
      </SidebarProvider>
    </UserProvider>
  );
}
