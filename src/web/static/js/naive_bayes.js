(() => {
  const form = document.getElementById("nbForm");
  const startBtn = document.getElementById("startBtn");
  const logBox = document.getElementById("logBox");
  const textColHidden = document.getElementById("text_col");
  const labelColHidden = document.getElementById("label_col");
  const textColDisplay = document.getElementById("textColDisplay");
  const labelColDisplay = document.getElementById("labelColDisplay");
  const textColSelect = document.getElementById("textColSelect");
  const labelColSelect = document.getElementById("labelColSelect");
  const trainInput = form?.querySelector('input[name="train_file"]');
  const testInput = form?.querySelector('input[name="test_file"]');
  const valInput = form?.querySelector('input[name="val_file"]');
  const warningBox = document.getElementById("nbWarning");
  const resultCard = document.getElementById("resultCard");
  const modeBadge = document.getElementById("modeBadge");
  const summaryContainer = document.getElementById("summaryContainer");
  const metricsContainer = document.getElementById("metricsContainer");
  const reportContainer = document.getElementById("reportContainer");
  const confusionContainer = document.getElementById("confusionContainer");
  const misclassifiedContainer = document.getElementById("misclassifiedContainer");
  const topTermsContainer = document.getElementById("topTermsContainer");
  const downloadsContainer = document.getElementById("downloadsContainer");

  let trainHeaders = [];

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

  function checkLabelSample(headers, rawLines) {
    if (!headers || headers.length === 0 || !rawLines) return [];
    const idx = headers.findIndex((h) => h.toLowerCase() === (labelColHidden?.value || "").toLowerCase());
    if (idx === -1) return [];
    const lines = rawLines.split(/\r?\n/).slice(1, 51);
    const seen = new Set();
    for (const line of lines) {
      if (!line.trim()) continue;
      const cols = parseHeaderLine(line);
      if (cols.length <= idx) continue;
      const val = cols[idx].trim().toLowerCase();
      if (val) seen.add(val);
    }
    const invalid = [...seen].filter((v) => v !== "negatif" && v !== "positif");
    if (invalid.length > 0) {
      return [`Label tidak valid terdeteksi di Train (contoh: ${invalid.slice(0, 3).join(", ")}). Hanya mendukung negatif/positif.`];
    }
    return [];
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
        const labelWarnings = checkLabelSample(headers, raw);
        if (labelWarnings.length) {
          showWarning(labelWarnings);
        }
      } else {
        trainHeaders = [];
        validateForm();
      }
    };
    reader.onerror = () => {
      trainHeaders = [];
      validateForm();
    };
    reader.readAsText(file.slice(0, 4096));
  }

  function validateForm(showMessage = false) {
    const messages = [];
    const infoMessages = [];
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
    if (labelCol && labelCol.toLowerCase() !== "sentimen") {
      infoMessages.push('Kolom label bukan "sentimen". Pastikan nilainya hanya negatif/positif.');
    }
    const isValid = messages.length === 0;
    if (startBtn) startBtn.disabled = !isValid;
    const combined = [...messages, ...infoMessages];
    if (showMessage || infoMessages.length) showWarning(combined);
    else showWarning([]);
    return isValid;
  }

  function renderLabelDist(labelDist) {
    if (!labelDist) return "";
    const rows = Object.entries(labelDist).map(
      ([lbl, stats]) => `<tr><td>${lbl}</td><td>${stats.count}</td><td>${(stats.pct * 100).toFixed(2)}%</td></tr>`
    );
    return `<table class="table table-sm table-bordered mb-1"><thead><tr><th>Label</th><th>Count</th><th>%</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  }

  function renderDatasetSummary(summary) {
    if (!summaryContainer || !summary) return;
    const counts = summary.counts || {};
    const dist = summary.label_dist || {};
    const warn = summary.warnings || [];
    summaryContainer.innerHTML = `
      <div class="mb-2">Jumlah data: Train=${counts.train || 0}, Test=${counts.test || 0}, Val=${counts.val || 0}</div>
      <div class="row g-3">
        <div class="col-md-4"><div class="fw-semibold mb-1">Train label dist</div>${renderLabelDist(dist.train)}</div>
        <div class="col-md-4"><div class="fw-semibold mb-1">Test label dist</div>${renderLabelDist(dist.test)}</div>
        <div class="col-md-4"><div class="fw-semibold mb-1">Val label dist</div>${renderLabelDist(dist.val)}</div>
      </div>
      ${warn.length ? `<div class="alert alert-warning mt-2 mb-0 small">${warn.join(" | ")}</div>` : ""}`;
  }

  function renderMetrics(res) {
    if (!metricsContainer || !res) return;
    const test = res.test || {};
    const valInfo = res.best_val_macro_f1 !== undefined ? `<div>Best Val Macro F1: ${res.best_val_macro_f1?.toFixed?.(4) ?? res.best_val_macro_f1}</div>` : "";
    metricsContainer.innerHTML = `
      <div class="fw-semibold mb-1">Test Metrics</div>
      <div>Accuracy: ${test.accuracy?.toFixed?.(4) ?? "-"}</div>
      <div>Macro F1: ${test.macro_f1?.toFixed?.(4) ?? "-"}</div>
      <div>Weighted F1: ${test.weighted_f1?.toFixed?.(4) ?? "-"}</div>
      ${valInfo}
    `;
  }

  function renderReport(report) {
    if (!reportContainer || !report) return;
    const rows = Object.entries(report)
      .filter(([k, v]) => k !== "accuracy" && typeof v === "object")
      .map(([label, stats]) => {
        const f1 = stats["f1-score"];
        return `<tr><td>${label}</td><td>${stats.precision?.toFixed?.(3) ?? "-"}</td><td>${stats.recall?.toFixed?.(3) ?? "-"}</td><td>${f1?.toFixed?.(3) ?? "-"}</td><td>${stats.support ?? "-"}</td></tr>`;
      })
      .join("");
    reportContainer.innerHTML = `<div class="fw-semibold mb-1">Classification Report (Test)</div>
      <div class="table-responsive">
        <table class="table table-sm table-bordered mb-0">
          <thead><tr><th>Label</th><th>Precision</th><th>Recall</th><th>F1</th><th>Support</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function renderConfusion(cm, labels) {
    if (!confusionContainer || !cm) return;
    const rows = cm.map((row, i) => {
      const cells = row.map((v) => `<td>${v}</td>`).join("");
      return `<tr><th>${labels[i] || i}</th>${cells}</tr>`;
    });
    const header = `<tr><th></th>${(labels || []).map((l) => `<th>${l}</th>`).join("")}</tr>`;
    confusionContainer.innerHTML = `<div class="fw-semibold mb-1">Confusion Matrix (Test)</div>
      <div class="table-responsive">
        <table class="table table-sm table-bordered mb-0">
          <thead>${header}</thead>
          <tbody>${rows.join("")}</tbody>
        </table>
      </div>`;
  }

  function renderMisclassified(list) {
    if (!misclassifiedContainer || !list) return;
    const rows = (list || []).slice(0, 20).map(
      (m) =>
        `<tr><td>${m.text}</td><td>${m.y_true}</td><td>${m.y_pred}</td><td>${m.confidence?.toFixed?.(3) ?? ""}</td></tr>`
    );
    misclassifiedContainer.innerHTML = `<div class="fw-semibold mb-1">Misclassified (max 20)</div>
      <div class="table-responsive">
        <table class="table table-sm table-bordered mb-0">
          <thead><tr><th>Teks</th><th>Actual</th><th>Pred</th><th>Conf</th></tr></thead>
          <tbody>${rows.join("") || '<tr><td colspan="4" class="text-muted small">Tidak ada.</td></tr>'}</tbody>
        </table>
      </div>`;
  }

  function renderTopTerms(topTerms) {
    if (!topTermsContainer || !topTerms) return;
    const entries = Object.entries(topTerms);
    const colClass = entries.length === 2 ? "col-md-6" : entries.length === 3 ? "col-md-4" : "col-md-4";
    const sections = entries.map(([label, terms]) => {
      const rows = (terms || []).slice(0, 20).map((t) => `<tr><td>${t.term}</td><td>${t.score.toFixed?.(3) ?? t.score}</td></tr>`).join("");
      return `<div class="${colClass}"><div class="fw-semibold mb-1">${label}</div>
        <div class="table-responsive">
          <table class="table table-sm table-bordered mb-2">
            <thead><tr><th>Term</th><th>Score</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
    });
    topTermsContainer.innerHTML = `<div class="fw-semibold mb-1">Top terms per class</div><div class="row g-2">${sections.join("")}</div>`;
  }

  function renderResult(data) {
    if (!data) return;
    resultCard?.classList.remove("d-none");
    modeBadge.textContent = data.mode === "3way" ? "3 dataset (Train/Val/Test)" : "2 dataset (Train/Test)";
    renderDatasetSummary(data.dataset_summary);
    renderMetrics(data.results);
    renderReport(data.results?.test?.report);
    renderConfusion(data.results?.test?.confusion_matrix, data.labels || []);
    renderMisclassified(data.results?.misclassified);
    renderTopTerms(data.results?.top_terms);
    renderDownloads(data.artifacts);
  }

  function renderDownloads(artifacts) {
    if (!downloadsContainer) return;
    if (!artifacts) {
      downloadsContainer.innerHTML = "";
      return;
    }
    const links = [];
    if (artifacts.test_predictions_full) {
      links.push(`<a class="btn btn-outline-primary btn-sm" href="/naive-bayes/download/${artifacts.test_predictions_full}">Full Test Predictions (CSV)</a>`);
    }
    if (artifacts.val_predictions_full) {
      links.push(`<a class="btn btn-outline-secondary btn-sm" href="/naive-bayes/download/${artifacts.val_predictions_full}">Full Val Predictions (CSV)</a>`);
    }
    if (artifacts.misclassified_sample) {
      links.push(`<a class="btn btn-outline-warning btn-sm" href="/naive-bayes/download/${artifacts.misclassified_sample}">Misclassified Sample (debug)</a>`);
    }
    if (artifacts.zip) {
      links.push(`<a class="btn btn-success btn-sm" href="/naive-bayes/download/${artifacts.zip}">Download Zip</a>`);
    }
    downloadsContainer.innerHTML = links.join(" ");
  }

  async function submitForm() {
    if (!form) return;
    const ok = validateForm(true);
    if (!ok) return;
    const fd = new FormData(form);
    if (startBtn) {
      startBtn.disabled = true;
      startBtn.textContent = "Memproses...";
    }
    try {
      const res = await fetch("/naive-bayes/train", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        log(data.message || "Gagal melatih Naive Bayes.");
        showWarning([data.message || "Gagal melatih Naive Bayes."]);
        return;
      }
      showWarning([]);
      renderResult(data);
      log("Training selesai.");
    } catch (err) {
      log("Gagal memproses permintaan.");
    } finally {
      if (startBtn) {
        startBtn.disabled = false;
        startBtn.textContent = "Train Naive Bayes";
      }
    }
  }

  if (form) {
    startBtn.disabled = true;
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      submitForm();
    });
    if (trainInput) {
      trainInput.addEventListener("change", () => {
        const f = trainInput.files?.[0];
        if (f) readTrainHeader(f);
        validateForm();
      });
    }
    if (testInput) testInput.addEventListener("change", () => validateForm());
    if (valInput) valInput.addEventListener("change", () => validateForm());
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
