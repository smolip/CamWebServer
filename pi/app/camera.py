import subprocess
import threading
import time
import logging
import sys

logger = logging.getLogger(__name__)

ffmpeg_proc = None
current_event_id = None
_lock = threading.Lock()
_stop_requested = False
_manual = False


def _launch(esp_ip, mediamtx_host='localhost', delay=0):
    global ffmpeg_proc, _stop_requested
    if delay:
        time.sleep(delay)
    while True:
        with _lock:
            if _stop_requested:
                logger.info('camera: stop requested, exiting')
                return
        logger.info(f'camera: starting ffmpeg → {esp_ip}')
        proc = subprocess.Popen([
            'ffmpeg', '-hide_banner',
            '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
            '-i', f'http://{esp_ip}:81/stream',
            '-pix_fmt', 'yuv420p',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
            '-profile:v', 'baseline', '-level', '3.1',
            '-g', '30', '-keyint_min', '30',
            '-f', 'rtsp', '-rtsp_transport', 'tcp',
            f'rtsp://{mediamtx_host}:8554/cam',
        ], stdout=sys.stdout, stderr=sys.stderr)
        with _lock:
            ffmpeg_proc = proc
        proc.wait()
        logger.info(f'camera: ffmpeg exited (code {proc.returncode})')
        with _lock:
            if _stop_requested:
                ffmpeg_proc = None
                return
        time.sleep(3)


def start_stream(esp_ip, mediamtx_host='localhost', delay=0, manual=False):
    global _stop_requested, _manual
    with _lock:
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            return False
        _stop_requested = False
        _manual = manual
    threading.Thread(target=_launch, args=(esp_ip, mediamtx_host, delay), daemon=True).start()
    return True


def stop_stream(force=False):
    global ffmpeg_proc, _stop_requested, _manual
    with _lock:
        if not force and _manual:
            logger.info('camera: ignoring stop — manual stream active')
            return
        _stop_requested = True
        _manual = False
        if ffmpeg_proc and ffmpeg_proc.poll() is None:
            ffmpeg_proc.terminate()
        ffmpeg_proc = None


def get_status():
    with _lock:
        running = ffmpeg_proc is not None and ffmpeg_proc.poll() is None
        pid = ffmpeg_proc.pid if running else None
    return {'running': running, 'pid': pid}
