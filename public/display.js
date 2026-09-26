const contentEl = document.getElementById("content");
const statusEl = document.getElementById("status");
const clockEl = document.getElementById("clock");

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updateClock() {
  clockEl.textContent =
    new Intl.DateTimeFormat(
      "de-DE",
      {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }
    ).format(new Date());
}

function render(state) {
  if (state.taigaError) {
    statusEl.textContent = "TAIGA FEHLER";
    statusEl.className = "status error";
  } else {
    statusEl.textContent = "LIVE";
    statusEl.className = "status online";
  }

  const tasks = state.selectedTasks || [];

  if (!tasks.length) {
    contentEl.innerHTML = `
      <div class="empty">
        Auf dem Tablet Aufgaben auswählen.
      </div>
    `;
    return;
  }

  contentEl.innerHTML = tasks
    .slice(0, 6)
    .map((task, index) => `
      <article
        class="quest-card"
        style="--status-color:${esc(task.statusColor)}"
      >
        <div class="number">
          ${String(index + 1).padStart(2, "0")}
        </div>

        <div>
          <div class="task-title">
            ${esc(task.subject)}
          </div>

          <div class="meta">
            #${esc(task.ref)}
            · ${esc(task.status)}
            · ${esc(task.assignedTo)}
          </div>
        </div>

        <div class="qr">
          <img
            src="/qr/${encodeURIComponent(task.id)}.png"
            alt="QR-Code"
          >
        </div>
      </article>
    `)
    .join("");
}

function connect() {
  const scheme =
    location.protocol === "https:"
      ? "wss"
      : "ws";

  const ws = new WebSocket(
    `${scheme}://${location.host}/ws`
  );

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);

    if (message.type === "state") {
      render(message.payload);
    }
  });

  ws.addEventListener("close", () => {
    statusEl.textContent = "VERBINDUNG WEG";
    statusEl.className = "status error";
    setTimeout(connect, 1500);
  });
}

updateClock();
setInterval(updateClock, 1000);
connect();
