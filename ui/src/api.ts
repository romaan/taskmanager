// If you use Vite, ensure tsconfig.json includes: "types": ["vite/client"]
const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api/v1/tasks";
type QueryValue = string | number | boolean | null | undefined;

function encodeParams(obj: Record<string, QueryValue> = {}): string {
  const q = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    q.append(k, String(v));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Minimal task shape your backend returns; extend if you have a full model */
export interface TaskInfo {
  task_id: string;
  status: string;
  [key: string]: unknown;
}

/** Payload for creating a task */
export interface TaskPostPayload {
  task_type: string;
  parameters: Record<string, unknown>;
  priority?: number;
}

export interface WaitOpts {
  wait?: boolean;
  timeout?: number; // seconds
}

export interface StreamOpts {
  status?: string;
  limit?: number;
}

/** Error object with HTTP status and parsed body attached */
export class ApiError extends Error {
  status?: number;
  data?: unknown;

  constructor(message: string, status?: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

/**
 * POST /tasks
 * Returns whatever your API returns after creation (often { task_id, status }).
 * You can make it generic if you have a strong response type.
 */
export async function postTask<T = TaskInfo>(payload: TaskPostPayload): Promise<T> {
  const res = await fetch(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const msg =
      (data as any)?.message ??
      (data as any)?.detail ??
      (data as any)?.details ??
      res.statusText;
    throw new ApiError(String(msg), res.status, data);
  }
  return data as T;
}

/**
 * DELETE /tasks/{taskId}
 * Returns updated TaskInfo (e.g., { task_id, status })
 */
export async function cancelTask(
  taskId: string,
  { wait = false, timeout = 10 }: WaitOpts = {}
): Promise<TaskInfo> {
  const qs = encodeParams({ wait: wait ? "true" : undefined, timeout });
  const res = await fetch(`${API_BASE}/${encodeURIComponent(taskId)}${qs}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = (data as any)?.detail ?? res.statusText;
    throw new ApiError(String(msg), res.status, data);
  }
  return res.json() as Promise<TaskInfo>;
}

/**
 * GET /tasks/{taskId}
 * Returns TaskInfo for a single task
 */
export async function getTask(
  taskId: string,
  { wait = false, timeout = 10 }: WaitOpts = {}
): Promise<TaskInfo> {
  const qs = encodeParams({ wait: wait ? "true" : undefined, timeout });
  const res = await fetch(`${API_BASE}/${encodeURIComponent(taskId)}${qs}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    const msg = (data as any)?.detail ?? res.statusText;
    throw new ApiError(String(msg), res.status, data);
  }
  return res.json() as Promise<TaskInfo>;
}

/**
 * GET /tasks?status=&limit=
 * Streams JSONL (or falls back to text with newline-delimited JSON)
 */
export async function* streamTasks({
  status,
  limit = 100,
}: StreamOpts = {}): AsyncGenerator<TaskInfo, void, unknown> {
  const qs = encodeParams({ status, limit });
  const res = await fetch(`${API_BASE}${qs}`);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(text || res.statusText, res.status);
  }

  // Try JSONL streaming
  const reader = (res.body as ReadableStream<Uint8Array> | null)?.getReader?.();
  if (!reader) {
    // Fallback: try parse as newline-delimited JSON
    const text = await res.text();
    const lines = text.split("\n").filter(Boolean);
    for (const line of lines) {
      try {
        yield JSON.parse(line) as TaskInfo;
      } catch {
        /* ignore bad lines */
      }
    }
    return;
  }

  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    // Emit full lines
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        yield JSON.parse(line) as TaskInfo;
      } catch {
        /* ignore bad lines */
      }
    }
  }

  // Flush any trailing data
  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer.trim()) as TaskInfo;
    } catch {
      /* ignore */
    }
  }
}
