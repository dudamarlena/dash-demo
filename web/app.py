import json
import os
import uuid

from dash import Dash, html, dcc, Input, Output, State, no_update
from azure.servicebus import ServiceBusClient, ServiceBusMessage

# from common import upsert_job, get_job

SERVICEBUS_CONNECTION_STRING = os.getenv("SERVICEBUS_CONNECTION_STRING")
SERVICEBUS_QUEUE_NAME = os.getenv("SERVICEBUS_QUEUE_NAME", "llm-jobs")


from datetime import datetime, timezone

from azure.data.tables import TableServiceClient

STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
TABLE_NAME = os.getenv("JOBS_TABLE_NAME", "jobs")


def _get_table_client():
    service = TableServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
    table_client = service.get_table_client(TABLE_NAME)

    try:
        table_client.create_table()
    except Exception:
        pass

    return table_client


def upsert_job(job_id: str, status: str, prompt: str = None, result: str = None, error: str = None):
    table = _get_table_client()

    entity = {
        "PartitionKey": "jobs",
        "RowKey": job_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    existing = get_job(job_id)
    if existing:
        entity.update(existing)

    if prompt is not None:
        entity["prompt"] = prompt
    if result is not None:
        entity["result"] = result
    if error is not None:
        entity["error"] = error

    table.upsert_entity(entity=entity)


def get_job(job_id: str):
    table = _get_table_client()

    try:
        entity = table.get_entity(partition_key="jobs", row_key=job_id)
        return dict(entity)
    except Exception:
        return None


app = Dash(__name__)
server = app.server

app.layout = html.Div(
    [
        html.H1("LLM Generator"),
        dcc.Textarea(
            id="prompt-input",
            placeholder="Wpisz prompt...",
            style={"width": "100%", "height": 200},
        ),
        html.Br(),
        html.Button("Generate", id="generate-btn", n_clicks=0),
        html.Hr(),
        dcc.Store(id="job-id-store"),
        dcc.Interval(id="poll-interval", interval=5000, n_intervals=0, disabled=True),
        html.Div(id="status-box"),
        html.Pre(id="result-box", style={"whiteSpace": "pre-wrap"}),
    ],
    style={"maxWidth": "900px", "margin": "40px auto", "fontFamily": "Arial"},
)


def enqueue_job(job_id: str, prompt: str) -> None:
    payload = {"job_id": job_id, "prompt": prompt}

    with ServiceBusClient.from_connection_string(SERVICEBUS_CONNECTION_STRING) as client:
        sender = client.get_queue_sender(queue_name=SERVICEBUS_QUEUE_NAME)
        with sender:
            sender.send_messages(ServiceBusMessage(json.dumps(payload)))


@app.callback(
    Output("job-id-store", "data"),
    Output("poll-interval", "disabled"),
    Output("status-box", "children"),
    Output("result-box", "children"),
    Input("generate-btn", "n_clicks"),
    State("prompt-input", "value"),
    prevent_initial_call=True,
)
def submit_job(n_clicks, prompt):
    if not prompt or not prompt.strip():
        return no_update, True, "Wpisz prompt.", ""

    job_id = str(uuid.uuid4())

    upsert_job(
        job_id=job_id,
        status="QUEUED",
        prompt=prompt,
        result="",
        error="",
    )

    enqueue_job(job_id, prompt)

    return job_id, False, f"Job queued. ID: {job_id}", ""


@app.callback(
    Output("status-box", "children", allow_duplicate=True),
    Output("result-box", "children", allow_duplicate=True),
    Output("poll-interval", "disabled", allow_duplicate=True),
    Input("poll-interval", "n_intervals"),
    State("job-id-store", "data"),
    prevent_initial_call=True,
)
def poll_job(n, job_id):
    if not job_id:
        return no_update, no_update, True

    job = get_job(job_id)
    if not job:
        return "Nie znaleziono joba.", "", True

    status = job.get("status", "UNKNOWN")
    result = job.get("result", "")
    error = job.get("error", "")

    if status in {"QUEUED", "RUNNING"}:
        return f"Status: {status}", "", False

    if status == "SUCCEEDED":
        return "Status: SUCCEEDED", result, True

    if status == "FAILED":
        return f"Status: FAILED", error or "Unknown error", True

    return f"Status: {status}", "", True


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)