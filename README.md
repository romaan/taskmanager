Task Manager

# Requirements

- Libraries: Use FastAPI for the API, asyncio for queues and async operations, and standard libraries like uuid and collections. No external dependencies beyond these.
- In-Memory Storage: Use a dictionary to store task details and an asyncio.Queue for pending tasks. Data is volatile and resets on restart.

## API Endpoints:

* POST /tasks: Submit a task.
  Response: 202 Accepted with task_id(UUID)and status "queued". Validate inputs; return 400 on errors.

* GET /tasks/{task_id}: Poll task status.
▪ Returns:JSON with status ("queued","processing","completed", "failed"), result (if completed), error (if failed).
▪ Optional:?wait=true for long-polling (wait upto 10 seconds for status change).

* GET /tasks: List tasks.
▪ Optional filters:?status=queued&limit=10.
▪ Stream response if manytasks(use async generator).

* DELETE /tasks/{task_id}: Cancel a task (set to "cancelled" if possible).


## Core Functionality:
- Task Queuing and Processing: Use asyncio.Queue for task submission. Run a background worker loop (via asyncio.create_task) that dequeues tasks, processes them asynchronously (simulate work with asyncio.sleep for 5-30 seconds based on type, using match for logic: e.g., sum numbers, generate fake report string, or raise errors for simulation). Update status in an in- memory dict (key: task_id, value: dict with status, parameters, result).
- Polling Mechanism: For /tasks/{task_id}, if ?wait=true, use asyncio.Event per task to notify on status changes, awaiting with timeout. This demonstrates efficient long-polling without busy-waiting.
- Rate Limiting: Limit to 10 requests/minute per IP. Track in an in-memory dict with collections.deque for timestamps. Use asyncio.Lock for thread- safety. Return 429 on exceedance.
- In-Memory Management: Dict for task storage, queue for pending tasks. Implement auto-cleanup: remove completed/failed tasks after 10 minutes using a separate async timer task.
- Concurrency: Process up to 5 tasks in parallel using asyncio.gather. Handle cancellations gracefully (e.g., via asyncio.CancelledError).

## Additional Features:
- Use Python 3.10+ specifics: match for task_type processing (e.g., matchtask_type: case "compute_sum": ...), parenthesized context managers for locks, or type aliases for task dicts.
- Error Handling: Custom async exceptions (e.g., TaskFailedError), logging, and detailed JSON responses. Use match for error classification.
- Testing: Async tests covering submission, polling (with mocks for sleeps), rate limiting, cancellations, and concurrency (e.g., simulate multiple submissions).
- Documentation: README.md with setup instructions, API docs (using FastAPI's Swagger).



# Tasks:

Plan is to implement backend stack in python3.12+, use FastAPI, asyncio and pytest PLUS also develop a tiny frontend using React framework PLUS also dockerize the applications. So the plan is as follows:

- Setup the repository, git initialize
- Add requirements, helper scripts and define project structure
- API definition and unit test skeleton added
- Implement Task Manager

# Prerequisites 
- Developed/Tested on linux / macos with bash terminal if you want to run the project locally
- Python3.12
- Node 22+
- Docker installed if building and running with containers

# Assumption
- CORSMIddleware and allow_origins="*" are set to allow frontend running on different origin to talk to backend, but in PRODUCTION this should be secured further

# How to run locally

## Backend

Initialize the python virtual environment

```sh
./run.sh init --dev
```

Run the backend

```sh
./run.sh dev
```

App will launch default on [http://localhost:8000](http://localhost:8000) and swagger docs will be available at [http://localhost:8000/docs](http://localhost:8000)

Run the backend tests

```sh
./run.sh test
```

## Frontend

TODO

## Docker 

TODO