import React, { useState, FormEvent, ChangeEvent } from "react";
import { postTask, TaskInfo, TaskPostPayload } from "../api";

interface TaskFormProps {
  onCreated?: (task: TaskInfo) => void;
}

export default function TaskForm({ onCreated }: TaskFormProps): JSX.Element {
  const [taskType, setTaskType] = useState<string>("compute_sum");
  const [priority, setPriority] = useState<number>(0);
  const [numbers, setNumbers] = useState<string>("1,2,3");
  const [title, setTitle] = useState<string>("Monthly Report");
  const [sections, setSections] = useState<string>("overview,details,summary");
  const [emails, setEmails] = useState<string>("abc@abc.com,xyz@xyz.com");
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  function buildParameters(): Record<string, unknown> {
    switch (taskType) {
      case "compute_sum":
        return {
          numbers: numbers
            .split(",")
            .map((s) => Number(s.trim()))
            .filter((v) => !Number.isNaN(v)),
        };
      case "generate_report":
        return {
          title,
          sections: sections
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        };
      case "batch_email":
        return {
          emails: emails
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        };
      case "lucky_job":
        return {};
      default:
        return {};
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload: TaskPostPayload = {
        task_type: taskType,
        parameters: buildParameters(),
        priority: Number(priority) || 0,
      };
      const info = await postTask(payload);
      onCreated?.(info);
    } catch (err: any) {
      setError(JSON.stringify(err?.data ?? err, null, 2));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card shadow-sm mb-4">
      <div className="card-body">
        <h5 className="card-title mb-3">Create Task</h5>
        {error && (
          <div className="alert alert-danger py-2">
            <strong>Request failed</strong>
            <pre
              className="mt-2 mb-0"
              style={{ whiteSpace: "pre-wrap", overflowX: "auto" }}
            >
              {error}
            </pre>
          </div>
        )}
        <form onSubmit={submit} className="row g-3">
          <div className="col-md-4">
            <label className="form-label">Task Type</label>
            <select
              className="form-select"
              value={taskType}
              onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                setTaskType(e.target.value)
              }
            >
              <option value="compute_sum">Compute Sum</option>
              <option value="generate_report">Generate Report</option>
              <option value="batch_email">Batch Email</option>
              <option value="lucky_job">Lucky Job</option>
            </select>
          </div>

          <div className="col-md-2">
            <label className="form-label">Priority (0–10)</label>
            <input
              type="number"
              className="form-control"
              value={priority}
              min={0}
              max={10}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setPriority(Number(e.target.value))
              }
            />
          </div>

          {taskType === "compute_sum" && (
            <div className="col-12">
              <label className="form-label">Numbers (comma separated)</label>
              <input
                className="form-control"
                value={numbers}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setNumbers(e.target.value)
                }
                placeholder="e.g. 1,2,3"
              />
            </div>
          )}

          {taskType === "generate_report" && (
            <>
              <div className="col-md-6">
                <label className="form-label">Title</label>
                <input
                  className="form-control"
                  value={title}
                  onChange={(e: ChangeEvent<HTMLInputElement>) =>
                    setTitle(e.target.value)
                  }
                />
              </div>
              <div className="col-md-6">
                <label className="form-label">Sections (comma separated)</label>
                <input
                  className="form-control"
                  value={sections}
                  onChange={(e: ChangeEvent<HTMLInputElement>) =>
                    setSections(e.target.value)
                  }
                />
              </div>
            </>
          )}

          {taskType === "batch_email" && (
            <div className="col-12">
              <label className="form-label">Emails (comma separated)</label>
              <input
                className="form-control"
                value={emails}
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setEmails(e.target.value)
                }
                placeholder="abc@abc.com, xyz@xyz.com"
              />
              <div className="form-text">
                Comma separated list of email addresses
              </div>
            </div>
          )}

          <div className="col-12">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy ? "Submitting…" : "Submit Task"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
