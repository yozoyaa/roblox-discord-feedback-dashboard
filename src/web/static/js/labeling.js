(() => {
  const root = document.getElementById("labelRoot");
  if (!root) return;

  const jobId = (root.dataset.jobId || "").trim() || null;

  const logBox = document.getElementById("logBox");
  const form = document.getElementById("labelForm");
  const startBtn = document.getElementById("startBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const note = document.getElementById("labelNote");
  const fileInput = form ? form.querySelector('input[name="csv_file"]') : null;
  const previewAlert = document.getElementById("previewAlert");
  const previewTable = document.getElementById("previewTable");
  const previewHead = document.getElementById("previewHead");
  const previewBody = document.getElementById("previewBody");
  const previewMeta = document.getElementById("previewMeta");
  const previewInfo = document.getElementById("previewInfo");
  const previewSelectionInfo = document.getElementById("previewSelectionInfo");
  const previewCard = document.getElementById("previewCard");
  const btnDeleteRows = document.getElementById("btnDeleteRows");
  const csvTextInput = document.getElementById("csvText");
  const jobStatus = document.getElementById("jobStatus");

  const editCard = document.getElementById("labelEditCard");
  const editAlert = document.getElementById("labelEditAlert");
  const editTable = document.getElementById("labelEditTable");
  const editHead = document.getElementById("labelEditHead");
  const editBody = document.getElementById("labelEditBody");
  const editInfo = document.getElementById("labelEditInfo");
  const btnSaveEdit = document.getElementById("btnSaveLabel");
  const btnCancelEdit = document.getElementById("btnCancelEdit");

  const PREVIEW_MAX_BYTES = 512 * 1024;
  const SENT_OPTIONS = ["positif", "negatif"];

  const state = {
    preview: { headers: [], rows: [], fileName: "", fileSize: 0 },
    edit: { headers: [], rows: [] },
  };

  function formatSize(bytes) {
    if (!bytes || bytes < 1024) return `${bytes || 0} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(1)} KB`;
    return `${(kb / 1024).toFixed(1)} MB`;
  }

  function appendLog(line) {
    if (!logBox) return;
    logBox.textContent += (logBox.textContent.endsWith("\n") ? "" : "\n") + line;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function setRunningUI(running) {
    if (form) {
      form.querySelectorAll("input, button, select").forEach((el) => {
        if (el.id === "cancelBtn") return;
        el.disabled = running;
      });
    }

    if (startBtn) startBtn.style.display = running ? "none" : "block";
    if (cancelBtn) cancelBtn.style.display = running ? "block" : "none";

    if (note) {
      if (running) {
        note.className = "form-text text-danger mt-2";
        note.textContent = 'Labeling sedang berjalan. Klik "Batal Labeling" jika perlu.';
      } else {
        note.className = "form-text text-muted mt-2";
        note.textContent = "Upload CSV lalu klik Start Labeling.";
      }
    }

    if (cancelBtn) {
      cancelBtn.disabled = false;
      cancelBtn.textContent = "Batal Labeling";
    }
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
    if (previewSelectionInfo) previewSelectionInfo.textContent = "";
    if (previewInfo) previewInfo.textContent = "";
  }

  function updateSelectionInfo() {
    if (!previewSelectionInfo) return;
    const selected = Array.from(previewBody.querySelectorAll(".row-check:checked")).length;
    previewSelectionInfo.textContent = `${selected} baris dipilih`;
  }

  function renderPreview() {
    if (!previewTable || !previewHead || !previewBody) return;
    const { headers, rows, fileName, fileSize } = state.preview;

    if (!headers.length) {
      resetPreview("Unggah file CSV untuk melihat preview.");
      return;
    }

    previewTable.style.display = "block";
    if (previewAlert) previewAlert.style.display = "none";

    const safeHeaders = headers.length ? headers : rows[0]?.map((_, idx) => `Kolom ${idx + 1}`) || [];

    previewHead.innerHTML = "";
    const headTr = document.createElement("tr");
    const thCheck = document.createElement("th");
    const chkAll = document.createElement("input");
    chkAll.type = "checkbox";
    chkAll.addEventListener("change", () => {
      previewBody.querySelectorAll(".row-check").forEach((c) => {
        c.checked = chkAll.checked;
      });
      updateSelectionInfo();
    });
    thCheck.appendChild(chkAll);
    headTr.appendChild(thCheck);

    const thIdx = document.createElement("th");
    thIdx.textContent = "#";
    headTr.appendChild(thIdx);

    safeHeaders.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      headTr.appendChild(th);
    });
    previewHead.appendChild(headTr);

    previewBody.innerHTML = "";
    rows.forEach((r, idx) => {
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

      safeHeaders.forEach((_, colIdx) => {
        const td = document.createElement("td");
        td.textContent = r[colIdx] ?? "";
        tr.appendChild(td);
      });
      previewBody.appendChild(tr);
    });

    if (previewMeta) previewMeta.textContent = `${fileName} • ${formatSize(fileSize)} • ${rows.length} baris`;
    if (previewInfo) previewInfo.textContent = `Menampilkan ${rows.length} baris (dapat dihapus manual sebelum labeling).`;
    updateSelectionInfo();
  }

  function parseCsvLine(line) {
    const row = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
      } else if (ch === "," && !inQuotes) {
        row.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    row.push(cur);
    return row;
  }

  function parseCsv(text) {
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return { headers: [], rows: [] };
    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map(parseCsvLine);
    return { headers, rows };
  }

  function handlePreview(file) {
    if (!file) {
      state.preview = { headers: [], rows: [], fileName: "", fileSize: 0 };
      resetPreview("Unggah file CSV untuk melihat preview.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      resetPreview("File harus berformat .csv", "danger");
      return;
    }

    if (previewAlert) {
      previewAlert.style.display = "block";
      previewAlert.className = "alert alert-light border mb-2";
      previewAlert.textContent = "Memuat preview...";
    }

    state.preview.fileName = file.name;
    state.preview.fileSize = file.size;

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result?.toString() || "";
        const parsed = parseCsv(text);
        state.preview.headers = parsed.headers;
        state.preview.rows = parsed.rows;
        if (!parsed.headers.length) {
          resetPreview("File kosong atau tidak bisa dibaca.", "danger");
          return;
        }
        renderPreview();
      } catch (e) {
        resetPreview("Gagal membaca file untuk preview.", "danger");
      }
    };
    reader.onerror = () => {
      resetPreview("Gagal membaca file untuk preview.", "danger");
    };
    reader.readAsText(file, "utf-8");
  }

  function buildCsvFromPreview() {
    const { headers, rows } = state.preview;
    if (!headers.length) return "";
    const esc = (v) => {
      const s = (v ?? "").toString();
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };
    const lines = [];
    lines.push(headers.map(esc).join(","));
    rows.forEach((row) => {
      const cells = headers.map((_, idx) => esc(row[idx] ?? ""));
      lines.push(cells.join(","));
    });
    return lines.join("\n");
  }

  function showEditCard(message) {
    if (editAlert) {
      editAlert.style.display = message ? "block" : "none";
      editAlert.textContent = message || "";
    }
    if (editCard) editCard.style.display = "block";
  }

  function hideEditCard() {
    if (editCard) editCard.style.display = "none";
  }

  function renderEditTable() {
    if (!editTable || !editHead || !editBody) return;
    const { headers, rows } = state.edit;
    if (!headers.length) {
      hideEditCard();
      return;
    }

    editTable.style.display = "block";
    editHead.innerHTML = "";
    const headTr = document.createElement("tr");
    headers.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      headTr.appendChild(th);
    });
    editHead.appendChild(headTr);

    editBody.innerHTML = "";
    rows.forEach((row, idx) => {
      const tr = document.createElement("tr");
      headers.forEach((h) => {
        const td = document.createElement("td");
        if (h.toLowerCase() === "sentimen") {
          const sel = document.createElement("select");
          sel.className = "form-select form-select-sm";
          SENT_OPTIONS.forEach((opt) => {
            const option = document.createElement("option");
            option.value = opt;
            option.textContent = opt;
            if ((row[h] || "").toLowerCase() === opt.toLowerCase()) {
              option.selected = true;
            }
            sel.appendChild(option);
          });
          sel.addEventListener("change", () => {
            row[h] = sel.value;
          });
          td.appendChild(sel);
        } else {
          td.textContent = row[h] ?? "";
        }
        tr.appendChild(td);
      });
      editBody.appendChild(tr);
    });

    if (editInfo) {
      editInfo.textContent = `Edit sentimen secara manual jika perlu, lalu simpan. Total baris: ${rows.length}`;
    }
    showEditCard("");
  }

  async function loadEditData() {
    if (!jobId) return;
    try {
      const res = await fetch(`/labeling/result/${jobId}`);
      const data = await res.json();
      if (!data.ok) {
        showEditCard(data.message || "Gagal memuat hasil labeling.");
        return;
      }
      state.edit.headers = data.headers || [];
      state.edit.rows = data.rows || [];
      renderEditTable();
      if (note) {
        note.className = "form-text text-info mt-2";
        note.textContent = "Labeling selesai. Review sentimen lalu Simpan atau Batalkan preview.";
      }
    } catch (e) {
      showEditCard("Gagal memuat hasil labeling (network error).");
    }
  }

  async function saveEditData() {
    if (!jobId) return;
    if (!state.edit.headers.length) return;
    if (btnSaveEdit) {
      btnSaveEdit.disabled = true;
      btnSaveEdit.textContent = "Menyimpan...";
    }
    try {
      const res = await fetch(`/labeling/save/${jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          headers: state.edit.headers,
          rows: state.edit.rows,
        }),
      });
      const data = await res.json();
      if (data.ok) {
        showEditCard("Berhasil menyimpan hasil labeling.");
        setTimeout(() => hideEditCard(), 800);
        if (note) {
          note.className = "form-text text-success mt-2";
          note.textContent = "Labeling disimpan. Cek History jika perlu.";
        }
      } else {
        showEditCard(data.message || "Gagal menyimpan.");
      }
    } catch (e) {
      showEditCard("Gagal menyimpan (network error).");
    } finally {
      if (btnSaveEdit) {
        btnSaveEdit.disabled = false;
        btnSaveEdit.textContent = "Simpan Perubahan";
      }
    }
  }

  // Init preview
  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (jobId) return;
      const file = fileInput.files?.[0];
      handlePreview(file);
    });
  }

  if (btnDeleteRows) {
    btnDeleteRows.addEventListener("click", () => {
      const checks = Array.from(previewBody.querySelectorAll(".row-check:checked"));
      if (!checks.length) return;
      const toRemove = new Set(checks.map((c) => Number(c.dataset.idx)));
      state.preview.rows = state.preview.rows.filter((_, idx) => !toRemove.has(idx));
      renderPreview();
    });
  }

  // Cancel
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      if (!jobId) return;

      cancelBtn.disabled = true;
      cancelBtn.textContent = "Membatalkan...";

      try {
        const res = await fetch(`/labeling/cancel/${jobId}`, { method: "POST" });
        const data = await res.json();
        appendLog(`[UI] ${data.message}`);
      } catch {
        appendLog("[UI] Gagal cancel (network error).");
        cancelBtn.disabled = false;
        cancelBtn.textContent = "Batal Labeling";
      }
    });
  }

  // Edit actions
  if (btnSaveEdit) {
    btnSaveEdit.addEventListener("click", () => {
      saveEditData();
    });
  }
  if (btnCancelEdit) {
    btnCancelEdit.addEventListener("click", () => {
      hideEditCard();
      if (note) {
        note.className = "form-text text-muted mt-2";
        note.textContent = "Preview ditutup. Jalankan labeling lagi jika perlu.";
      }
    });
  }

  // Form submit: prevent double click + send edited CSV
  if (form && startBtn) {
    form.addEventListener("submit", () => {
      if (csvTextInput) {
        csvTextInput.value = buildCsvFromPreview();
      }
      startBtn.disabled = true;
      startBtn.textContent = "Memulai...";
      hideEditCard();
    });
  }

  // SSE stream
  if (jobId) {
    if (logBox) {
      logBox.textContent = "";
      appendLog("[UI] Menyambungkan ke stream log...");
    }
    setRunningUI(true);
    if (jobStatus) jobStatus.textContent = `Job: ${jobId}`;

    const es = new EventSource(`/labeling/stream/${jobId}`);

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
            note.textContent = "Selesai. Muat ulang hasil untuk edit sentimen.";
          } else if (cancelled) {
            note.className = "form-text text-warning mt-2";
            note.textContent = "Job dibatalkan. Kamu bisa start ulang dengan input baru.";
          } else {
            note.className = "form-text text-danger mt-2";
            note.textContent = "Terjadi error. Cek log di bawah.";
          }
        }

        if (done) {
          loadEditData();
        }
      }
    };

    es.onerror = () => {
      appendLog("[UI] Stream terputus / error koneksi.");
      es.close();
      setRunningUI(false);
    };
  } else {
    setRunningUI(false);
    resetPreview("Unggah file CSV untuk melihat preview.");
  }
})();
