import subprocess
import threading
import time

ffmpeg_proc = None
current_event_id = None
_lock = threading.Lock()


def _launch(esp_ip, mediamtx_host='localhost', retries=5, delay=0):
    global ffmpeg_proc
    if delay:
        time.sleep(delay)
    for _ in range(retries):
        with _lock:
            if ffmpeg_proc and ffmpeg_proc.poll() is None:
                return
            proc = subprocess.Popen([
                'ffmpeg',
                '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
                '-i', f'http://{esp_ip}:81/stream',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
                '-g', '15', '-keyint_min', '15',
                '-f', 'rtsp', '-rtsp_transport', 'tcp',
                f'rtsp://{mediamtx_host}:8554/cam',
            ])
            ffmpeg_proc = proc
        proc.wait()
        if proc.returncode == 0:
            return
        time.sleep(3)


def start_stream(esp_ip, mediamtx_host='localhost', delay=0):
    with _lock:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            return False
    threading.Thread(target=_launch, args=(esp_ip, mediamtx_host, 5, delay), daemon=True).start()
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
