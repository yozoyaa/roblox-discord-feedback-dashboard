(() => {
  const form = document.getElementById("evalForm");
  const startBtn = document.getElementById("startBtn");
  const logBox = document.getElementById("logBox");
  const textColHidden = document.getElementById("text_col");
  const labelColHidden = document.getElementById("label_col");
  const textColDisplay = document.getElementById("textColDisplay");
  const labelColDisplay = document.getElementById("labelColDisplay");
  const textColSelect = document.getElementById("textColSelect");
  const labelColSelect = document.getElementById("labelColSelect");
  const dataInput = form?.querySelector('input[name="data_file"]');
  const warningBox = document.getElementById("evalWarning");
  const resultCard = document.getElementById("resultCard");
  const modeBadge = document.getElementById("modeBadge");
  const summaryContainer = document.getElementById("summaryContainer");
  const classificationContainer = document.getElementById("classificationContainer");
  const metricsContainer = document.getElementById("metricsContainer");
  const confusionContainer = document.getElementById("confusionContainer");
  const downloadsContainer = document.getElementById("downloadsContainer");

  let headers = [];

  function log(msg) {
    if (!logBox) return;
    const ts = new Date().toLocaleTimeString();
    logBox.textContent += `\n[${ts}] ${msg}`;
    logBox.scrollTop = logBox.scrollHeight;
  }

  function showWarning(messages) {
    if (!warningBox) return;
    if (!messages || messages.length === 0) {
      warningBox.classList.add("d-none");
      warningBox.textContent = "";
      return;
    }
    warningBox.textContent = messages.join(" ");
    warningBox.classList.remove("d-none");
  }

  function updateDisplays() {
    if (textColDisplay && textColHidden) textColDisplay.textContent = textColHidden.value || "-";
    if (labelColDisplay && labelColHidden) labelColDisplay.textContent = labelColHidden.value || "-";
  }

  function parseHeaderLine(line) {
    const cols = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        inQuotes = !inQuotes;
        continue;
      }
      if (ch === "," && !inQuotes) {
        cols.push(cur.trim());
        cur = "";
      } else {
        cur += ch;
      }
    }
    if (cur.length > 0) cols.push(cur.trim());
    return cols.filter((c) => c.length > 0);
  }

  function chooseColumn(cols, priorities, fallback) {
    const set = new Set(cols.map((c) => c.toLowerCase()));
    for (const p of priorities) {
      if (set.has(p.toLowerCase())) {
        const idx = cols.findIndex((c) => c.toLowerCase() === p.toLowerCase());
        if (idx >= 0) return cols[idx];
      }
    }
    return cols[0] || fallback;
  }

  function populateSelect(selectEl, cols, selected) {
    if (!selectEl) return;
    const placeholder = '<option value="">Pilih kolom</option>';
    selectEl.innerHTML = placeholder + cols.map((c) => `<option value="${c}">${c}</option>`).join("");
    if (selected) selectEl.value = selected;
  }

  function handleHeaders(cols) {
    headers = cols;
    const textCol = chooseColumn(cols, ["tokens_stemmed", "text", "text_clean", "tokens_no_stopwords"], textColHidden?.value || "tokens_stemmed");
    const labelCol = chooseColumn(cols, ["sentimen", "label", "sentiment", "kelas"], labelColHidden?.value || "sentimen");
    populateSelect(textColSelect, cols, textCol);
    populateSelect(labelColSelect, cols, labelCol);
    setColumns(textCol, labelCol);
    validateForm();
  }

  function readHeader(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const raw = (e?.target?.result || "").toString();
      const headerLine = raw.split(/\r?\n/)[0] || "";
      const cols = parseHeaderLine(headerLine);
      if (cols.length > 0) handleHeaders(cols);
    };
    reader.readAsText(file.slice(0, 4096));
  }

  function setColumns(textCol, labelCol) {
    if (textColHidden) textColHidden.value = textCol;
    if (labelColHidden) labelColHidden.value = labelCol;
    updateDisplays();
  }

  function validateForm(showMessage = false) {
    const msgs = [];
    if (!dataInput?.files?.length) msgs.push("Upload Data Uji terlebih dahulu.");
    const textCol = textColHidden?.value || "";
    const labelCol = labelColHidden?.value || "";
    if (headers.length > 0) {
      const lower = new Set(headers.map((h) => h.toLowerCase()));
      if (!lower.has(textCol.toLowerCase())) msgs.push(`Kolom teks "${textCol}" tidak ada di header.`);
      if (labelCol && !lower.has(labelCol.toLowerCase())) msgs.push(`Kolom label "${labelCol}" tidak ada di header.`);
    }
    const valid = msgs.length === 0;
    if (startBtn) startBtn.disabled = !valid;
    if (showMessage) showWarning(msgs);
    else showWarning([]);
    return valid;
  }

  function warnIfSampleFile(file) {
    if (!file) return;
    const name = file.name.toLowerCase();
    if (name.includes("misclassified")) {
      showWarning(["File ini tampak sampel/parsial. Untuk metrik valid, gunakan test_predictions_full.csv atau CSV penuh dengan y_true."]);
    }
  }

  function renderSummary(data) {
    if (!summaryContainer || !data) return;
    const stats = data.stats || {};
    const trueCounts = stats.true_label_counts || {};
    const predCounts = stats.pred_label_counts || {};
    const labels = ["negatif", "positif"];
    const rows = labels
      .map(
        (lbl) =>
          `<tr><td>${lbl}</td><td>${stats.mode === "with_ground_truth" || trueCounts[lbl] !== undefined ? trueCounts[lbl] ?? 0 : "-"}</td><td>${
            predCounts[lbl] ?? 0
          }</td></tr>`
      )
      .join("");
    const distTable = `<table class="table table-sm table-bordered mb-2">
      <thead><tr><th>Label</th><th>True</th><th>Pred</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
    summaryContainer.innerHTML = `
      <div>Created: ${data.created_at || "-"}</div>
      <div>Data artifact: Train=${stats.total_train ?? "-"}, Test=${stats.total_test ?? "-"}, Val=${stats.total_val ?? "-"}</div>
      <div>Total uploaded: ${stats.total_rows_uploaded ?? "-"}</div>
      <div>Dropped empty text: ${stats.rows_dropped_empty_text ?? 0}</div>
      <div>Total classified: ${stats.total_classified ?? "-"}</div>
      <div>Raw data total: ${stats.total_raw_data ?? 0}</div>
      <div>Preprocessed total: ${stats.total_preprocessed_data ?? 0} (Train=${stats.total_preprocessed_train ?? 0}, Test=${stats.total_preprocessed_test ?? 0}, Val=${stats.total_preprocessed_val ?? 0})</div>
      <div class="fw-semibold mt-2">Distribusi Label</div>
      <div class="table-responsive">${distTable}</div>
    `;
    if (Array.isArray(data.optional_warnings) && data.optional_warnings.length > 0) {
      showWarning(data.optional_warnings);
    }
  }

  function renderClassification(preview) {
    if (!classificationContainer) return;
    const tc = textColHidden?.value || "tokens_stemmed";
    const rows = (preview || []).map(
      (r) =>
        `<tr><td>${(r[tc] || r.tokens_stemmed || r.text || "").toString().slice(0, 120)}</td><td>${r.predicted_label || ""}</td><td>${
          r.confidence !== undefined ? Number(r.confidence).toFixed(3) : ""
        }</td></tr>`
    );
    classificationContainer.innerHTML = `<div class="fw-semibold mb-1">Preview hasil klasifikasi (max 20)</div>
      <div class="table-responsive">
        <table class="table table-sm table-bordered mb-0">
          <thead><tr><th>Teks</th><th>Pred</th><th>Conf</th></tr></thead>
          <tbody>${rows.join("") || '<tr><td colspan="3" class="text-muted small">Tidak ada preview.</td></tr>'}</tbody>
        </table>
      </div>`;
  }

  function renderMetrics(metrics) {
    if (!metricsContainer) return;
    if (!metrics || metrics.accuracy === null) {
      metricsContainer.innerHTML = `<div class="text-muted small">Tidak ada ground truth, hanya klasifikasi.</div>`;
      confusionContainer.innerHTML = "";
      return;
    }
    metricsContainer.innerHTML = `
      <div class="fw-semibold mb-1">Metrics (with ground truth)</div>
      <div>Accuracy: ${metrics.accuracy?.toFixed?.(4) ?? "-"}</div>
      <div>Precision macro: ${metrics.precision?.macro?.toFixed?.(4) ?? "-"}, weighted: ${metrics.precision?.weighted?.toFixed?.(4) ?? "-"}</div>
      <div>Recall macro: ${metrics.recall?.macro?.toFixed?.(4) ?? "-"}, weighted: ${metrics.recall?.weighted?.toFixed?.(4) ?? "-"}</div>
    `;
    if (metrics.confusion_matrix) {
      const labels = (metrics.labels || []).length ? metrics.labels : [];
      const cm = metrics.confusion_matrix;
      const header = `<tr><th></th>${(labels || []).map((l) => `<th>${l}</th>`).join("")}</tr>`;
      const rows = cm
        .map((row, i) => `<tr><th>${labels[i] || i}</th>${row.map((v) => `<td>${v}</td>`).join("")}</tr>`)
        .join("");
      confusionContainer.innerHTML = `<div class="fw-semibold mb-1">Confusion Matrix</div>
        <div class="table-responsive">
          <table class="table table-sm table-bordered mb-0"><thead>${header}</thead><tbody>${rows}</tbody></table>
        </div>`;
    } else {
      confusionContainer.innerHTML = "";
    }
  }

  function renderDownloads(files) {
    if (!downloadsContainer) return;
    const links = [];
    if (files.summary_file) links.push(`<a href="/evaluate/download/${files.summary_file}" class="btn btn-outline-primary btn-sm">Download Summary JSON</a>`);
    if (files.classified_file) links.push(`<a href="/evaluate/download/${files.classified_file}" class="btn btn-outline-secondary btn-sm">Download Classified CSV</a>`);
    if (files.zip_file) links.push(`<a href="/evaluate/download/${files.zip_file}" class="btn btn-outline-success btn-sm">Download Zip</a>`);
    downloadsContainer.innerHTML = links.join(" ");
  }

  async function submitForm() {
    const ok = validateForm(true);
    if (!ok) return;
    const fd = new FormData(form);
    if (startBtn) {
      startBtn.disabled = true;
      startBtn.textContent = "Memproses...";
    }
    try {
      const res = await fetch("/evaluate/run", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        log(data.message || "Evaluasi gagal.");
        showWarning([data.message || "Evaluasi gagal."]);
        return;
      }
      showWarning([]);
      resultCard?.classList.remove("d-none");
      modeBadge.textContent = data.mode === "with_ground_truth" ? "Dengan ground truth" : "Klasifikasi saja";
      renderSummary(data);
      renderClassification(data.preview_classified);
      renderMetrics({ ...data.metrics, labels: data.labels });
      renderDownloads({
        summary_file: data.summary_file,
        classified_file: data.classified_file,
        zip_file: data.zip_file,
      });
      log("Evaluasi selesai.");
    } catch (err) {
      log("Gagal memproses evaluasi.");
    } finally {
      if (startBtn) {
        startBtn.disabled = false;
        startBtn.textContent = "Evaluate";
      }
    }
  }

  if (form) {
    startBtn.disabled = true;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitForm();
    });
    if (dataInput) {
      dataInput.addEventListener("change", () => {
        const f = dataInput.files?.[0];
        if (f) {
          readHeader(f);
          warnIfSampleFile(f);
        }
        validateForm();
      });
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
  }
})();
