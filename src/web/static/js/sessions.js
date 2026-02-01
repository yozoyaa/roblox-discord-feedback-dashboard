(function () {
  const SKEY = "kkp_sessions";
  const AKEY = "kkp_active_session";

  function loadSessions() {
    try { return JSON.parse(localStorage.getItem(SKEY) || "[]"); }
    catch { return []; }
  }
  function saveSessions(list) {
    localStorage.setItem(SKEY, JSON.stringify(list));
  }
  function getActive() {
    return localStorage.getItem(AKEY) || "";
  }
  function setActive(id) {
    localStorage.setItem(AKEY, id);
  }

  function makeId() {
    const raw = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
    return raw.replace(/[^a-zA-Z0-9]/g, "").slice(0, 12);
  }

  async function apiCurrent() {
    const res = await fetch("/api/session/current");
    return await res.json();
  }
  async function apiSwitch(sid) {
    const res = await fetch("/api/session/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sid })
    });
    return await res.json();
  }
  async function apiDelete(sid) {
    const res = await fetch(`/api/session/delete/${sid}`, { method: "POST" });
    return await res.json();
  }
  function apiCleanupUploads() {
    const url = "/api/session/cleanup-uploads";
    const payload = JSON.stringify({ reason: "unload" });
    if (navigator.sendBeacon) {
      try {
        const blob = new Blob([payload], { type: "application/json" });
        navigator.sendBeacon(url, blob);
        return;
      } catch (e) {
        // fallback to fetch below
      }
    }
    try {
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload,
        keepalive: true,
      });
    } catch (e) {
      // ignore
    }
  }

  function render(el, sessions, activeSid) {
    el.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "d-flex gap-2 align-items-center";

    const select = document.createElement("select");
    select.className = "form-select form-select-sm";
    select.style.width = "220px";

    sessions.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.sid;
      opt.textContent = s.name;
      if (s.sid === activeSid) opt.selected = true;
      select.appendChild(opt);
    });

    const btnNew = document.createElement("button");
    btnNew.className = "btn btn-outline-secondary btn-sm";
    btnNew.textContent = "New";

    const btnDel = document.createElement("button");
    btnDel.className = "btn btn-outline-danger btn-sm";
    btnDel.textContent = "Delete";

    wrap.appendChild(select);
    wrap.appendChild(btnNew);
    wrap.appendChild(btnDel);
    el.appendChild(wrap);

    select.addEventListener("change", async () => {
      const sid = select.value;
      setActive(sid);
      await apiSwitch(sid);
      window.location.reload();
    });

    btnNew.addEventListener("click", async () => {
      const name = prompt("Nama session baru:", "Dataset Baru");
      if (!name) return;

      const sid = makeId();
      sessions.unshift({ sid, name });
      saveSessions(sessions);
      setActive(sid);

      await apiSwitch(sid);
      window.location.reload();
    });

    btnDel.addEventListener("click", async () => {
      const sid = getActive();
      const item = sessions.find(s => s.sid === sid);
      if (!sid || !item) return;

      if (sid === "default") {
        alert("Default session tidak bisa dihapus.");
        return;
      }

      const ok = confirm(`Hapus session "${item.name}"?\nSemua file session ini akan ikut terhapus.`);
      if (!ok) return;

      await apiDelete(sid);

      const next = sessions.filter(s => s.sid !== sid);
      saveSessions(next);

      const newActive = next[0]?.sid || "default";
      setActive(newActive);
      await apiSwitch(newActive);
      window.location.reload();
    });
  }

  async function init() {
    const mount = document.getElementById("sessionWidget");
    if (!mount) return;

    const current = await apiCurrent();

    let sessions = loadSessions();
    if (sessions.length === 0) {
      sessions = [{ sid: "default", name: "Default Session" }];
      saveSessions(sessions);
    }

    let activeSid = getActive() || current.sid || "default";
    if (!sessions.some(s => s.sid === activeSid)) {
      activeSid = sessions[0].sid;
      setActive(activeSid);
    }

    if (current.sid !== activeSid) {
      await apiSwitch(activeSid);
    }

    render(mount, sessions, activeSid);

    if (!window.__kkp_cleanup_bound) {
      const cleanupHandler = () => apiCleanupUploads();
      window.addEventListener("pagehide", cleanupHandler);
      window.addEventListener("beforeunload", cleanupHandler);
      window.__kkp_cleanup_bound = true;
    }
  }

  init();
})();
