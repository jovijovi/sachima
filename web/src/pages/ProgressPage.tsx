import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  ListChecks,
  Loader2,
  RefreshCw,
  Terminal,
  XCircle,
} from "lucide-react";
import { H2 } from "@nous-research/ui/ui/components/typography/h2";
import { api } from "@/lib/api";
import type {
  ProgressEventRecord,
  ProgressIterationUsage,
  ProgressTodoItem,
  ProgressTransactionSummary,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";

const STATUS_OPTIONS = ["all", "running", "completed", "failed"] as const;
type StatusFilter = (typeof STATUS_OPTIONS)[number];

const STATUS_BADGE: Record<
  string,
  { label: string; tone: "success" | "warning" | "destructive" | "outline" }
> = {
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "destructive" },
  running: { label: "Running", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "outline" },
};

function statusBadge(status?: string | null) {
  return STATUS_BADGE[status || ""] ?? { label: status || "Unknown", tone: "outline" as const };
}

function formatTime(ts?: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

function relativeTime(ts?: number | null): string {
  if (!ts) return "—";
  return timeAgo(ts);
}

function duration(seconds?: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

/** "current / max" work-round label, or null when no meaningful budget exists
 *  (omit rather than show a misleading "0 / 0"). */
function roundsLabel(usage?: ProgressIterationUsage | null): string | null {
  if (!usage || usage.maximum <= 0) return null;
  return `${usage.current} / ${usage.maximum}`;
}

// ── Structured todo preview (two-level, capped) ──────────────────────────
const TODO_GLYPH: Record<string, string> = {
  completed: "✅",
  in_progress: "➡️",
  pending: "○",
  cancelled: "⚪",
};
const TODO_MAX_VISIBLE = 12;

function todoGlyph(status?: string | null): string {
  return TODO_GLYPH[(status || "").toLowerCase()] ?? "○";
}

function todoStruck(status?: string | null): boolean {
  const normalized = (status || "").toLowerCase();
  return normalized === "completed" || normalized === "cancelled";
}

function todoDepth(item: ProgressTodoItem): number {
  return (item.depth ?? 0) >= 1 ? 1 : 0;
}

/** Group a flat todo list into ordered two-level blocks. A child whose
 *  parent_id resolves to a top-level id nests under it; roots and any
 *  orphaned/over-nested children each become their own block. */
function buildTodoBlocks(
  items: ProgressTodoItem[],
): Array<{ top: ProgressTodoItem; children: ProgressTodoItem[] }> {
  const rootIds = new Set(
    items.filter((it) => todoDepth(it) === 0 && it.id).map((it) => it.id),
  );
  const childrenByParent = new Map<string, ProgressTodoItem[]>();
  for (const it of items) {
    if (todoDepth(it) === 1 && it.parent_id && rootIds.has(it.parent_id)) {
      const list = childrenByParent.get(it.parent_id) ?? [];
      list.push(it);
      childrenByParent.set(it.parent_id, list);
    }
  }
  const blocks: Array<{ top: ProgressTodoItem; children: ProgressTodoItem[] }> = [];
  for (const it of items) {
    if (todoDepth(it) === 1 && it.parent_id && rootIds.has(it.parent_id)) continue;
    const children = todoDepth(it) === 0 ? childrenByParent.get(it.id) ?? [] : [];
    blocks.push({ top: it, children });
  }
  return blocks;
}

function TodoItemRow({ item, indent }: { item: ProgressTodoItem; indent?: boolean }) {
  return (
    <div className={cn("flex items-start gap-1.5 text-xs normal-case", indent && "pl-4")}>
      <span aria-hidden className="shrink-0 leading-5">
        {todoGlyph(item.status)}
      </span>
      <span
        className={cn(
          "min-w-0 break-words leading-5",
          todoStruck(item.status) ? "text-muted-foreground line-through" : "text-foreground",
        )}
      >
        {item.content}
      </span>
    </div>
  );
}

function TodoBlock({ items }: { items: ProgressTodoItem[] }) {
  if (!items || items.length === 0) return null;
  const blocks = buildTodoBlocks(items);
  const total = blocks.reduce((sum, block) => sum + 1 + block.children.length, 0);
  const rows: ReactNode[] = [];
  for (const block of blocks) {
    if (rows.length >= TODO_MAX_VISIBLE) break;
    if (block.children.length > 0) {
      const done = block.children.filter(
        (child) => (child.status || "").toLowerCase() === "completed",
      ).length;
      rows.push(
        <div
          key={`group-${block.top.id}`}
          className="flex items-center gap-1.5 text-xs font-medium text-foreground normal-case"
        >
          <span aria-hidden>▸</span>
          <span className="min-w-0 break-words">{block.top.content}</span>
          <span className="text-muted-foreground">
            {done}/{block.children.length}
          </span>
        </div>,
      );
      for (const child of block.children) {
        if (rows.length >= TODO_MAX_VISIBLE) break;
        rows.push(<TodoItemRow key={`child-${child.id}`} item={child} indent />);
      }
    } else {
      rows.push(<TodoItemRow key={`flat-${block.top.id}`} item={block.top} />);
    }
  }
  const hidden = total - rows.length;
  return (
    <div className="mt-3 border-t border-border/60 pt-3">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-foreground normal-case">
        <ListChecks className="h-3.5 w-3.5" />
        To-dos ({items.length})
      </div>
      <div className="flex flex-col gap-1">
        {rows}
        {hidden > 0 && (
          <div className="text-[11px] text-muted-foreground normal-case">… {hidden} more</div>
        )}
      </div>
    </div>
  );
}

function TransactionRow({
  tx,
  selected,
  onSelect,
}: {
  tx: ProgressTransactionSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  const badge = statusBadge(tx.status);
  const last = tx.last_operation;
  const rounds = roundsLabel(tx.iteration_usage);
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "group w-full border border-border bg-card/50 p-3 text-left transition-colors cursor-pointer",
        "hover:border-primary/40 hover:bg-primary/5",
        selected && "border-primary/60 bg-primary/10",
      )}
    >
      <div className="flex items-start gap-3">
        <Activity className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground group-hover:text-primary" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-foreground normal-case">
              {tx.title || tx.id}
            </p>
            <Badge tone={badge.tone} className="text-[9px]">
              {badge.label}
            </Badge>
          </div>
          <p className="mt-1 truncate font-mono-ui text-[11px] text-muted-foreground normal-case">
            {tx.id}
          </p>
          {last && (
            <p className="mt-2 truncate text-xs text-muted-foreground normal-case">
              {last.tool_name || last.event_type}: {last.preview || last.status}
            </p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
            <span>{tx.operation_count} ops</span>
            {rounds && (
              <>
                <span>·</span>
                <span>Rounds: {rounds}</span>
              </>
            )}
            {tx.todo_items && tx.todo_items.length > 0 && (
              <>
                <span>·</span>
                <span>{tx.todo_items.length} to-dos</span>
              </>
            )}
            <span>·</span>
            <span>{relativeTime(tx.updated_at || tx.started_at)}</span>
          </div>
        </div>
        <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
      </div>
    </button>
  );
}

function EventRow({ event }: { event: ProgressEventRecord }) {
  const op = event.operation;
  const badge = statusBadge(op?.status || event.transaction.status);
  const title = op
    ? `${op.tool_name || op.event_type || "operation"}`
    : "Transaction snapshot";
  const preview = op?.preview || op?.args_preview || event.transaction.title;
  return (
    <div className="border-b border-border/60 p-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        {op?.is_error ? (
          <XCircle className="h-4 w-4 text-destructive" />
        ) : event.record_type === "progress.snapshot" ? (
          <CheckCircle2 className="h-4 w-4 text-success" />
        ) : (
          <Terminal className="h-4 w-4 text-muted-foreground" />
        )}
        <span className="font-mono-ui text-xs text-foreground normal-case">{title}</span>
        <Badge tone={badge.tone} className="text-[9px]">
          {badge.label}
        </Badge>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {formatTime(event.written_at)}
        </span>
      </div>
      {preview && (
        <p className="mt-2 whitespace-pre-wrap break-words text-xs text-muted-foreground normal-case">
          {preview}
        </p>
      )}
      {op && (
        <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-muted-foreground normal-case">
          <span>event: {op.event_type || "—"}</span>
          <span>duration: {duration(op.duration)}</span>
          {op.id && <span className="font-mono-ui">id: {op.id}</span>}
        </div>
      )}
    </div>
  );
}

export default function ProgressPage() {
  const [transactions, setTransactions] = useState<ProgressTransactionSummary[]>([]);
  const [events, setEvents] = useState<ProgressEventRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [skippedLines, setSkippedLines] = useState(0);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => transactions.find((tx) => tx.id === selectedId) ?? null,
    [selectedId, transactions],
  );

  const loadTransactions = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getProgressTransactions({ limit: 50, status })
      .then((resp) => {
        setEnabled(resp.enabled);
        setTransactions(resp.transactions);
        setSkippedLines(resp.skipped_lines);
        if (!selectedId || !resp.transactions.some((tx) => tx.id === selectedId)) {
          setSelectedId(resp.transactions[0]?.id ?? null);
        }
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [selectedId, status]);

  useEffect(() => {
    loadTransactions();
  }, [loadTransactions]);

  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      return;
    }
    setDetailLoading(true);
    api
      .getProgressTransactionEvents(selectedId, 200)
      .then((resp) => {
        setEnabled(resp.enabled);
        setEvents(resp.events);
        setSkippedLines((current) => Math.max(current, resp.skipped_lines));
      })
      .catch((err) => setError(String(err)))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const running = transactions.filter((tx) => tx.status === "running").length;
  const failed = transactions.filter((tx) => tx.status === "failed").length;
  const completed = transactions.filter((tx) => tx.status === "completed").length;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-muted-foreground" />
          <H2 variant="sm">Progress</H2>
          {loading && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
          <Badge tone={enabled ? "success" : "outline"} className="text-[10px]">
            {enabled ? "Event store enabled" : "Event store off"}
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
            className="h-8 border border-border bg-background px-2 text-xs uppercase text-foreground"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <Button
            outlined
            size="sm"
            onClick={loadTransactions}
            disabled={loading}
            prefix={<RefreshCw className="h-3 w-3" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive normal-case">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!enabled && (
        <div className="border border-warning/30 bg-warning/10 p-3 text-sm text-warning normal-case">
          Progress persistence is disabled. Enable display.task_tracker.persist_events with the jsonl event store to populate this dashboard.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-sm">Running</CardTitle></CardHeader>
          <CardContent className="px-4 pb-4 text-2xl text-warning">{running}</CardContent>
        </Card>
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-sm">Completed</CardTitle></CardHeader>
          <CardContent className="px-4 pb-4 text-2xl text-success">{completed}</CardContent>
        </Card>
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-sm">Failed</CardTitle></CardHeader>
          <CardContent className="px-4 pb-4 text-2xl text-destructive">{failed}</CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Clock className="h-4 w-4" />
              Transactions
            </CardTitle>
          </CardHeader>
          <CardContent className="flex max-h-[680px] flex-col gap-2 overflow-y-auto p-3">
            {transactions.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted-foreground normal-case">
                No persisted progress transactions yet.
              </p>
            ) : (
              transactions.map((tx) => (
                <TransactionRow
                  key={tx.id}
                  tx={tx}
                  selected={tx.id === selectedId}
                  onSelect={() => setSelectedId(tx.id)}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Terminal className="h-4 w-4" />
              Timeline
              {detailLoading && <Loader2 className="h-3 w-3 animate-spin text-primary" />}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {selected ? (
              <>
                <div className="border-b border-border/70 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-medium text-foreground normal-case">{selected.title}</h3>
                    <Badge tone={statusBadge(selected.status).tone} className="text-[9px]">
                      {statusBadge(selected.status).label}
                    </Badge>
                  </div>
                  <div className="mt-2 grid gap-1 text-[11px] text-muted-foreground normal-case sm:grid-cols-2">
                    <span>Started: {formatTime(selected.started_at)}</span>
                    <span>Updated: {formatTime(selected.updated_at)}</span>
                    <span>Completed: {formatTime(selected.completed_at)}</span>
                    <span>Operations: {selected.operation_count}</span>
                    {roundsLabel(selected.iteration_usage) && (
                      <span>Rounds: {roundsLabel(selected.iteration_usage)}</span>
                    )}
                  </div>
                  {selected.todo_items && selected.todo_items.length > 0 && (
                    <TodoBlock items={selected.todo_items} />
                  )}
                </div>
                <div className="max-h-[560px] overflow-y-auto">
                  {events.length === 0 ? (
                    <p className="p-6 text-center text-sm text-muted-foreground normal-case">
                      No events found for this transaction.
                    </p>
                  ) : (
                    events.map((event, index) => (
                      <EventRow
                        key={`${event.record_type}-${event.written_at ?? index}-${event.operation?.id ?? index}`}
                        event={event}
                      />
                    ))
                  )}
                </div>
              </>
            ) : (
              <p className="p-8 text-center text-sm text-muted-foreground normal-case">
                Select a transaction to inspect its tool timeline.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {skippedLines > 0 && (
        <p className="text-xs text-warning normal-case">
          {skippedLines} malformed progress event line{skippedLines === 1 ? "" : "s"} skipped while reading the JSONL store.
        </p>
      )}
    </div>
  );
}
