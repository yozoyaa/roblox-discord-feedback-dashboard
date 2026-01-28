(() => {
  const root = document.getElementById("validateRoot");
  if (!root) return;

  const jobId = (root.dataset.jobId || "").trim() || null;

  const logBox = document.getElementById("logBox");
  const form = document.getElementById("validateForm");
  const startBtn = document.getElementById("startBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const note = document.getElementById("validateNote");
  const fileInput = form ? form.querySelector('input[name="csv_file"]') : null;
  const csvTextInput = document.getElementById("csvText");
  const previewAlert = document.getElementById("previewAlert");
  const previewTable = document.getElementById("previewTable");
  const previewHead = document.getElementById("previewHead");
  const previewBody = document.getElementById("previewBody");
  const previewMeta = document.getElementById("previewMeta");
  const previewInfo = document.getElementById("previewInfo");
  const previewSelectionInfo = document.getElementById("previewSelectionInfo");
  const previewCard = document.getElementById("previewCard");
  const uploadCard = document.getElementById("uploadCard");
  const btnDeleteRows = document.getElementById("btnDeleteRows");
  const jobStatus = document.getElementById("jobStatus");

  const state = {
    headers: [],
    rows: [],
    fileName: "",
    fileSize: 0,
  };

  function formatSize(bytes) {
    if (!bytes || bytes < 1024) return `${bytes || 0} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  }

  function escapeCsvCell(v) {
    const s = (v ?? "").toString();
    if (/[",\n]/.test(s)) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  }

  function buildCsv() {
    if (!state.headers.length) return "";
    const lines = [];
    lines.push(state.headers.map(escapeCsvCell).join(","));
    state.rows.forEach((row) => {
      const cells = state.headers.map((_, idx) => escapeCsvCell(row[idx] ?? ""));
      lines.push(cells.join(","));
    });
    return lines.join("\n");
  }

  function appendLog(line) {
    if (!logBox) return;
    logBox.textContent += (logBox.textContent.endsWith("\n") ? "" : "\n") + line;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function resetPreview(message, level = "info") {
    if (previewAlert) {
      previewAlert.style.display = "block";
      const base = level === "danger" ? "alert alert-danger" : "alert alert-light border";
      previewAlert.className = `${base} mb-2`;
      previewAlert.textContent = message;
    }
    if (previewTable) previewTable.style.display = "none";
    if (previewMeta) previewMeta.textContent = "";
    if (previewInfo) previewInfo.textContent = "";
    if (previewSelectionInfo) previewSelectionInfo.textContent = "";
  }

  function renderPreview() {
    if (!previewTable || !previewHead || !previewBody) return;

    if (!state.headers.length) {
      resetPreview("Unggah file CSV untuk melihat preview isi sebelum validasi dimulai.");
      return;
    }

    previewTable.style.display = "block";
    if (previewAlert) previewAlert.style.display = "none";

    previewHead.innerHTML = "";
    const headTr = document.createElement("tr");

    const thSelect = document.createElement("th");
    const chkAll = document.createElement("input");
    chkAll.type = "checkbox";
    chkAll.addEventListener("change", () => {
      previewBody.querySelectorAll(".row-check").forEach((c) => {
        c.checked = chkAll.checked;
      });
      updateSelectionInfo();
    });
    thSelect.appendChild(chkAll);
    headTr.appendChild(thSelect);

    const thIdx = document.createElement("th");
    thIdx.textContent = "#";
    headTr.appendChild(thIdx);

    state.headers.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      headTr.appendChild(th);
    });
    previewHead.appendChild(headTr);

    previewBody.innerHTML = "";
    state.rows.forEach((r, idx) => {
      const tr = document.createElement("tr");

      const tdCheck = document.createElement("td");
      const chk = document.createElement("input");
      chk.type = "checkbox";
      chk.className = "row-check";
      chk.dataset.idx = String(idx);
      chk.addEventListener("change", updateSelectionInfo);
      tdCheck.appendChild(chk);
      tr.appendChild(tdCheck);

      const tdIdx = document.createElement("td");
      tdIdx.textContent = String(idx + 1);
      tr.appendChild(tdIdx);

      state.headers.forEach((_, colIdx) => {
        const td = document.createElement("td");
        td.textContent = r[colIdx] ?? "";
        tr.appendChild(td);
      });

      previewBody.appendChild(tr);
    });

    if (previewMeta) {
      const total = state.rows.length;
      previewMeta.textContent = `${state.fileName} • ${formatSize(state.fileSize)} • ${total} baris`;
    }
    if (previewInfo) {
      previewInfo.textContent = `Menampilkan ${state.rows.length} baris (dapat dihapus manual sebelum validasi).`;
    }
    updateSelectionInfo();
  }

  function updateSelectionInfo() {
    if (!previewSelectionInfo) return;
    const selected = Array.from(previewBody.querySelectorAll(".row-check")).filter((c) => c.checked).length;
    previewSelectionInfo.textContent = `${selected} baris dipilih`;
  }

  function parseCsvLine(line) {
    const row = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"' && inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
        continue;
      }
      if (ch === '"') {
        inQuotes = !inQuotes;
        continue;
      }
      if (ch === "," && !inQuotes) {
        row.push(cur);
        cur = "";
        continue;
      }
      cur += ch;
    }
    row.push(cur);
    return row;
  }

  function parseCsv(text) {
    const lines = (text || "").split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return { headers: [], rows: [] };
    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map(parseCsvLine);
    return { headers, rows };
  }

  function handleFile(file) {
    if (!file) {
      state.headers = [];
      state.rows = [];
      state.fileName = "";
      state.fileSize = 0;
      resetPreview("Unggah file CSV untuk melihat preview isi sebelum validasi dimulai.");
      return;
    }

    state.fileName = file.name;
    state.fileSize = file.size;
    if (previewAlert) {
      previewAlert.style.display = "block";
      previewAlert.className = "alert alert-light border mb-2";
      previewAlert.textContent = "Memuat preview...";
    }
    const reader = new FileReader();
    reader.onload = () => {
      const text = reader.result || "";
      const parsed = parseCsv(text.toString());
      state.headers = parsed.headers;
      state.rows = parsed.rows;
      if (!state.headers.length) {
        resetPreview("Tidak bisa membaca header CSV. Pastikan file tidak kosong.", "danger");
        return;
      }
      renderPreview();
    };
    reader.onerror = () => {
      resetPreview("Gagal membaca file. Coba pilih ulang.", "danger");
    };
    reader.readAsText(file, "utf-8");
  }

  function setRunningUI(running) {
    if (form) {
      form.querySelectorAll("input, select, button, textarea").forEach((el) => {
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

  function closePreviewCard() {
    if (previewCard) previewCard.style.display = "none";
  }

  // Init state
  setRunningUI(Boolean(jobId));

  if (jobId) {
    closePreviewCard();
    if (jobStatus) jobStatus.textContent = `Job: ${jobId}`;
  }

  if (fileInput) {
    const initial = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
    if (initial && !jobId) handleFile(initial);
    fileInput.addEventListener("change", () => {
      if (jobId) return;
      const file = fileInput.files && fileInput.files[0] ? fileInput.files[0] : null;
      handleFile(file);
    });
  } else {
    resetPreview("Unggah file CSV untuk melihat preview isi sebelum validasi dimulai.");
  }

  if (btnDeleteRows) {
    btnDeleteRows.addEventListener("click", () => {
      const checks = Array.from(previewBody.querySelectorAll(".row-check:checked"));
      if (!checks.length) return;
      const toRemove = new Set(checks.map((c) => Number(c.dataset.idx)));
      state.rows = state.rows.filter((_, idx) => !toRemove.has(idx));
      renderPreview();
    });
  }

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

  if (form) {
    form.addEventListener("submit", (e) => {
      if (!state.headers.length && !jobId) {
        e.preventDefault();
        resetPreview("Harus upload file CSV sebelum mulai.", "danger");
        return;
      }

      if (csvTextInput) {
        csvTextInput.value = buildCsv();
      }

      if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = "Memulai...";
      }

      // hide preview once job starts
      closePreviewCard();
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
