(() => {
  const root = document.getElementById("processRoot");
  const form = document.getElementById("processForm");
  const startBtn = document.getElementById("startBtn");
  const stepCard = document.getElementById("stepCard");
  const previewCard = document.getElementById("previewCard");
  const stepsList = document.getElementById("stepsList");
  const stepTitle = document.getElementById("stepTitle");
  const stepHint = document.getElementById("stepHint");
  const jobStatus = document.getElementById("jobStatus");
  const logStatus = document.getElementById("logStatus");
  const logBox = document.getElementById("logBox");
  const btnNext = document.getElementById("btnNext");
  const btnCancelJob = document.getElementById("btnCancelJob");
  const previewMeta = document.getElementById("previewMeta");
  const textColHidden = document.getElementById("text_col");
  const labelColHidden = document.getElementById("label_col");
  const textColDisplay = document.getElementById("textColDisplay");
  const labelColDisplay = document.getElementById("labelColDisplay");
  const textColSelect = document.getElementById("textColSelect");
  const labelColSelect = document.getElementById("labelColSelect");
  const trainInput = form?.querySelector('input[name="train_file"]');
  const testInput = form?.querySelector('input[name="test_file"]');
  const warningBox = document.getElementById("processWarning");
  let preprocessConfig = null;

  let jobId = root?.dataset.jobId || "";
  let steps = [];
  let stepIndex = 0;
  let done = false;
  let saved = false;
  let trainHeaders = [];

  const previewTargets = {
    train: { head: document.getElementById("trainHead"), body: document.getElementById("trainBody"), meta: document.getElementById("trainMeta") },
    test: { head: document.getElementById("testHead"), body: document.getElementById("testBody"), meta: document.getElementById("testMeta") },
    val: { head: document.getElementById("valHead"), body: document.getElementById("valBody"), meta: document.getElementById("valMeta") },
  };

  function log(msg) {
    if (!logBox) return;
    const ts = new Date().toLocaleTimeString();
    logBox.textContent += `\n[${ts}] ${msg}`;
    logBox.scrollTop = logBox.scrollHeight;
  }
  function appendLogLines(lines) {
    if (!Array.isArray(lines)) return;
    lines.forEach((line) => log(line));
  }

  function setStatusText(text) {
    if (jobStatus) jobStatus.textContent = text;
    if (logStatus) logStatus.textContent = text;
  }

  function renderSteps() {
    if (!stepsList) return;
    stepsList.innerHTML = "";
    steps.forEach((step, idx) => {
      const col = document.createElement("div");
      col.className = "col-6 col-md-4 col-lg-2";
      const box = document.createElement("div");
      box.className = "p-2 border rounded text-center";
      const badge = document.createElement("span");
      badge.className = "badge";
      if (idx < stepIndex) {
        badge.classList.add("bg-success");
        badge.textContent = "Done";
      } else if (idx === stepIndex && !done) {
        badge.classList.add("bg-primary");
        badge.textContent = "Current";
      } else {
        badge.classList.add("bg-secondary");
        badge.textContent = "Pending";
      }
      const title = document.createElement("div");
      title.className = "fw-semibold small mt-1";
      title.textContent = `${idx + 1}. ${step}`;
      box.appendChild(badge);
      box.appendChild(title);
      col.appendChild(box);
      stepsList.appendChild(col);
    });
  }

  function renderPreviewSection(previews) {
    const splits = ["train", "test", "val"];
    splits.forEach((name) => {
      const target = previewTargets[name];
      if (!target) return;
      const data = previews?.[name];
      if (!data) {
        if (target.head) target.head.innerHTML = "";
        if (target.body) target.body.innerHTML = "";
        if (target.meta) target.meta.textContent = name === "val" ? "Val tidak diupload." : "Belum ada data.";
        return;
      }
      const { headers = [], rows = [], total = 0 } = data;
      if (target.head) {
        target.head.innerHTML = "";
        const tr = document.createElement("tr");
        headers.forEach((h) => {
          const th = document.createElement("th");
          th.textContent = h;
          tr.appendChild(th);
        });
        target.head.appendChild(tr);
      }
      if (target.body) {
        target.body.innerHTML = "";
        rows.forEach((row) => {
          const tr = document.createElement("tr");
          headers.forEach((h) => {
            const td = document.createElement("td");
            td.textContent = row[h] ?? "";
            tr.appendChild(td);
          });
          target.body.appendChild(tr);
        });
      }
      if (target.meta) {
        target.meta.textContent = `${total} rows x ${headers.length} kolom`;
      }
    });
  }

  function refreshButtons() {
    if (!btnNext || !btnCancelJob) return;
    if (!jobId) {
      btnNext.disabled = true;
      btnCancelJob.disabled = true;
      return;
    }
    btnCancelJob.disabled = false;
    if (done) {
      btnNext.textContent = "Save Output";
    } else {
      btnNext.textContent = `Next Step (${Math.min(stepIndex + 1, steps.length)}/${steps.length || 1})`;
    }
  }

  function parseHeaderLine(line) {
    const headers = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        inQuotes = !inQuotes;
        continue;
      }
      if (ch === "," && !inQuotes) {
        headers.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    if (current.length > 0) headers.push(current.trim());
    return headers.filter((h) => h.length > 0);
  }

  const TEXT_PRIORITIES = ["tokens_stemmed", "text_processed", "tokens_no_stopwords", "text_clean", "text_case", "text", "feedback", "comment", "tweet"];
  const LABEL_PRIORITIES = ["sentimen", "label", "sentiment", "kelas", "class", "target"];

  function chooseColumn(headers, priorities) {
    const lowerSet = new Set(headers.map((h) => h.toLowerCase()));
    for (const key of priorities) {
      if (lowerSet.has(key.toLowerCase())) {
        const idx = headers.findIndex((h) => h.toLowerCase() === key.toLowerCase());
        if (idx >= 0) return headers[idx];
      }
    }
    return headers[0] || "";
  }

  function populateSelect(selectEl, headers, selected) {
    if (!selectEl) return;
    const placeholder = '<option value="">Pilih kolom</option>';
    selectEl.innerHTML = placeholder + headers.map((h) => `<option value="${h}">${h}</option>`).join("");
    if (selected) selectEl.value = selected;
  }

  function updateDisplays() {
    if (textColDisplay && textColHidden) textColDisplay.textContent = textColHidden.value || "-";
    if (labelColDisplay && labelColHidden) labelColDisplay.textContent = labelColHidden.value || "-";
  }

  function setColumns(textCol, labelCol) {
    if (textColHidden) textColHidden.value = textCol;
    if (labelColHidden) labelColHidden.value = labelCol;
    updateDisplays();
  }

  function handleHeaders(headers) {
    trainHeaders = headers;
    const textCol = chooseColumn(headers, TEXT_PRIORITIES);
    const labelCol = chooseColumn(headers, LABEL_PRIORITIES);
    populateSelect(textColSelect, headers, textCol);
    populateSelect(labelColSelect, headers, labelCol);
    setColumns(textCol, labelCol);
    validateForm();
  }

  function readTrainHeader(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const raw = (e?.target?.result || "").toString();
      const headerLine = raw.split(/\r?\n/)[0] || "";
      const headers = parseHeaderLine(headerLine);
      if (headers.length > 0) {
        handleHeaders(headers);
      } else {
        trainHeaders = [];
        validateForm();
      }
    };
    reader.onerror = () => {
      trainHeaders = [];
      validateForm();
    };
    const slice = file.slice(0, 4096);
    reader.readAsText(slice);
  }

  function showWarning(messages) {
    if (!warningBox) return;
    if (messages.length === 0) {
      warningBox.classList.add("d-none");
      warningBox.textContent = "";
      return;
    }
    warningBox.textContent = messages.join(" ");
    warningBox.classList.remove("d-none");
  }

  function validateForm(showMessage = false) {
    if (!form) return false;
    const messages = [];
    const hasTrain = Boolean(trainInput?.files?.length);
    const hasTest = Boolean(testInput?.files?.length);
    if (!hasTrain) messages.push("Upload Train data terlebih dahulu.");
    if (!hasTest) messages.push("Upload Test data terlebih dahulu.");
    if (trainHeaders.length === 0) messages.push("Header Train belum terbaca.");

    const textCol = textColHidden?.value || "";
    const labelCol = labelColHidden?.value || "";
    if (trainHeaders.length > 0) {
      const lower = new Set(trainHeaders.map((h) => h.toLowerCase()));
      if (!lower.has(textCol.toLowerCase())) messages.push(`Kolom teks "${textCol || "(kosong)"}" tidak ada di header Train.`);
      if (!lower.has(labelCol.toLowerCase())) messages.push(`Kolom label "${labelCol || "(kosong)"}" tidak ada di header Train.`);
    }

    const isValid = messages.length === 0;
    if (startBtn) startBtn.disabled = !isValid;
    if (showMessage) {
      showWarning(messages);
    } else if (warningBox) {
      warningBox.classList.add("d-none");
      warningBox.textContent = "";
    }
    return isValid;
  }

  function logSummaries(stepName, summaries) {
    if (!summaries) return;
    Object.entries(summaries).forEach(([split, summary]) => {
      if (!summary) return;
      if (summary.dropped_rows !== undefined) {
        const reasons = summary.reason_counts || {};
        const topReasons = Object.entries(reasons)
          .sort((a, b) => b[1] - a[1])
          .slice(0, 3)
          .map(([r, c]) => `${r}:${c}`)
          .join(", ");
        const tokensRemoved = summary.tokens_removed_total !== undefined ? ` | tokens removed: ${summary.tokens_removed_total}` : "";
        log(
          `${stepName} (${split}): dropped ${summary.dropped_rows}, kept ${summary.kept_rows}${tokensRemoved}${
            topReasons ? ` | reasons: ${topReasons}` : ""
          }`
        );
        const samples = summary.samples || [];
        samples.slice(0, 2).forEach((s) => {
          const orig = (s.original || "").slice(0, 80);
          const fin = (s.final || "").slice(0, 80);
          log(`  sample [${split}] reason=${s.reason}: "${orig}" -> "${fin}"`);
        });
      }
    });
  }

  function logLabelStats(labelStats) {
    if (!labelStats) return;
    Object.entries(labelStats).forEach(([split, stats]) => {
      const neg = stats?.negatif ?? 0;
      const pos = stats?.positif ?? 0;
      const unknown = stats?.unknown ?? 0;
      log(`Label dist (${split}): negatif=${neg}, positif=${pos}${unknown ? `, unknown=${unknown}` : ""}`);
    });
  }

  function handleState(state, msg = "") {
    if (!state || !state.ok) {
      if (msg) log(msg);
      return;
    }
    steps = state.steps || [];
    stepIndex = state.step_index || 0;
    done = Boolean(state.done);
    saved = Boolean(state.saved);

    if (stepTitle) {
      const current = steps[stepIndex] || "Selesai";
      stepTitle.textContent = done ? "Semua step selesai" : `Step: ${current}`;
    }
    if (previewMeta) {
      previewMeta.textContent = done ? "Selesai. Klik Save untuk simpan output." : "Preview otomatis ter-update tiap selesai step.";
    }
    setStatusText(jobId ? `Job: ${jobId}${saved ? " (saved)" : ""}` : "Belum ada job");
    renderSteps();
    renderPreviewSection(state.previews || {});
    refreshButtons();
    if (msg) log(msg);
  }

  async function fetchState() {
    if (!jobId) return;
    try {
      const res = await fetch(`/processing/state/${jobId}`);
      const data = await res.json();
      if (!data.ok) {
        log(data.message || "Gagal ambil state.");
        return;
      }
      stepCard.style.display = "block";
      previewCard.style.display = "block";
      handleState(data, "State dimuat.");
    } catch (err) {
      log("Gagal memuat state job.");
    }
  }

  async function runNext() {
    if (!jobId) {
      log("Buat job terlebih dahulu.");
      return;
    }
    if (done) {
      await saveJob();
      return;
    }
    btnNext.disabled = true;
    try {
      const res = await fetch(`/processing/next/${jobId}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        log(data.message || "Step gagal.");
      } else {
        handleState(data, data.message || "Step selesai.");
        logSummaries(data.step, data.summaries);
        if (data.label_stats) logLabelStats(data.label_stats);
        if (data.log_lines) appendLogLines(data.log_lines);
      }
    } catch (err) {
      log("Gagal menjalankan step berikut.");
    } finally {
      btnNext.disabled = false;
    }
  }

  async function saveJob() {
    if (!jobId) return;
    btnNext.disabled = true;
    try {
      const res = await fetch(`/processing/save/${jobId}`, { method: "POST" });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        log(data.message || "Gagal menyimpan output.");
      } else {
        log(`Output disimpan: ${data.output}`);
        saved = true;
        jobId = "";
        root.dataset.jobId = "";
        stepCard.style.display = "none";
        previewCard.style.display = "none";
        setStatusText("Output tersimpan. Mulai job baru untuk memproses lagi.");
        if (logBox) logBox.textContent = "";
        Object.values(previewTargets).forEach((t) => {
          if (t.head) t.head.innerHTML = "";
          if (t.body) t.body.innerHTML = "";
          if (t.meta) t.meta.textContent = "";
        });
      }
    } catch (err) {
      log("Gagal menyimpan output.");
    } finally {
      btnNext.disabled = false;
      refreshButtons();
    }
  }

  async function cancelJob() {
    if (!jobId) return;
    btnCancelJob.disabled = true;
    try {
      const res = await fetch(`/processing/cancel/${jobId}`, { method: "POST" });
      await res.json();
      log("Job dibatalkan dan dibersihkan.");
    } catch (err) {
      log("Gagal membatalkan job.");
    } finally {
      jobId = "";
      root.dataset.jobId = "";
      stepCard.style.display = "none";
      previewCard.style.display = "none";
      refreshButtons();
      btnCancelJob.disabled = false;
      setStatusText("Tidak ada job aktif.");
    }
  }

  if (btnNext) btnNext.addEventListener("click", runNext);
  if (btnCancelJob) btnCancelJob.addEventListener("click", cancelJob);

  async function loadConfig() {
    try {
      const res = await fetch("/processing/config");
      const data = await res.json();
      if (data?.ok) {
        preprocessConfig = data.config;
        log("Config loaded.");
      }
    } catch (err) {
      log("Gagal memuat config preprocessing.");
    }
  }

  if (form) {
    if (startBtn) startBtn.disabled = true;

    if (trainInput) {
      trainInput.addEventListener("change", () => {
        const file = trainInput.files?.[0];
        readTrainHeader(file);
        validateForm();
      });
    }

    if (testInput) {
      testInput.addEventListener("change", () => validateForm());
    }

    if (textColSelect) {
      textColSelect.addEventListener("change", () => {
        const val = textColSelect.value || textColHidden?.value || "";
        setColumns(val, labelColHidden?.value || "");
        validateForm();
      });
    }

    if (labelColSelect) {
      labelColSelect.addEventListener("change", () => {
        const val = labelColSelect.value || labelColHidden?.value || "";
        setColumns(textColHidden?.value || "", val);
        validateForm();
      });
    }

    updateDisplays();
    validateForm();

    form.addEventListener("submit", (e) => {
      if (jobId && !saved) {
        e.preventDefault();
        log("Selesaikan atau save job yang berjalan sebelum mulai baru.");
        alert("Simpan atau batalkan job yang sedang berjalan sebelum memulai job baru.");
        return;
      }
      const ok = validateForm(true);
      if (!ok) {
        e.preventDefault();
        return;
      }
      if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = "Membuat job...";
      }
    });
  }

  // init
  loadConfig();
  if (jobId) {
    stepCard.style.display = "block";
    previewCard.style.display = "block";
    log("Job processing dibuat. Klik Next Step untuk mulai.");
    fetchState();
  }
  refreshButtons();
})(); 
