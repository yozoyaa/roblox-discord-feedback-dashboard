// src/web/static/js/crawling.js

(function () {
  const root = document.getElementById("crawlRoot");
  if (!root) return;

  const jobId = root.dataset.jobId || null;

  const logBox = document.getElementById("logBox");
  const crawlForm = document.getElementById("crawlForm");
  const startBtn = document.getElementById("startBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const crawlNote = document.getElementById("crawlNote");

  function appendLog(line) {
    if (!logBox) return;
    logBox.textContent += (logBox.textContent.endsWith("\n") ? "" : "\n") + line;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function setRunningUI(running) {
    // lock form inputs while running (kecuali tombol)
    if (crawlForm) {
      crawlForm.querySelectorAll("input, select").forEach((el) => {
        if (el.id === "startBtn" || el.id === "cancelBtn") return;
        el.disabled = running;
      });
    }

    if (startBtn) startBtn.style.display = running ? "none" : "block";
    if (cancelBtn) cancelBtn.style.display = running ? "block" : "none";

    if (crawlNote) {
      if (running) {
        crawlNote.className = "form-text text-danger mt-2";
        crawlNote.textContent = 'Crawling sedang berjalan. Klik "Batal Crawling" jika kamu salah input.';
      } else {
        crawlNote.className = "form-text text-muted mt-2";
        crawlNote.textContent = "Isi form lalu klik Start Crawling.";
      }
    }

    if (cancelBtn) {
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Batal Crawling";
    }
  }

  // initial state
  setRunningUI(Boolean(jobId));

  // start: no special handler; form submit biasa

  // cancel
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      if (!jobId) return;

      cancelBtn.disabled = true;
      cancelBtn.textContent = "Membatalkan...";

      try {
        const res = await fetch(`/crawling/cancel/${jobId}`, { method: "POST" });
        const data = await res.json();
        appendLog(`[UI] ${data.message}`);
      } catch {
        appendLog("[UI] Gagal cancel (network error).");
        cancelBtn.disabled = false;
        cancelBtn.textContent = "Batal Crawling";
      }
    });
  }

  // SSE stream
  if (jobId) {
    if (logBox) {
      logBox.textContent = "";
      appendLog("[UI] Menyambungkan ke stream log...");
    }

    const es = new EventSource(`/crawling/stream/${jobId}`);

    es.onmessage = (ev) => {
      appendLog(ev.data);

      const done = ev.data.includes("[DONE]");
      const err = ev.data.includes("[ERROR]");
      const cancelled = ev.data.includes("[CANCELLED]");

      if (done || err || cancelled) {
        es.close();
        setRunningUI(false);

        if (crawlNote) {
          if (done) {
            crawlNote.className = "form-text text-success mt-2";
            crawlNote.textContent = "Selesai. Hasil bisa dicek di /files.";
          } else if (cancelled) {
            crawlNote.className = "form-text text-warning mt-2";
            crawlNote.textContent = "Job dibatalkan. Kamu bisa start ulang dengan input baru.";
          } else {
            crawlNote.className = "form-text text-danger mt-2";
            crawlNote.textContent = "Terjadi error. Cek log di bawah.";
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
