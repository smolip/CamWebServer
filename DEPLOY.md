# Nasazení CamWebServer

## Architektura

```
ESP32 (kamera + PIR)
  │  MJPEG stream :81
  │  POST /motion, /idle
  ▼
Raspberry Pi (lokální síť)
  ├── MediaMTX     – re-streamuje HLS, nahrává záznamy
  ├── Flask app    – přijímá PIR notifikace, spouští ffmpeg
  └── nginx        – servuje web UI + proxy
  │
  │  WireGuard tunel
  ▼
VPS
  └── nginx        – vystavuje vše na internet
```

---

## Co kde vyplnit

Před nasazením si poznamenej tyto hodnoty:

| Proměnná | Popis | Příklad |
|---|---|---|
| `WIFI_SSID` | Název WiFi sítě | `ASUS2` |
| `WIFI_PASS` | Heslo WiFi | `heslo123` |
| `ESP32_LOCAL_IP` | IP adresa ESP32 v lokální síti | `192.168.1.50` |
| `RPI_LOCAL_IP` | IP adresa RPi v lokální síti | `192.168.1.10` |
| `RPI_WG_IP` | WireGuard IP adresa RPi | `10.0.0.2` |

> Lokální IP ESP32 zjistíš po prvním flashnutí ze Serial monitoru v PlatformIO.

---

## 1. ESP32

### 1.1 Konfigurace

V `src/main.cpp` vyplň:

```cpp
const char *ssid     = "WIFI_SSID";
const char *password = "WIFI_PASS";

#define PIR_NOTIFY_URL  "http://RPI_LOCAL_IP/motion"
#define PIR_IDLE_URL    "http://RPI_LOCAL_IP/idle"
#define IDLE_TIMEOUT_MS 30000   // sekundy klidu před deep sleep
```

### 1.2 Flash

```bash
# v adresáři projektu
pio run --target upload
pio device monitor   # sleduj IP adresu v logu
```

Po startu uvidíš v Serial monitoru:
```
WiFi connected
Stream: http://192.168.1.50:81/stream
```

---

## 2. Raspberry Pi

### 2.1 Závislosti

```bash
sudo apt update
sudo apt install -y nginx ffmpeg python3-pip
pip3 install flask
```

### 2.2 MediaMTX

```bash
# Zkontroluj aktuální verzi na: https://github.com/bluenviron/mediamtx/releases
# Nahraď VER a ARCH (arm64v8 pro RPi 4/5, armv7 pro RPi 3)
VER=v1.9.3
ARCH=linux_arm64v8
wget https://github.com/bluenviron/mediamtx/releases/download/${VER}/mediamtx_${VER}_${ARCH}.tar.gz
tar -xf mediamtx_*.tar.gz
sudo mv mediamtx /usr/local/bin/
rm mediamtx_*.tar.gz
```

Vytvoř konfiguraci `/etc/mediamtx.yml`:

```yaml
api: yes
apiAddress: 127.0.0.1:9997

rtspAddress: :8554
hlsAddress: :8888

pathDefaults:
  record: yes
  recordFormat: fmp4
  recordPath: /home/pi/recordings/%path/%Y%m%d_%H%M%S-%f
  recordSegmentDuration: 10m

paths:
  cam: {}
```

### 2.3 Adresářová struktura

```bash
mkdir -p /home/pi/cam/web
mkdir -p /home/pi/recordings
```

### 2.4 Flask webhook

Vytvoř soubor `/home/pi/cam/pir_webhook.py`:

```python
from flask import Flask, jsonify
import subprocess, threading, time, glob, os

app      = Flask(__name__)
ESP_IP   = "ESP32_LOCAL_IP"
RECS_DIR = "/home/pi/recordings"

ffmpeg_proc = None

def _launch(retries=5, delay=7):
    global ffmpeg_proc
    time.sleep(delay)   # ESP32 potřebuje ~7 s na WiFi reconnect po deep sleep
    for _ in range(retries):
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            return
        ffmpeg_proc = subprocess.Popen([
            "ffmpeg", "-re",
            "-i", f"http://{ESP_IP}:81/stream",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-f", "rtsp", "rtsp://localhost:8554/cam"
        ])
        ffmpeg_proc.wait()
        if ffmpeg_proc.returncode == 0:
            return
        time.sleep(3)

def start_stream():
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        return
    threading.Thread(target=_launch, daemon=True).start()

def stop_stream():
    global ffmpeg_proc
    if ffmpeg_proc and ffmpeg_proc.poll() is None:
        ffmpeg_proc.terminate()
    ffmpeg_proc = None

@app.route("/motion", methods=["POST"])
def motion():
    start_stream()
    return jsonify({"ok": True})

@app.route("/idle", methods=["POST"])
def idle():
    stop_stream()
    return jsonify({"ok": True})

@app.route("/recordings")
def recordings():
    files = sorted(
        glob.glob(f"{RECS_DIR}/**/*.mp4", recursive=True),
        reverse=True
    )
    return jsonify([os.path.relpath(f, RECS_DIR) for f in files])

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
```

### 2.5 Web UI

Zkopíruj soubor `web/index.html` z tohoto repozitáře do `/home/pi/cam/web/index.html`:

```bash
scp web/index.html pi@RPI_LOCAL_IP:/home/pi/cam/web/index.html
```

### 2.6 nginx

Vytvoř `/etc/nginx/sites-available/cam`:

```nginx
server {
    listen 80;

    root /home/pi/cam/web;
    index index.html;

    location /live/ {
        proxy_pass         http://127.0.0.1:8888/;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3600s;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5000/;
    }

    location /recordings/ {
        alias /home/pi/recordings/;
        add_header Content-Disposition 'inline';
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/cam /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7 Systemd služby

**MediaMTX** — `/etc/systemd/system/mediamtx.service`:

```ini
[Unit]
Description=MediaMTX
After=network.target

[Service]
ExecStart=/usr/local/bin/mediamtx /etc/mediamtx.yml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**Flask webhook** — `/etc/systemd/system/cam-webhook.service`:

```ini
[Unit]
Description=Camera PIR webhook
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/cam/pir_webhook.py
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target
```

Zapni obě služby:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mediamtx
sudo systemctl enable --now cam-webhook
```

---

## 3. VPS

### 3.1 nginx

Vytvoř `/etc/nginx/sites-available/cam`:

> `RPI_WG_IP` je WireGuard IP adresa RPi — ověř ji příkazem `ip addr show wg0` na RPi (typicky `10.0.0.x`).

```nginx
server {
    listen 80;
    server_name tvoje-domena.com;   # nebo jen IP VPS

    location /live/ {
        proxy_pass         http://RPI_WG_IP:8888/;
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3600s;
    }

    location / {
        proxy_pass http://RPI_WG_IP:80;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/cam /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 4. Ověření

Otestuj každou vrstvu postupně:

```bash
# 1. ESP32 stream (z lokální sítě)
curl -I http://ESP32_LOCAL_IP:81/stream

# 2. RPi webhook
curl -X POST http://RPI_LOCAL_IP/motion
curl -X POST http://RPI_LOCAL_IP/idle

# 3. MediaMTX HLS (chvíli po /motion)
curl -I http://RPI_LOCAL_IP:8888/cam/index.m3u8

# 4. Záznamy API
curl http://RPI_LOCAL_IP/api/recordings

# 5. Celý stack přes VPS
curl -I http://VPS_IP/live/cam/index.m3u8
```

Stav služeb na RPi:

```bash
sudo systemctl status mediamtx
sudo systemctl status cam-webhook
sudo journalctl -u mediamtx -f        # živý log MediaMTX
sudo journalctl -u cam-webhook -f     # živý log webhook
```

---

## Endpointy

| URL | Popis |
|---|---|
| `http://VPS/` | Web rozhraní (stream + záznamy) |
| `http://VPS/live/cam/index.m3u8` | HLS stream |
| `http://VPS/recordings/cam/...` | Soubory nahrávek |
| `http://RPI_LOCAL_IP/motion` | PIR notifikace (jen z lokální sítě) |
| `http://ESP32_LOCAL_IP/brightness?val=0` | Jas kamery (-2 až 2) |
| `http://ESP32_LOCAL_IP/contrast?val=0` | Kontrast (-2 až 2) |
| `http://ESP32_LOCAL_IP/saturation?val=0` | Saturace (-2 až 2) |
| `http://ESP32_LOCAL_IP/quality?val=10` | JPEG kvalita (10–63, nižší = lepší) |
| `http://ESP32_LOCAL_IP/resolution?val=5` | Rozlišení (framesize enum) |

> Nastavení kamery jsou dostupná jen lokálně (ESP32 je ve WiFi síti, ne na internetu).

---

## Řešení problémů

**ESP32 se neprobouzí po deep sleep**
- Zkontroluj zapojení PIR na GPIO9 (D10 na XIAO ESP32S3)
- PIR musí mít výstup HIGH při detekci (většina HC-SR501 má)

**Záznamy nejdou přehrát v prohlížeči**
- Ověř že ffmpeg používá `-c:v libx264` (ne `-c:v copy`)
- Na RPi 3 může být libx264 pomalý — zkus `-c:v h264_v4l2m2m` pro HW akceleraci

**MediaMTX nenahrává**
- Zkontroluj že `/home/pi/recordings` existuje a má správná práva:
  ```bash
  sudo chown pi:pi /home/pi/recordings
  ```
