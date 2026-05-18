import subprocess
import threading
import time

ffmpeg_proc = None
current_event_id = None
_lock = threading.Lock()


def _launch(esp_ip, mediamtx_host='localhost', retries=5, delay=7):
    """Spustí ffmpeg v samostatném vlákně s retry logikou.
    Čeká delay sekund — ESP32 potřebuje čas na WiFi reconnect po deep sleep."""
    global ffmpeg_proc
    time.sleep(delay)
    for _ in range(retries):
        with _lock:
            if ffmpeg_proc and ffmpeg_proc.poll() is None:
                return
            proc = subprocess.Popen([
                'ffmpeg', '-re',
                '-i', f'http://{esp_ip}:81/stream',
                '-c:v', 'libx264', '-preset', 'ultrafast',
                '-f', 'rtsp', f'rtsp://{mediamtx_host}:8554/cam',
            ])
            ffmpeg_proc = proc
        proc.wait()
        if proc.returncode == 0:
            return
        time.sleep(3)


def start_stream(esp_ip, mediamtx_host='localhost'):
    """Spustí stream; vrací False pokud už běží."""
    with _lock:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            return False
    threading.Thread(target=_launch, args=(esp_ip, mediamtx_host), daemon=True).start()
    return True


def stop_stream():
    global ffmpeg_proc
    with _lock:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.terminate()
        ffmpeg_proc = None


def get_status():
    with _lock:
        running = ffmpeg_proc is not None and ffmpeg_proc.poll() is None
        pid = ffmpeg_proc.pid if running else None
    return {'running': running, 'pid': pid}
