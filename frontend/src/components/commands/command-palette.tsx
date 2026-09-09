import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Search, Users, Target, ArrowRight, FileText } from "lucide-react";
import { api } from "@/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/button";
import { useHotkey, useDebounce } from "@/hooks/ui";
import { useCaseNavStore } from "@/stores/case-nav";
import { useCan } from "@/lib/permissions";
import { cn } from "@/lib/utils";
import type { EntityType } from "@/types/domain";

interface SearchResult {
  id: string;
  title: string;
  subtitle?: string;
  kind: "case" | "entity" | "action";
  icon?: "case" | "entity";
  action?: () => void;
}

const ENTITY_TYPE_LABEL: Record<EntityType, string> = {
  person: "Person",
  phone: "Phone",
  vehicle: "Vehicle",
  organization: "Organization",
  account: "Account",
  location: "Location",
  document: "Document",
  event: "Event",
};

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const debounced = useDebounce(query.trim(), 200);
  const activeCaseId = useCaseNavStore((s) => s.activeCaseId);
  const canAudit = useCan("audit.read");

  useHotkey(["mod+k"], () => {
    onOpenChange(!open);
    setQuery("");
  });

  useEffect(() => {
    if (open) setQuery("");
  }, [open]);

  const casesQuery = useQuery({
    queryKey: ["palette", "cases", debounced],
    queryFn: () => api.cases.list({ limit: 50, search: debounced || undefined }),
    enabled: open,
    staleTime: 30_000,
  });

  const entitiesQuery = useQuery({
    queryKey: ["palette", "entities", activeCaseId, debounced],
    queryFn: () => api.entities.list(activeCaseId ?? "", { query: debounced || undefined, limit: 25 }),
    enabled: open && Boolean(activeCaseId),
    staleTime: 30_000,
  });

  const go = (to: string, card: "case" | "entity") => {
    onOpenChange(false);
    if (card === "case") useCaseNavStore.getState().setActiveCaseId(to.split("/").pop() ?? null);
    navigate(to);
  };

  const results = useMemo<SearchResult[]>(() => {
    const out: SearchResult[] = [];
    const q = debounced.toLowerCase();

    if (!q) {
      out.push({
        id: "new-case",
        title: "Create a new case",
        kind: "action",
        action: () => navigate("/app/cases?new=1"),
      });
      if (canAudit) {
        out.push({ id: "audit", title: "Open audit log", kind: "action", action: () => navigate("/app/audit") });
      }
      out.push({ id: "settings", title: "Go to settings", kind: "action", action: () => navigate("/app/settings") });
      return out;
    }

    for (const c of (casesQuery.data?.items ?? []).slice(0, 8)) {
      out.push({
        id: `case-${c.id}`,
        title: c.title,
        subtitle: `${c.case_number} · ${c.status}`,
        kind: "case",
        icon: "case",
        action: () => go(`/app/cases/${c.id}`, "case"),
      });
    }
    for (const e of (entitiesQuery.data?.items ?? []).slice(0, 8)) {
      out.push({
        id: `entity-${e.id}`,
        title: e.display_value,
        subtitle: activeCaseId ? `${ENTITY_TYPE_LABEL[e.entity_type]} · in current case` : ENTITY_TYPE_LABEL[e.entity_type],
        kind: "entity",
        icon: "entity",
        action: () => go(`/app/cases/${activeCaseId}/entities/${e.id}`, "entity"),
      });
    }
    if (out.length === 0) {
      out.push({ id: "empty", title: "No matches", subtitle: `Nothing found for “${q}”`, kind: "action" });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, casesQuery.data, entitiesQuery.data, activeCaseId]);

  const loading = casesQuery.isLoading || (Boolean(activeCaseId) && entitiesQuery.isLoading);

  function selectResult(index: number) {
    const result = results[index];
    if (!result) return;
    result.action?.();
    if (!result.action) onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[18vh] w-[min(92vw,560px)] translate-y-0 p-3">
        <DialogTitle className="sr-only">Search</DialogTitle>
        <DialogDescription className="sr-only">Global command search</DialogDescription>

        <div className="flex items-center gap-2 border-b border-border px-2 pb-3">
          <Search className="size-4 shrink-0 text-dim" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                document.getElementById("palette-item-0")?.focus();
              }
            }}
            placeholder="Search cases and entities…"
            className="w-full bg-transparent text-sm text-foreground placeholder:text-dim focus:outline-none"
          />
          {loading ? <Spinner className="size-4 text-dim" /> : null}
        </div>

        {results.length > 0 ? (
          <ul className="max-h-[40vh] overflow-y-auto pt-2">
            {results.map((result, index) => (
              <li key={result.id}>
                <button
                  id={`palette-item-${index}`}
                  type="button"
                  onClick={() => selectResult(index)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") selectResult(index);
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      document.getElementById(`palette-item-${index + 1}`)?.focus();
                    }
                    if (e.key === "ArrowUp") {
                      e.preventDefault();
                      if (index === 0) return;
                      document.getElementById(`palette-item-${index - 1}`)?.focus();
                    }
                  }}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors",
                    "focus:bg-surface-3 focus:outline-none",
                  )}
                >
                  <span
                    className={cn(
                      "grid size-7 shrink-0 place-items-center rounded-md border",
                      result.kind === "entity"
                        ? "border-info/25 bg-info/10 text-info"
                        : "border-accent/25 bg-accent/10 text-accent",
                    )}
                  >
                    {result.icon === "entity" ? (
                      <Users className="size-3.5" />
                    ) : result.icon === "case" ? (
                      <FileText className="size-3.5" />
                    ) : (
                      <ArrowRight className="size-3.5" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-foreground">{result.title}</span>
                    {result.subtitle ? (
                      <span className="block truncate text-[11px] text-dim">{result.subtitle}</span>
                    ) : null}
                  </span>
                  {result.kind === "case" ? <FolderKanban className="size-3.5 shrink-0 text-dim" /> : null}
                  <span className="flex shrink-0 items-center gap-1 text-[10px] uppercase tracking-wider text-dim">
                    {result.kind}
                    <Target className="size-3" />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="flex items-center justify-between border-t border-border px-2 pt-2 text-[10px] text-dim">
          <span>
            <kbd className="mr-1 rounded border border-border-strong px-1 font-mono">↑↓</kbd>
            navigate
            <kbd className="ml-2 mr-1 rounded border border-border-strong px-1 font-mono">↵</kbd>
            select
          </span>
          <span className="font-mono">
            {api.src === "mock" ? "mock adapter" : "live adapter"}
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}