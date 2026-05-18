import subprocess
import threading
import time

ffmpeg_proc = None
current_event_id = None
_lock = threading.Lock()
_stop_requested = False


def _launch(esp_ip, mediamtx_host='localhost', delay=0):
    global ffmpeg_proc, _stop_requested
    if delay:
        time.sleep(delay)
    while True:
        with _lock:
            if _stop_requested:
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
        with _lock:
            ffmpeg_proc = proc
        proc.wait()
        with _lock:
            if _stop_requested:
                ffmpeg_proc = None
                return
        time.sleep(3)


def start_stream(esp_ip, mediamtx_host='localhost', delay=0):
    global _stop_requested
    with _lock:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            return False
        _stop_requested = False
    threading.Thread(target=_launch, args=(esp_ip, mediamtx_host, delay), daemon=True).start()
    return True


def stop_stream():
    global ffmpeg_proc, _stop_requested
    with _lock:
        _stop_requested = True
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.terminate()
        ffmpeg_proc = None


def get_status():
    with _lock:
        running = ffmpeg_proc is not None and ffmpeg_proc.poll() is None
        pid = ffmpeg_proc.pid if running else None
    return {'running': running, 'pid': pid}
