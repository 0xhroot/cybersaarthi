import { useState } from "react";
import { MoreHorizontal, UserCheck, UserX, Pause, Play, ShieldCheck } from "lucide-react";
import { useAdminPendingUsers, useAdminUserMutation, useAdminUsers } from "@/hooks/queries";
import { PageContainer, PageHeader } from "@/components/layout/page";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/loading";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { formatRelative } from "@/lib/utils";
import type { AccountStatus, AdminUserOut, Role } from "@/types/domain";

const STATUS_TONES: Record<string, "neutral" | "success" | "critical" | "accent"> = {
  ACTIVE: "success",
  PENDING: "accent",
  SUSPENDED: "critical",
  REJECTED: "neutral",
};

function statusTone(status: AccountStatus) {
  return STATUS_TONES[status] ?? "neutral";
}

const ROLES: Role[] = ["ADMIN", "INVESTIGATOR", "ANALYST", "VIEWER"];

function EmailCell({ email }: { email: string }) {
  return (
    <TD className="hidden md:table-cell">
      <span className="text-xs text-muted">{email}</span>
    </TD>
  );
}

function ApproveDialog({
  user,
  onApprove,
  busy,
}: {
  user: AdminUserOut | null;
  onApprove: (role: Role) => void;
  busy: boolean;
}) {
  const [role, setRole] = useState<Role>("ANALYST");
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (next) setRole("ANALYST"); }}>
      <Button
        size="sm"
        variant="secondary"
        onClick={() => setOpen(true)}
        className="whitespace-nowrap"
      >
        <UserCheck className="size-3.5" />
        Approve
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Approve {user?.username}</DialogTitle>
          <DialogDescription>
            Activating the account grants the selected role. Roles cannot be trusted from the
            registration request — choose one explicitly.
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 space-y-2">
          <Label>Role</Label>
          <Select value={role} onValueChange={(value) => setRole(value as Role)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
          <Button size="sm" loading={busy} onClick={() => onApprove(role)}>Approve account</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UserActions({
  user,
  onAction,
  busy,
}: {
  user: AdminUserOut;
  onAction: (action: import("@/hooks/queries").AdminUserAction) => void;
  busy: boolean;
}) {
  const isActive = user.status === "ACTIVE";
  const isAdmin = user.roles.includes("ADMIN");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Manage ${user.username}`}>
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{user.username}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {user.status === "PENDING" ? (
          <>
            <DropdownMenuItem disabled={busy} onSelect={() => onAction({ type: "approve", userId: user.id, role: "ANALYST" })}>
              <UserCheck className="size-4" /> Approve as ANALYST
            </DropdownMenuItem>
            <DropdownMenuItem disabled={busy} onSelect={() => onAction({ type: "reject", userId: user.id })}>
              <UserX className="size-4" /> Reject
            </DropdownMenuItem>
          </>
        ) : null}
        {isActive ? (
          <DropdownMenuItem disabled={busy || (isAdmin && user.status === "ACTIVE")} onSelect={() => onAction({ type: "suspend", userId: user.id })}>
            <Pause className="size-4" /> Suspend
          </DropdownMenuItem>
        ) : user.status === "SUSPENDED" || user.status === "REJECTED" ? (
          <DropdownMenuItem disabled={busy} onSelect={() => onAction({ type: "activate", userId: user.id })}>
            <Play className="size-4" /> Activate
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        {ROLES.filter((r) => r !== (user.roles[0] ?? null)).map((role) => (
          <DropdownMenuItem
            key={role}
            disabled={busy}
            onSelect={() => onAction({ type: "role", userId: user.id, role })}
          >
            <ShieldCheck className="size-4" /> Assign {role}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function AdminUsersPage() {
  const [tab, setTab] = useState<"pending" | "all">("pending");
  const [status, setStatus] = useState("all");
  const pending = useAdminPendingUsers();
  const all = useAdminUsers({
    limit: 200,
    status: status === "all" ? undefined : status,
  });
  const mutation = useAdminUserMutation();
  const busy = mutation.isPending;
  const [approving, setApproving] = useState<AdminUserOut | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  function showError(err: unknown, actionLabel: string) {
    setActionError(`${actionLabel} failed: ${(err as Error)?.message ?? "unexpected error"}`);
  }

  function handleAction(action: import("@/hooks/queries").AdminUserAction) {
    setActionError(null);
    mutation.mutate(action, {
      onSuccess: () => setActionError(null),
      onError: (err) => showError(err, "Account action"),
    });
  }

  function handleApprove(role: Role) {
    if (!approving) return;
    setActionError(null);
    mutation.mutate(
      { type: "approve", userId: approving.id, role },
      {
        onSuccess: () => setActionError(null),
        onError: (err) => showError(err, "Approval"),
      },
    );
    setApproving(null);
  }

  const pendingList = pending.data?.items ?? [];
  const allList = all.data?.items ?? [];

  return (
    <PageContainer>
      <PageHeader
        eyebrow="Administration"
        title="Users & approvals"
        description="Approve registration requests, suspend accounts and assign roles. Actions are audit-logged."
      />

      {actionError ? (
        <div
          role="alert"
          className="mt-4 rounded-md border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {actionError}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2 border-b border-border">
        <button
          type="button"
          onClick={() => setTab("pending")}
          className={`rounded-t-md px-3 py-2 text-sm font-medium transition-colors ${tab === "pending" ? "border-b-2 border-accent text-foreground" : "text-muted hover:text-foreground"}`}
        >
          Pending approvals
          {pendingList.length > 0 ? <span className="ml-1.5 text-accent">({pendingList.length})</span> : null}
        </button>
        <button
          type="button"
          onClick={() => setTab("all")}
          className={`rounded-t-md px-3 py-2 text-sm font-medium transition-colors ${tab === "all" ? "border-b-2 border-accent text-foreground" : "text-muted hover:text-foreground"}`}
        >
          All users
        </button>
      </div>

      {tab === "all" ? (
        <div className="mt-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Select value={status} onValueChange={(value) => setStatus(value)}>
              <SelectTrigger className="w-[180px]"><SelectValue placeholder="All statuses" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="PENDING">Pending</SelectItem>
                <SelectItem value="ACTIVE">Active</SelectItem>
                <SelectItem value="SUSPENDED">Suspended</SelectItem>
                <SelectItem value="REJECTED">Rejected</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {renderUsers(all, allList, busy, handleAction, setApproving)}
        </div>
      ) : (
        <div className="mt-4">{renderUsers(pending, pendingList, busy, handleAction, setApproving)}</div>
      )}

      <ApproveDialog user={approving} busy={busy} onApprove={handleApprove} />
    </PageContainer>
  );

  function renderUsers(
    query: { isLoading: boolean; isError: boolean; error: unknown; refetch: () => void },
    items: AdminUserOut[],
    loading: boolean,
    onAction: (a: import("@/hooks/queries").AdminUserAction) => void,
    onApprove: (u: AdminUserOut) => void,
  ) {
    if (query.isLoading) {
      return (
        <Card><CardContent className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-11" />)}
        </CardContent></Card>
      );
    }
    if (query.isError) {
      return (
        <Card><ErrorState error={query.error} onRetry={() => query.refetch()} /></Card>
      );
    }
    if (items.length === 0) {
      return (
        <Card>
          <EmptyState
            title={tab === "pending" ? "No pending requests" : "No users found"}
            description={tab === "pending" ? "New registration requests will appear here." : "Try a different filter."}
          />
        </Card>
      );
    }
    return (
      <Card>
        <Table>
          <THead>
            <TR>
              <TH>User</TH>
              <TH className="hidden md:table-cell">Email</TH>
              <TH>Status</TH>
              <TH>Role</TH>
              <TH className="hidden lg:table-cell">Requested</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((user) => (
              <TR key={user.id}>
                <TD>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">{user.username}</span>
                    {user.roles.includes("ADMIN") ? <ShieldCheck className="size-3.5 text-accent" aria-label="Administrator" /> : null}
                  </div>
                </TD>
                <EmailCell email={user.email} />
                <TD><Badge tone={statusTone(user.status)}>{user.status}</Badge></TD>
                <TD className="text-xs text-muted">{user.roles.join(", ") || "—"}</TD>
                <TD className="hidden text-xs text-dim lg:table-cell" title={user.created_at}>
                  {formatRelative(user.created_at)}
                </TD>
                <TD className="text-right">
                  {user.status === "PENDING" ? (
                    <div className="flex items-center justify-end gap-2">
                      <Button size="sm" variant="secondary" onClick={() => onApprove(user)} className="whitespace-nowrap">
                        <UserCheck className="size-3.5" /> Approve
                      </Button>
                      <UserActions user={user} busy={loading} onAction={onAction} />
                    </div>
                  ) : (
                    <UserActions user={user} busy={loading} onAction={onAction} />
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </Card>
    );
  }
}