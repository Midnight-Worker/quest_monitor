# Taiga-Raumdisplay

Das Projekt besteht aus zwei getrennten Anwendungen:

```text
taiga-room-display/
├── display-app/       Python + pywebview auf dem Raspberry Pi
└── status-server/     Node.js + WebSockets + mobile Webseite
```

## Ablauf

1. Die Python-Anwendung liest alle Taiga-Projekte, in denen der konfigurierte
   Benutzer Mitglied ist.
2. Es werden nur User Stories mit dem Status `In Progress` oder `In Arbeit`
   und dem Tag `display` angezeigt.
3. Nach jeweils drei Taiga-Karten erscheint kurz der Raumstatus.
4. Der Node-Server stellt eine Handy-Webseite bereit.
5. Ein Klick auf `OFFEN`, `BE QUIET` oder `ON AIR` wird per WebSocket
   sofort an das Display übertragen.

---

## 1. Dateien kopieren

Beispiel:

```bash
cd /home/maik
unzip taiga-room-display.zip
cd taiga-room-display
```

## 2. Node-Server installieren

```bash
cd /home/maik/taiga-room-display/status-server
npm install
```

Test:

```bash
node server.js
```

Dann auf dem Handy im selben WLAN öffnen:

```text
http://IP-DES-RASPBERRY-PI:3000
```

IP-Adresse anzeigen:

```bash
hostname -I
```

## 3. Mit PM2 starten

```bash
sudo npm install -g pm2
cd /home/maik/taiga-room-display/status-server

pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

Den von `pm2 startup` ausgegebenen `sudo ...`-Befehl ebenfalls ausführen.

Status prüfen:

```bash
pm2 status
pm2 logs room-status
```

## 4. Python-Anwendung installieren

```bash
cd /home/maik/taiga-room-display/display-app

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Mindestens diese Werte anpassen:

```env
TAIGA_USERNAME=...
TAIGA_PASSWORD=...
```

Test zunächst ohne Vollbild:

```bash
FULLSCREEN=0 FRAMELESS=0 venv/bin/python app.py
```

Danach normal:

```bash
venv/bin/python app.py
```

## 5. Autostart der pywebview

Service-Datei prüfen. Besonders wichtig sind:

```ini
User=maik
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/maik/.Xauthority
```

Installieren:

```bash
sudo cp taiga-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now taiga-display.service
```

Logs:

```bash
journalctl -u taiga-display.service -f
```

## 6. Ports und WLAN

Der Node-Server lauscht auf:

```text
0.0.0.0:3000
```

Dadurch kann das Handy im lokalen WLAN darauf zugreifen. Bei aktivierter Firewall:

```bash
sudo ufw allow 3000/tcp
```

## 7. Wichtige Einstellungen

In `display-app/.env`:

```env
TAIGA_STATUS_NAMES=In Progress,In Arbeit
TAIGA_DISPLAY_TAG=display
TAIGA_REFRESH_SECONDS=300
TAIGA_MAX_ITEMS=50
STATUS_WS_URL=ws://127.0.0.1:3000/ws
```

Taiga wird direkt beim Start und anschließend alle fünf Minuten erneut
abgefragt. Das Intervall lässt sich über `TAIGA_REFRESH_SECONDS` ändern.

Die Anzeigedauer wird in `display-app/public/main.js` eingestellt:

```js
const STORY_SECONDS = 8;
const ROOM_SECONDS = 5;
const ROOM_AFTER_STORIES = 3;
```

## Sicherheit

Die Handy-Steuerung besitzt in diesem Starter noch kein Passwort. Sie sollte
zunächst nur im vertrauenswürdigen internen WLAN erreichbar sein. Vor einer
Freigabe ins Internet müssen mindestens Authentifizierung, HTTPS/WSS und ein
Reverse Proxy ergänzt werden.
# quest_monitor
# quest_monitor
# quest_monitor
