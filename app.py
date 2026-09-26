from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import qrcode
import uvicorn
import webview
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from taiga import TaigaAPI


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
STATE_FILE = BASE_DIR / "display-state.json"
QR_DIR = BASE_DIR / ".qr-cache"

load_dotenv(BASE_DIR / ".env")

HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))


class TaskUpdate(BaseModel):
    selected: bool | None = None
    questText: str | None = None
    order: int | None = None


class DisplayState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.tasks: list[dict[str, Any]] = []
        self.taiga_error: str | None = None
        self.last_success: int | None = None
        self.display_state: dict[str, dict[str, Any]] = {}
        self._load_local_state()

    def _load_local_state(self) -> None:
        if not STATE_FILE.exists():
            self.display_state = {}
            return

        try:
            raw = json.loads(
                STATE_FILE.read_text(encoding="utf-8")
            )
            if isinstance(raw, dict):
                self.display_state = raw
        except Exception:
            traceback.print_exc()
            self.display_state = {}

    def _save_local_state(self) -> None:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                self.display_state,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        tmp.replace(STATE_FILE)

    def set_tasks(
        self,
        tasks: list[dict[str, Any]],
    ) -> None:
        with self._lock:
            self.tasks = tasks
            self.last_success = int(time.time())
            self.taiga_error = None

    def set_error(self, error: str) -> None:
        with self._lock:
            self.taiga_error = error

def update_task(
    self,
    task_id: int,
    selected: bool | None = None,
    quest_text: str | None = None,
    order: int | None = None,
) -> None:
    key = str(task_id)

    with self._lock:
        item = self.display_state.setdefault(
            key,
            {
                "selected": False,
                "questText": "",
                "order": 9999,
            },
        )

        if selected is not None:
            if selected:
                # Nur beim NEUEN Anwählen eine Position vergeben.
                if not item.get("selected", False):
                    selected_orders = [
                        int(value.get("order", 0))
                        for value in self.display_state.values()
                        if value.get("selected")
                        and int(value.get("order", 9999)) < 9999
                    ]

                    item["order"] = (
                        max(selected_orders, default=0)
                        + 1
                    )

                item["selected"] = True

            else:
                item["selected"] = False

                # Wird später erneut gewählt,
                # soll es hinten angehängt werden.
                item["order"] = 9999

        if quest_text is not None:
            item["questText"] = str(
                quest_text
            )

        # Manuelle Reihenfolge lassen wir weiterhin zu,
        # falls wir sie später wieder brauchen.
        if order is not None:
            item["order"] = int(order)

        self._save_local_state()

    def get_task(self, task_id: int) -> dict[str, Any] | None:
        with self._lock:
            for task in self.tasks:
                if int(task.get("id") or -1) == task_id:
                    return self._merge_task(task)
        return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            merged = [
                self._merge_task(task)
                for task in self.tasks
            ]

            selected = sorted(
                [
                    task
                    for task in merged
                    if task["selected"]
                ],
                key=lambda item: (
                    item["order"],
                    item.get("dueDate") is None,
                    str(item.get("dueDate") or "9999-12-31"),
                    int(item.get("ref") or 999999),
                ),
            )

            return {
                "tasks": merged,
                "selectedTasks": selected,
                "taigaError": self.taiga_error,
                "lastSuccess": self.last_success,
                "generatedAt": int(time.time()),
                "server": {
                    "port": HTTP_PORT,
                    "localIp": get_local_ip(),
                },
            }

    def _merge_task(
        self,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        item = dict(task)
        local = self.display_state.get(
            str(task.get("id")),
            {},
        )

        item["selected"] = bool(
            local.get("selected", False)
        )
        item["questText"] = str(
            local.get("questText", "")
        )
        item["order"] = int(
            local.get("order", 9999)
        )

        return item


STATE = DisplayState()
APP = FastAPI(title="BA1 Taiga Display")

APP.mount(
    "/static",
    StaticFiles(directory=PUBLIC_DIR),
    name="static",
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()

        async with self._lock:
            self.active.append(ws)

        await ws.send_json(
            {
                "type": "state",
                "payload": STATE.snapshot(),
            }
        )

    async def disconnect(
        self,
        ws: WebSocket,
    ) -> None:
        async with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast_state(self) -> None:
        message = {
            "type": "state",
            "payload": STATE.snapshot(),
        }

        stale: list[WebSocket] = []

        async with self._lock:
            targets = list(self.active)

        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)

        if stale:
            async with self._lock:
                for ws in stale:
                    if ws in self.active:
                        self.active.remove(ws)


WS = ConnectionManager()
SERVER_LOOP: asyncio.AbstractEventLoop | None = None


@APP.on_event("startup")
async def remember_loop() -> None:
    global SERVER_LOOP
    SERVER_LOOP = asyncio.get_running_loop()


@APP.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(
        """
        <h1>BA1 Taiga Display</h1>
        <p><a href="/display">Display</a></p>
        <p><a href="/control">Tablet-Steuerung</a></p>
        """
    )


@APP.get("/display")
def display() -> FileResponse:
    return FileResponse(
        PUBLIC_DIR / "display.html"
    )


@APP.get("/control")
def control() -> FileResponse:
    return FileResponse(
        PUBLIC_DIR / "control.html"
    )


@APP.get("/api/state")
def api_state() -> dict[str, Any]:
    return STATE.snapshot()


@APP.patch("/api/task/{task_id}")
async def api_update_task(
    task_id: int,
    update: TaskUpdate,
) -> dict[str, Any]:
    if STATE.get_task(task_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Task nicht gefunden",
        )

    STATE.update_task(
        task_id=task_id,
        selected=update.selected,
        quest_text=update.questText,
        order=update.order,
    )

    await WS.broadcast_state()

    return {
        "ok": True,
        "task": STATE.get_task(task_id),
    }


@APP.get("/q/{task_id}")
def quest_page(task_id: int) -> HTMLResponse:
    task = STATE.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task nicht gefunden",
        )

    subject = html_escape(
        task.get("subject", "Aufgabe")
    )
    quest_text = html_escape(
        task.get("questText")
        or "Für diese Aufgabe wurden noch keine weiteren Anweisungen hinterlegt."
    )

    return HTMLResponse(
        f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{subject}</title>
<style>
body {{
  margin:0;
  background:#0b1012;
  color:#f4f7f8;
  font-family:system-ui,sans-serif;
  padding:24px;
}}
main {{
  max-width:760px;
  margin:0 auto;
}}
.kicker {{
  color:#dfff59;
  font-weight:800;
  letter-spacing:.12em;
}}
h1 {{
  font-size:clamp(34px,8vw,72px);
  line-height:1;
}}
.quest {{
  white-space:pre-wrap;
  background:#141d20;
  border:1px solid #2c3a3f;
  padding:20px;
  border-radius:14px;
  font-size:20px;
  line-height:1.5;
}}
</style>
</head>
<body>
<main>
<div class="kicker">BLUMENTHAL 7 · QUEST #{task.get("ref", "–")}</div>
<h1>{subject}</h1>
<div class="quest">{quest_text}</div>
</main>
</body>
</html>"""
    )


@APP.get("/qr/{task_id}.png")
def qr_image(task_id: int) -> FileResponse:
    task = STATE.get_task(task_id)

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task nicht gefunden",
        )

    QR_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    ip = get_local_ip()
    url = f"http://{ip}:{HTTP_PORT}/q/{task_id}"
    path = QR_DIR / f"{task_id}.png"

    image = qrcode.make(url)
    image.save(path)

    return FileResponse(
        path,
        media_type="image/png",
    )


@APP.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
) -> None:
    await WS.connect(ws)

    try:
        while True:
            message = await ws.receive_json()

            if message.get("type") == "ping":
                await ws.send_json(
                    {
                        "type": "pong",
                        "time": int(time.time()),
                    }
                )

    except WebSocketDisconnect:
        await WS.disconnect(ws)


def notify_clients() -> None:
    loop = SERVER_LOOP

    if loop is None:
        return

    try:
        asyncio.run_coroutine_threadsafe(
            WS.broadcast_state(),
            loop,
        )
    except Exception:
        traceback.print_exc()


def taiga_loop() -> None:
    interval = int(
        os.getenv(
            "TAIGA_REFRESH_SECONDS",
            "60",
        )
    )

    while True:
        try:
            tasks = load_open_tasks()
            STATE.set_tasks(tasks)

            print(
                f"Taiga: {len(tasks)} offene Tasks geladen."
            )

            notify_clients()

        except Exception as exc:
            message = (
                f"{type(exc).__name__}: {exc}"
            )

            STATE.set_error(message)
            notify_clients()

            print(
                f"Taiga-Fehler: {message}"
            )
            traceback.print_exc()

        time.sleep(
            max(interval, 15)
        )


def load_open_tasks() -> list[dict[str, Any]]:
    host = require_env(
        "TAIGA_URL"
    ).rstrip("/")

    username = require_env(
        "TAIGA_USERNAME"
    )

    password = require_env(
        "TAIGA_PASSWORD"
    )

    project_slug = require_env(
        "TAIGA_PROJECT_SLUG"
    )

    max_items = int(
        os.getenv(
            "TAIGA_MAX_ITEMS",
            "200",
        )
    )

    api = TaigaAPI(host=host)

    api.auth(
        username=username,
        password=password,
    )

    project = api.projects.get_by_slug(
        project_slug
    )

    statuses = api.task_statuses.list(
        project=project.id
    )

    open_statuses = [
        status
        for status in statuses
        if not bool(
            getattr(
                status,
                "is_closed",
                False,
            )
        )
    ]

    result: list[dict[str, Any]] = []

    for status in open_statuses:
        status_name = str(
            getattr(
                status,
                "name",
                "Offen",
            )
        )

        print(
            "Taiga: Lade offene Tasks "
            f"aus Status '{status_name}' ..."
        )

        raw_tasks = api.tasks.list(
            project=project.id,
            status=status.id,
        )

        for task in raw_tasks:
            result.append(
                task_for_display(
                    task,
                    project,
                    status,
                )
            )

    result.sort(
        key=lambda item: (
            item.get("dueDate") is None,
            str(
                item.get("dueDate")
                or "9999-12-31"
            ),
            int(item.get("ref") or 999999),
        )
    )

    return result[:max_items]


def task_for_display(
    task: Any,
    project: Any,
    status: Any,
) -> dict[str, Any]:
    assignee = getattr(
        task,
        "assigned_to_extra_info",
        None,
    ) or {}

    if hasattr(
        assignee,
        "to_dict",
    ):
        assignee = assignee.to_dict()

    if not isinstance(
        assignee,
        dict,
    ):
        assignee = {}

    assigned_to = (
        assignee.get(
            "full_name_display"
        )
        or assignee.get(
            "full_name"
        )
        or assignee.get(
            "username"
        )
        or "Nicht zugewiesen"
    )

    story = getattr(
        task,
        "user_story_extra_info",
        None,
    ) or {}

    if hasattr(
        story,
        "to_dict",
    ):
        story = story.to_dict()

    if not isinstance(
        story,
        dict,
    ):
        story = {}

    return {
        "id": getattr(
            task,
            "id",
            None,
        ),
        "ref": getattr(
            task,
            "ref",
            None,
        ),
        "subject": str(
            getattr(
                task,
                "subject",
                "Ohne Titel",
            )
            or "Ohne Titel"
        ),
        "assignedTo": str(
            assigned_to
        ),
        "dueDate": json_value(
            getattr(
                task,
                "due_date",
                None,
            )
        ),
        "modifiedDate": json_value(
            getattr(
                task,
                "modified_date",
                None,
            )
        ),
        "status": str(
            getattr(
                status,
                "name",
                "Offen",
            )
        ),
        "statusColor": str(
            getattr(
                status,
                "color",
                "#8ca3a8",
            )
            or "#8ca3a8"
        ),
        "project": str(
            getattr(
                project,
                "name",
                "Unbekanntes Projekt",
            )
        ),
        "userStory": str(
            story.get("subject")
            or ""
        ),
        "isBlocked": bool(
            getattr(
                task,
                "is_blocked",
                False,
            )
        ),
    }


def start_server() -> None:
    config = uvicorn.Config(
        APP,
        host=HTTP_HOST,
        port=HTTP_PORT,
        log_level="info",
    )

    server = uvicorn.Server(config)
    server.run()


def get_local_ip() -> str:
    override = os.getenv(
        "PUBLIC_IP",
        "",
    ).strip()

    if override:
        return override

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    try:
        sock.connect(
            ("8.8.8.8", 80)
        )
        return str(
            sock.getsockname()[0]
        )
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def json_value(
    value: Any,
) -> Any:
    if hasattr(
        value,
        "isoformat",
    ):
        return value.isoformat()

    return value


def require_env(
    name: str,
) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"{name} fehlt in .env"
        )

    return value.strip()


def html_escape(
    value: Any,
) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def main() -> None:
    print(
        f"Server: http://{get_local_ip()}:{HTTP_PORT}"
    )

    threading.Thread(
        target=start_server,
        daemon=True,
        name="http-server",
    ).start()

    threading.Thread(
        target=taiga_loop,
        daemon=True,
        name="taiga-refresh",
    ).start()

    # Uvicorn kurz Zeit zum Start geben.
    time.sleep(1.0)

    webview.create_window(
        "BA1 Display",
        url=f"http://127.0.0.1:{HTTP_PORT}/display",
        fullscreen=(
            os.getenv(
                "FULLSCREEN",
                "1",
            )
            == "1"
        ),
        frameless=(
            os.getenv(
                "FRAMELESS",
                "1",
            )
            == "1"
        ),
        background_color="#0b1012",
    )

    webview.start(
        gui=os.getenv(
            "PYWEBVIEW_GUI",
            "qt",
        ),
        debug=(
            os.getenv(
                "DEBUG",
                "0",
            )
            == "1"
        ),
    )


if __name__ == "__main__":
    main()
