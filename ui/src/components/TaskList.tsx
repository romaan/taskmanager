import React, { useEffect, useState, useRef, ChangeEvent, MouseEvent } from "react";
import { streamTasks, getTask, cancelTask, TaskInfo } from "../api";

interface ProgressInfo {
  message?: string;
  eta_seconds?: number | null;
  started_at?: string | null;
}

// Extend TaskInfo with optional fields your UI reads
type TaskWithProgress = TaskInfo & {
  task_type?: string;
  status: string;
  progress?: number;
  progress_info?: ProgressInfo;
};

export default function TaskList(): JSX.Element {
  const [tasks, setTasks] = useState<TaskWithProgress[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [limit, setLimit] = useState<number>(100);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const streamingRef = useRef<boolean>(false);

  async function load(): Promise<void> {
    setError("");
    setLoading(true);
    streamingRef.current = true;
    const items: TaskWithProgress[] = [];
    try {
      for await (const obj of streamTasks({
        status: statusFilter || undefined,
        limit,
      })) {
        if (obj) items.push(obj as TaskWithProgress);
      }
      setTasks(items);
    } catch (err: unknown) {
      const e = err as { message?: string };
      setError(String(e?.message ?? err));
    } finally {
      streamingRef.current = false;
      setLoading(false);
    }
  }

  async function refreshOne(taskId: string): Promise<void> {
    try {
      const updated = (await getTask(taskId, {
        wait: true,
        timeout: 10,
      })) as TaskWithProgress;
      setTasks((prev) =>
        prev.map((t) => (t.task_id === updated.task_id ? updated : t))
      );
    } catch (err: unknown) {
      const e = err as { message?: string };
      setError(String(e?.message ?? err));
    }
  }

  async function doCancel(taskId: string): Promise<void> {
    try {
      const updated = (await cancelTask(taskId, {
        wait: true,
        timeout: 10,
      })) as TaskWithProgress;
      setTasks((prev) =>
        prev.map((t) => (t.task_id === updated.task_id ? updated : t))
      );
    } catch (err: unknown) {
      const e = err as { message?: string };
      setError(String(e?.message ?? err));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="card shadow-sm">
      <div className="card-body">
        <div className="d-flex align-items-end gap-3 mb-3">
          <div>
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                setStatusFilter(e.target.value)
              }
            >
              <option value="">(all)</option>
              <option value="queued">queued</option>
              <option value="processing">processing</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="cancelled">cancelled</option>
            </select>
          </div>
          <div style={{ width: 120 }}>
            <label className="form-label">Limit</label>
            <input
              className="form-control"
              type="number"
              min={1}
              max={1000}
              value={limit}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setLimit(Number(e.target.value) || 1)
              }
            />
          </div>
          <div className="ms-auto">
            <button className="btn btn-outline-light" onClick={() => void load()} disabled={loading}>
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>

        {error && <div className="alert alert-danger py-2">{error}</div>}

        <div className="table-responsive">
          <table className="table table-hover align-middle">
            <thead>
              <tr>
                <th>Task ID</th>
                <th>Type</th>
                <th>Status</th>
                <th style={{ width: 300 }}>Progress</th>
                <th>ETA</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center text-muted py-4">
                    No tasks
                  </td>
                </tr>
              )}
              {tasks.map((t) => (
                <TaskRow
                  key={t.task_id}
                  task={t}
                  onCancel={doCancel}
                  onRefresh={refreshOne}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

interface TaskRowProps {
  task: TaskWithProgress;
  onCancel: (taskId: string) => Promise<void> | void;
  onRefresh: (taskId: string) => Promise<void> | void;
}

function TaskRow({ task, onCancel, onRefresh }: TaskRowProps): JSX.Element {
  const [busy, setBusy] = useState<boolean>(false);
  const eta = task?.progress_info?.eta_seconds ?? null;
  const msg = task?.progress_info?.message ?? "";

  function formatEta(s: number | null): string {
    if (s == null) return "-";
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}m ${r}s`;
    }

  async function handleCancel(e: MouseEvent<HTMLButtonElement>): Promise<void> {
    e.stopPropagation();
    setBusy(true);
    try {
      await onCancel(task.task_id);
    } finally {
      setBusy(false);
    }
  }

  async function refreshOne(): Promise<void> {
    setBusy(true);
    try {
      await onRefresh(task.task_id);
    } finally {
      setBusy(false);
    }
  }

  const badgeClass =
    {
      queued: "secondary",
      processing: "info",
      completed: "success",
      failed: "danger",
      cancelled: "warning",
    }[(task.status || "").toLowerCase()] || "secondary";

  return (
    <tr
      onClick={() => void refreshOne()}
      style={{ cursor: "pointer" }}
      title="Click to long-poll refresh"
    >
      <td className="small-mono">{task.task_id}</td>
      <td>{task.task_type ?? "-"}</td>
      <td>
        <span className={`badge text-bg-${badgeClass}`}>{task.status}</span>
      </td>
      <td style={{ width: 300 }}>
        <div className="small">{msg}</div>
        {typeof task.progress === "number" && (
          <div className="progress mt-1">
            <div
              className="progress-bar"
              role="progressbar"
              style={{ width: `${task.progress}%` }}
              aria-valuenow={task.progress}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        )}
      </td>
      <td>{formatEta(eta)}</td>
      <td>
        <button
          className="btn btn-sm btn-outline-danger"
          onClick={handleCancel}
          disabled={
            busy ||
            !["queued", "processing"].includes((task.status || "").toLowerCase())
          }
        >
          Cancel
        </button>
      </td>
    </tr>
  );
}
