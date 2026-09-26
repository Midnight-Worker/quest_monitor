const listEl = document.getElementById("list");
const searchEl = document.getElementById("search");
const connectionEl = document.getElementById("connection");

let state = {
  tasks: [],
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function render() {
  const term =
    searchEl.value
      .trim()
      .toLowerCase();

  const tasks = (state.tasks || [])
    .filter((task) => {
      if (!term) {
        return true;
      }

      return [
        task.subject,
        task.status,
        task.assignedTo,
        task.userStory,
        task.ref,
      ]
        .join(" ")
        .toLowerCase()
        .includes(term);
    });

  listEl.innerHTML = tasks.map((task) => `
    <article
      class="task ${task.selected ? "selected" : ""}"
      style="--status-color:${esc(task.statusColor)}"
      data-id="${esc(task.id)}"
    >
      <div class="toggle">
        <input
          type="checkbox"
          ${task.selected ? "checked" : ""}
          onchange="toggleTask(${Number(task.id)}, this.checked)"
        >
      </div>

      <div>
        <div class="title">
          #${esc(task.ref)} · ${esc(task.subject)}
        </div>

        <div class="meta">
          <span>${esc(task.status)}</span>
          <span>${esc(task.assignedTo)}</span>
          ${
            task.userStory
              ? `<span>${esc(task.userStory)}</span>`
              : ""
          }
        </div>

        <div class="editor">
          <textarea
            id="quest-${esc(task.id)}"
            placeholder="Anweisungen fürs Handy / Quest …"
          >${esc(task.questText || "")}</textarea>

          <button
            onclick="saveTask(${Number(task.id)})"
          >
            SPEICHERN
          </button>
        </div>
      </div>
    </article>
  `).join("");
}

async function patchTask(id, payload) {
  const response = await fetch(
    `/api/task/${id}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    throw new Error(
      `HTTP ${response.status}`
    );
  }
}

async function toggleTask(id, selected) {
  try {
    await patchTask(
      id,
      { selected }
    );
  } catch (error) {
    alert(
      "Konnte Auswahl nicht speichern: "
      + error
    );
  }
}

async function saveTask(id) {
  const questText =
    document.getElementById(
      `quest-${id}`
    ).value;

  try {
    await patchTask(
      id,
      {
        questText,
      }
    );
  } catch (error) {
    alert(
      "Konnte Aufgabe nicht speichern: "
      + error
    );
  }
}

function connect() {
  const scheme =
    location.protocol === "https:"
      ? "wss"
      : "ws";

  const ws = new WebSocket(
    `${scheme}://${location.host}/ws`
  );

  ws.addEventListener(
    "open",
    () => {
      connectionEl.textContent =
        "Live mit Raspberry Pi verbunden";
    }
  );

  ws.addEventListener(
    "message",
    (event) => {
      const message =
        JSON.parse(event.data);

      if (message.type === "state") {
        state = message.payload;
        render();
      }
    }
  );

  ws.addEventListener(
    "close",
    () => {
      connectionEl.textContent =
        "Verbindung getrennt – neuer Versuch …";

      setTimeout(
        connect,
        1500
      );
    }
  );
}

searchEl.addEventListener(
  "input",
  render
);

connect();
