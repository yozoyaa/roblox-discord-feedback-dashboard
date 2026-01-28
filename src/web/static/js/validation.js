(() => {
  const root = document.getElementById("validateRoot");
  if (!root) return;

  const jobId = (root.dataset.jobId || "").trim() || null;

  const logBox = document.getElementById("logBox");
  const form = document.getElementById("validateForm");
  const startBtn = document.getElementById("startBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const note = document.getElementById("validateNote");

  function appendLog(line) {
    if (!logBox) return;
    logBox.textContent += (logBox.textContent.endsWith("\n") ? "" : "\n") + line;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function setRunningUI(running) {
    if (form) {
      form.querySelectorAll("input, select, button").forEach((el) => {
        if (el === cancelBtn) return;
        if (el === startBtn) return;
        el.disabled = running;
      });
    }

    if (startBtn) startBtn.style.display = running ? "none" : "block";
    if (cancelBtn) cancelBtn.style.display = running ? "block" : "none";

    if (note) {
      if (running) {
        note.className = "form-text text-danger mt-2";
        note.textContent = 'Validasi sedang berjalan. Klik "Batal Validasi" jika ingin membatalkan.';
      } else {
        note.className = "form-text text-muted mt-2";
        note.textContent = "Upload CSV lalu klik Start Validation.";
      }
    }

    if (cancelBtn) {
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Batal Validasi";
    }
  }

  setRunningUI(Boolean(jobId));

  if (cancelBtn && jobId) {
    cancelBtn.addEventListener("click", async () => {
      cancelBtn.disabled = true;
      cancelBtn.textContent = "Membatalkan...";

      try {
        const res = await fetch(`/validation/cancel/${jobId}`, { method: "POST" });
        const data = await res.json();
        appendLog(`[UI] ${data.message}`);
      } catch (e) {
        appendLog("[UI] Gagal membatalkan (network error).");
        cancelBtn.disabled = false;
        cancelBtn.textContent = "Batal Validasi";
      }
    });
  }

  if (jobId) {
    if (logBox) logBox.textContent = "";
    appendLog("[UI] Menyambungkan ke stream log...");

    const es = new EventSource(`/validation/stream/${jobId}`);
    es.onmessage = (ev) => {
      appendLog(ev.data);

      const done = ev.data.includes("[DONE]");
      const err = ev.data.includes("[ERROR]");
      const cancelled = ev.data.includes("[CANCELLED]");

      if (done || err || cancelled) {
        es.close();
        setRunningUI(false);

        if (note) {
          if (done) {
            note.className = "form-text text-success mt-2";
            note.textContent = "Selesai. Cek History untuk download output.";
          } else if (cancelled) {
            note.className = "form-text text-warning mt-2";
            note.textContent = "Job dibatalkan. Kamu bisa mulai ulang.";
          } else {
            note.className = "form-text text-danger mt-2";
            note.textContent = "Terjadi error. Cek log untuk detail.";
          }
        }
      }
    };

    es.onerror = () => {
      appendLog("[UI] Stream terputus / error koneksi.");
      es.close();
      setRunningUI(false);
    };
  }
})();
