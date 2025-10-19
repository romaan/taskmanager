import React, { useState } from "react";
import TaskForm from './components/TaskForm';
import TaskList from './components/TaskList';

interface TaskInfo {
  task_id: string;
  [key: string]: any; 
}

export default function App(): JSX.Element {
  const [lastCreated, setLastCreated] = useState<TaskInfo | null>(null);

  return (
    <div className="container py-4">
      <h2 className="mb-2">Async Task Manager</h2>
      <p className="text-secondary">
        Submit tasks and watch them progress. Click a row to long-poll refresh
        just that task.
      </p>

      <TaskForm onCreated={setLastCreated} />

      {/* Re-key list so it refreshes when a task is created */}
      <TaskList key={lastCreated?.task_id || "list"} />
    </div>
  );
}
