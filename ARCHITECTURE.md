# Architektura systému bezpečnostní kamery

## Přehled

```
[ESP32-S3 + OV2640 + PIR]
         │  MJPEG :81  │  POST /motion /idle
         │              ↓
         │        [RPi — Docker]
         │        ┌─────────────────────────────┐
         └──────→ │ ffmpeg → MediaMTX           │
                  │           ├─ RTSP :8554      │
                  │           ├─ HLS  :8888      │
                  │           └─ fmp4 /recordings│
                  │                              │
                  │ Flask :5000                  │
                  │  ├─ web UI (login, dashboard)│
                  │  ├─ /motion /idle webhooks   │
                  │  └─ /api/* /rec/*            │
                  └──────────┬──────────────────┘
                             │ nginx :8080
                             │ WireGuard tunel
                             ↓
                        [VPS — nginx HTTPS]
                        budka.smolikovic.cz :443
                             │
                             ↓
                        [Prohlížeč]
```

---

## Hardware

### ESP32-S3 (Seeed XIAO ESP32S3 Sense)
- Kamera: OV2640 — servíruje MJPEG stream na `http://192.168.0.179:81/stream`
- PIR senzor: GPIO 3 (INPUT_PULLDOWN)
- Limit: MJPEG server zvládne **jednoho klienta** najednou — ffmpeg je ten jediný odběratel

### Raspberry Pi (`immich`, `192.168.0.65`)
- Běží Docker Compose se dvěma kontejnery
- nginx na portu **8080** (cam server), Apache na portu **80** (Immich — nesouvisí)
- WireGuard interface `PiDoma`, IP v tunelu: `10.182.35.3`

### VPS (`64.226.72.201`)
- nginx s Let's Encrypt SSL
- WireGuard server, IP v tunelu: `10.182.35.2`
- Doména: `budka.smolikovic.cz`

---

## Tok videa (stream pipeline)

```
ESP32 MJPEG :81/stream
    ↓
ffmpeg (cam-app container)
  - přijímá MJPEG přes HTTP
  - překóduje: yuvj422p → yuv420p, libx264 baseline 3.1, ultrafast/zerolatency
  - důvod pix_fmt: prohlížeče nepodporují H.264 High 4:2:2 (avc1.7a001e)
  - pushuje RTSP → mediamtx:8554/cam
    ↓
MediaMTX (mediamtx container)
  - přijímá RTSP :8554
  - servíruje HLS :8888/cam/index.m3u8
  - nahrává fmp4 segmenty → /recordings/cam/YYYYMMDD_HHMMSS-*.mp4 (segmenty po 10 min)
    ↓
RPi nginx :8080  →  location /live/ proxy_pass :8888
    ↓ WireGuard tunel
VPS nginx :443   →  location /live/ proxy_pass 10.182.35.3:8888
  - proxy_redirect /cam/ /live/cam/  ← opravuje MediaMTX cookie-check redirect
    ↓
HLS.js v prohlížeči přehrává /live/cam/index.m3u8
```

---

## PIR flow (automatické spuštění)

```
1. PIR HIGH → ESP32 se probudí z deep sleep
2. ESP32 připojí WiFi, spustí MJPEG server
3. ESP32 POST → http://192.168.0.65:8080/motion  (přímá LAN, obchází VPS)
4. Flask /motion:
   - start_stream(delay=7s)  ← 7s prodleva než ESP32 nastartuje MJPEG
   - INSERT INTO events (source='pir')
5. ffmpeg se připojí na ESP32 MJPEG, stream běží
6. PIR monitoruje: 100s bez pohybu → goToSleep()
7. ESP32 POST → http://192.168.0.65:8080/idle, pak deep sleep
8. Flask /idle:
   - stop_stream()
   - UPDATE events SET ended_at, duration_s
```

**Ochrana manual streamu:** pokud uživatel ručně spustil stream (`_manual=True`), webhooky `/motion` a `/idle` jsou ignorovány — stream neinterrumpuje.

---

## Ruční stream

```
Uživatel klikne ▶ Spustit stream
→ POST /api/stream/start
→ camera.start_stream(manual=True)
→ ffmpeg start, polling každé 2s (max 20s čekání)
→ HLS.js začne přehrávat

Uživatel klikne ⏹ Zastavit
→ POST /api/stream/stop
→ camera.stop_stream(force=True)  ← force=True překoná manual flag
```

---

## Webhooky (ESP32 → RPi)

Přijímají se **přímo na LAN**, nikdy neprojdou přes VPS.
Nginx je omezuje:

```nginx
location ~ ^/(motion|idle)$ {
    allow 192.168.0.0/24;
    allow 127.0.0.1;
    deny all;
    proxy_pass http://127.0.0.1:5000;
}
```

---

## Flask aplikace (`pi/app/`)

| Soubor | Obsah |
|--------|-------|
| `__init__.py` | App factory, ProxyFix middleware, registrace blueprintů |
| `auth.py` | StaticUser (Flask-Login), login/logout |
| `camera.py` | ffmpeg subprocess management, thread-safe, infinite retry |
| `events.py` | `/motion` a `/idle` blueprinty |
| `api.py` | `/api/stream/*`, `/api/events`, `/api/recordings` |
| `views.py` | HTML stránky, `/rec/<path>` (serving záznamů) |
| `db.py` | SQLite přes `sqlite3`, `get_db()`, init schématu |

### ProxyFix
```python
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
```
Nutné proto, že reálná IP a protokol přicházejí v `X-Forwarded-*` hlavičkách z VPS nginx.

---

## Databáze (SQLite)

Soubor: `/app/data/cam.db` uvnitř kontejneru, persistován přes Docker volume `./data:/app/data`.

```sql
CREATE TABLE events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at  DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now')),
    ended_at      DATETIME,
    duration_s    INTEGER,
    source        TEXT NOT NULL DEFAULT 'pir',   -- 'pir' | 'manual'
    recording_path TEXT
);

CREATE TABLE recordings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT NOT NULL UNIQUE,
    recorded_at  DATETIME NOT NULL,
    size_bytes   INTEGER,
    event_id     INTEGER REFERENCES events(id) ON DELETE SET NULL
);
```

Při startu aplikace se uzavřou všechny nedokončené události z předchozího běhu.

---

## Záznamy

MediaMTX ukládá segmenty kontinuálně (dokud běží ffmpeg) do:
```
/recordings/cam/YYYYMMDD_HHMMSS-<us>.mp4   (segmenty po 10 minutách)
```

Flask API `/api/recordings` prochází adresář globem, volá `ffprobe` pro délku klipu.
Soubory servíruje Flask na `/rec/<path>` (ne nginx alias) — kontejner zapisuje jako root, nginx by měl 403.

---

## Docker Compose (`pi/docker-compose.yml`)

```
mediamtx:
  image: bluenviron/mediamtx
  ports: 8554 (RTSP), 8888 (HLS)
  volumes: ./recordings:/recordings, ./docker/mediamtx.yml

cam-app:
  build: . (Dockerfile s ffmpeg + Python)
  ports: 5000
  env: MEDIAMTX_HOST=mediamtx, RECS_DIR=/recordings, DATABASE=/app/data/cam.db
  volumes: ./recordings:/recordings:ro, ./config.py:/app/config.py:ro, ./data:/app/data
  depends_on: mediamtx
```

Kontejnery komunikují přes interní Docker síť (`mediamtx` hostname).

---

## nginx — RPi (`pi/nginx/cam.conf`)

Poslouchá na portu **8080** (Apache má 80 pro Immich).

```
/live/          → proxy MediaMTX :8888  (HLS stream)
/(motion|idle)  → proxy Flask :5000  (jen LAN)
/               → proxy Flask :5000  (vše ostatní)
```

Předává `X-Forwarded-For` a `X-Forwarded-Proto` z VPS dál do Flasku.

---

## nginx — VPS (`vps/nginx/cam.conf`)

```
:80   → 301 HTTPS redirect
:443  → SSL (Let's Encrypt, certbot)
  /live/  → http://10.182.35.3:8888/  (přímý HLS z MediaMTX přes WG)
            proxy_redirect /cam/ /live/cam/  ← cookie-check fix
  /       → http://10.182.35.3:8080  (RPi nginx)
            X-Forwarded-For, X-Forwarded-Proto headers
```

---

## WireGuard tunel

| | RPi | VPS |
|--|-----|-----|
| Interface | `PiDoma` | — |
| WG IP | `10.182.35.3` | `10.182.35.2` |
| Veřejná IP | `192.168.0.65` (LAN) | `64.226.72.201` |

RPi má `AllowedIPs = 0.0.0.0/0` → veškerý provoz z RPi teče přes VPS (full tunnel).
Persistent keepalive 25s udržuje tunel živý za NAT.

---

## Autentizace

- Jeden admin uživatel (StaticUser pattern z Flask-Login)
- Heslo jako scrypt hash v `config.py` (soubor není v gitu, mountován jako Docker volume)
- `remember=True` → 30denní cookie
- `SESSION_COOKIE_SECURE = True` (HTTPS přes VPS)
- `SESSION_COOKIE_SAMESITE = Lax`

---

## Struktura repozitáře

```
src/                    ESP32 firmware (C++/Arduino)
  main.cpp              WiFi, PIR logika, deep sleep, HTTP webhooky
  app_httpd.cpp         MJPEG HTTP server

pi/
  app/                  Flask aplikace
  templates/            Jinja2 HTML šablony (dark theme)
  static/               app.js (HLS.js logika), style.css
  docker/               mediamtx.yml konfigurace
  nginx/cam.conf        RPi nginx config
  schema.sql            SQLite schéma
  docker-compose.yml
  Dockerfile
  config.py.example     Šablona — skutečný config.py není v gitu

vps/
  nginx/cam.conf        VPS nginx config (HTTPS proxy)
```
