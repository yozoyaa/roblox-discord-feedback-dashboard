(() => {
  const root = document.getElementById("splitRoot");
  if (!root) return;

  const form = document.getElementById("splitForm");
  const fileInput = form ? form.querySelector('input[name="csv_file"]') : null;
  const prefixInput = form ? form.querySelector('input[name="prefix"]') : null;
  const splitMode = document.getElementById("splitMode");
  const ratioChoice = document.getElementById("ratioChoice");
  const ratioWrapper = document.getElementById("ratioWrapper");
  const startBtn = document.getElementById("startBtn");
  const saveBtn = document.getElementById("saveBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const note = document.getElementById("splitNote");
  const csvTextInput = document.getElementById("csvText");
  const formAction = document.getElementById("formAction");
  const splitPayload = document.getElementById("splitPayload");

  const previewAlert = document.getElementById("previewAlert");
  const previewTable = document.getElementById("previewTable");
  const previewHead = document.getElementById("previewHead");
  const previewBody = document.getElementById("previewBody");
  const previewMeta = document.getElementById("previewMeta");
  const previewInfo = document.getElementById("previewInfo");
  const previewSelectionInfo = document.getElementById("previewSelectionInfo");
  const btnDeleteRows = document.getElementById("btnDeleteRows");
  const previewCard = document.getElementById("previewCard");

  const state = { headers: [], rows: [], fileName: "", fileSize: 0 };

  function resetPreview(msg, level = "info") {
    if (previewAlert) {
      previewAlert.style.display = "block";
      const base = level === "danger" ? "alert alert-danger" : "alert alert-light border";
      previewAlert.className = `${base} mb-2`;
      previewAlert.textContent = msg;
    }
    if (previewTable) previewTable.style.display = "none";
    if (previewMeta) previewMeta.textContent = "";
    if (previewInfo) previewInfo.textContent = "";
    if (previewSelectionInfo) previewSelectionInfo.textContent = "";
  }

  function updateSelectionInfo() {
    if (!previewSelectionInfo) return;
    const selected = Array.from(previewBody.querySelectorAll(".row-check:checked")).length;
    previewSelectionInfo.textContent = `${selected} baris dipilih`;
  }

  function renderPreview() {
    if (!previewTable || !previewHead || !previewBody) return;
    if (!state.headers.length) {
      resetPreview("Unggah file CSV untuk melihat preview isi sebelum split dimulai.");
      return;
    }
    previewTable.style.display = "block";
    if (previewAlert) previewAlert.style.display = "none";

    previewHead.innerHTML = "";
    const trHead = document.createElement("tr");
    const thCheck = document.createElement("th");
    const chkAll = document.createElement("input");
    chkAll.type = "checkbox";
    chkAll.addEventListener("change", () => {
      previewBody.querySelectorAll(".row-check").forEach((c) => (c.checked = chkAll.checked));
      updateSelectionInfo();
    });
    thCheck.appendChild(chkAll);
    trHead.appendChild(thCheck);

    const thIdx = document.createElement("th");
    thIdx.textContent = "#";
    trHead.appendChild(thIdx);

    state.headers.forEach((h) => {
      const th = document.createElement("th");
      th.textContent = h;
      trHead.appendChild(th);
    });
    previewHead.appendChild(trHead);

    previewBody.innerHTML = "";
    state.rows.forEach((row, idx) => {
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

      state.headers.forEach((h, colIdx) => {
        const td = document.createElement("td");
        td.textContent = row[colIdx] ?? "";
        tr.appendChild(td);
      });

      previewBody.appendChild(tr);
    });

    if (previewMeta) previewMeta.textContent = `${state.fileName} • ${state.fileSize} B • ${state.rows.length} baris`;
    if (previewInfo) previewInfo.textContent = `Menampilkan ${state.rows.length} baris (dapat dihapus manual sebelum split).`;
    updateSelectionInfo();
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
    const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
    if (!lines.length) return { headers: [], rows: [] };
    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map((ln) => parseCsvLine(ln));
    return { headers, rows };
  }

  function buildCsvFromPreview() {
    if (!state.headers.length) return "";
    const esc = (v) => {
      const s = (v ?? "").toString();
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };
    const lines = [];
    lines.push(state.headers.map(esc).join(","));
    state.rows.forEach((r) => {
      const cells = state.headers.map((_, idx) => esc(r[idx] ?? ""));
      lines.push(cells.join(","));
    });
    return lines.join("\n");
  }

  function handlePreview(file) {
    if (!file) {
      state.headers = [];
      state.rows = [];
      state.fileName = "";
      state.fileSize = 0;
      resetPreview("Unggah file CSV untuk melihat preview isi sebelum split dimulai.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".csv")) {
      resetPreview("File harus berformat .csv", "danger");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result?.toString() || "";
        const parsed = parseCsv(text);
        state.headers = parsed.headers;
        state.rows = parsed.rows;
        state.fileName = file.name;
        state.fileSize = file.size;
        if (!state.headers.length) {
          resetPreview("File kosong atau tidak bisa dibaca.", "danger");
          return;
        }
        if (previewCard) previewCard.style.display = "block";
        renderPreview();
      } catch {
        resetPreview("Gagal membaca file untuk preview.", "danger");
      }
    };
    reader.onerror = () => {
      resetPreview("Gagal membaca file untuk preview.", "danger");
    };
    reader.readAsText(file, "utf-8");
  }

  function refreshRatioOptions() {
    if (!splitMode || !ratioChoice) return;
    const mode = splitMode.value;
    ratioChoice.innerHTML = "";
    if (mode === "3") {
      ratioChoice.insertAdjacentHTML("beforeend", `<option value="70_15_15">70 / 15 / 15</option>`);
      ratioChoice.insertAdjacentHTML("beforeend", `<option value="50_25_25">50 / 25 / 25</option>`);
    } else {
      ratioChoice.insertAdjacentHTML("beforeend", `<option value="70_30">70 / 30</option>`);
      ratioChoice.insertAdjacentHTML("beforeend", `<option value="50_50">50 / 50</option>`);
    }
  }

  if (splitMode) {
    splitMode.addEventListener("change", () => {
      refreshRatioOptions();
    });
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      const file = fileInput.files?.[0];
      handlePreview(file);
    });
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

  if (saveBtn) {
    saveBtn.addEventListener("click", () => {
      if (formAction) formAction.value = "save";
      form.submit();
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      window.location.href = "/split";
    });
  }

  if (form) {
    form.addEventListener("submit", () => {
      if (formAction.value === "save") return;
      // start action: ensure csv text uses edited preview
      if (csvTextInput) {
        csvTextInput.value = buildCsvFromPreview();
      }
      if (!state.headers.length && (!fileInput || !fileInput.value)) {
        if (note) {
          note.className = "form-text text-danger mt-2";
          note.textContent = "Upload CSV dulu sebelum split.";
        }
        event?.preventDefault();
        return;
      }
    });
  }

  refreshRatioOptions();

  // if coming from server previews (after split), show buttons
  if (splitPayload && splitPayload.value && splitPayload.value !== "[]") {
    if (saveBtn) saveBtn.style.display = "block";
    if (cancelBtn) cancelBtn.style.display = "block";
    if (startBtn) startBtn.style.display = "none";
  }
})();
