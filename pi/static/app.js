const HLS_URL  = '/live/cam/index.m3u8';
const RECS_API = '/api/recordings';
const STATUS_API = '/api/stream/status';

// ── Helpers ──────────────────────────────────────────────────
function formatFilename(path) {
  const m = path.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/);
  if (!m) return path;
  return `${m[3]}.${m[2]}.${m[1]}  ${m[4]}:${m[5]}:${m[6]}`;
}

function formatDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso.replace('T', ' ') + 'Z');
  return d.toLocaleString('cs-CZ', { timeZone: 'Europe/Prague',
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function fmtDuration(s) {
  if (!s) return '—';
  if (s < 60) return `${s} s`;
  return `${Math.floor(s / 60)} min ${s % 60} s`;
}

// ── Dashboard ─────────────────────────────────────────────────
if (document.getElementById('streamBtn')) {
  const video  = document.getElementById('video');
  const btn    = document.getElementById('streamBtn');
  const dot    = document.getElementById('dot');
  const stText = document.getElementById('statusText');
  let hls = null;

  async function updateStatus() {
    try {
      const r = await fetch(STATUS_API, { cache: 'no-store' });
      const data = await r.json();
      const online = data.running;
      dot.className      = 'dot' + (online ? ' live' : '');
      stText.textContent = online ? 'Online' : 'Offline';
      return online;
    } catch { return false; }
  }

  function startHls() {
    video.classList.add('visible');
    btn.textContent = '⏹ Zastavit';
    btn.classList.add('active');

    if (typeof Hls !== 'undefined' && Hls.isSupported()) {
      let recoveries = 0;
      hls = new Hls({ lowLatencyMode: true, manifestLoadingMaxRetry: 8, manifestLoadingRetryDelay: 2000 });
      hls.loadSource(HLS_URL);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play());
      hls.on(Hls.Events.ERROR, (_, d) => {
        if (!d.fatal) return;
        if (recoveries++ >= 4) { stopHls(); return; }
        if (d.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();
        } else if (d.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
        } else {
          stopHls();
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = HLS_URL;
      video.play();
    }
  }

  function stopHls() {
    if (hls) { hls.destroy(); hls = null; }
    video.src = '';
    video.classList.remove('visible');
    btn.textContent = '▶ Spustit stream';
    btn.classList.remove('active');
  }

  btn.addEventListener('click', async () => {
    if (hls || video.src) {
      await fetch('/api/stream/stop', { method: 'POST' });
      stopHls();
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Spouštím…';
    try {
      await fetch('/api/stream/start', { method: 'POST' });
      // Čekáme až ffmpeg nastartuje (max 20 s, kontrola každé 2 s)
      let running = false;
      for (let i = 0; i < 10; i++) {
        await new Promise(r => setTimeout(r, 2000));
        running = await updateStatus();
        if (running) break;
      }
      if (running) {
        startHls();
      } else {
        btn.textContent = '▶ Spustit stream';
      }
    } finally {
      btn.disabled = false;
    }
  });

  updateStatus();
  setInterval(updateStatus, 10000);

  // ── Poslední události (mini-list) ────────────────────────────
  async function loadRecentEvents() {
    const list = document.getElementById('eventMiniList');
    if (!list) return;
    try {
      const data = await fetch('/api/events?page=1').then(r => r.json());
      const ev = data.events.slice(0, 5);
      if (!ev.length) {
        list.innerHTML = '<div class="empty">Žádné události</div>';
        return;
      }
      list.innerHTML = ev.map(e => `
        <div class="event-mini-item">
          <span class="event-time">${formatDatetime(e.triggered_at)}</span>
          <span class="badge badge-${e.source}">${e.source === 'pir' ? 'PIR' : 'Ručně'}</span>
        </div>
      `).join('');
    } catch {
      list.innerHTML = '<div class="empty">Chyba při načítání</div>';
    }
  }

  loadRecentEvents();
  setInterval(loadRecentEvents, 30000);
}

// ── Recordings page ───────────────────────────────────────────
if (document.getElementById('recList')) {
  async function loadRecordings() {
    const list = document.getElementById('recList');
    try {
      const files = await fetch(RECS_API).then(r => r.json());
      if (!files.length) {
        list.innerHTML = '<div class="empty">Žádné záznamy</div>';
        return;
      }
      list.innerHTML = files.map((f, i) => `
        <div class="rec-item-inner">
          <div class="rec-item" style="flex-wrap:wrap">
            <span class="rec-time">${formatFilename(f)}</span>
            <div class="rec-actions">
              <a onclick="toggleVideo(${i})" id="playBtn${i}">▶ Přehrát</a>
              <a href="/recordings/${f}" download>↓ Stáhnout</a>
            </div>
          </div>
          <div class="rec-video-wrap" id="videoWrap${i}">
            <video controls preload="none">
              <source src="/recordings/${f}" type="video/mp4">
            </video>
          </div>
        </div>
      `).join('');
    } catch {
      list.innerHTML = '<div class="empty">Chyba při načítání</div>';
    }
  }

  window.toggleVideo = function(i) {
    const wrap = document.getElementById(`videoWrap${i}`);
    const btn  = document.getElementById(`playBtn${i}`);
    const isOpen = wrap.classList.contains('open');
    wrap.classList.toggle('open', !isOpen);
    btn.textContent = isOpen ? '▶ Přehrát' : '⏹ Zavřít';
    if (isOpen) {
      const vid = wrap.querySelector('video');
      vid.pause();
      vid.currentTime = 0;
    }
  };

  loadRecordings();
  setInterval(loadRecordings, 30000);
}
