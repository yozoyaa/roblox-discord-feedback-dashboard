(() => {
  const selectEl = document.getElementById("evalSelect");
  const selectedInfo = document.getElementById("selectedInfo");
  const statRaw = document.getElementById("statRaw");
  const statProcessed = document.getElementById("statProcessed");
  const statVocab = document.getElementById("statVocab");
  const statAccuracy = document.getElementById("statAccuracy");
  const statMacroF1 = document.getElementById("statMacroF1");
  const statEvaluated = document.getElementById("statEvaluated");
  const confTable = document.getElementById("confTable");
  const chartTrueEl = document.getElementById("chartTrue");
  const chartPredEl = document.getElementById("chartPred");

  let chartTrue = null;
  let chartPred = null;

  function destroyCharts() {
    if (chartTrue) chartTrue.destroy();
    if (chartPred) chartPred.destroy();
    chartTrue = null;
    chartPred = null;
  }

  function renderEmpty() {
    if (statRaw) statRaw.textContent = "0";
    if (statProcessed) statProcessed.textContent = "0";
    if (statVocab) statVocab.textContent = "-";
    if (statAccuracy) statAccuracy.textContent = "-";
    if (statMacroF1) statMacroF1.textContent = "-";
    if (statEvaluated) statEvaluated.textContent = "0";
    if (selectedInfo) selectedInfo.textContent = "Selected: None";
    destroyCharts();
    if (chartTrueEl) chartTrueEl.replaceChildren();
    if (chartPredEl) chartPredEl.replaceChildren();
    if (confTable) {
      const body = confTable.querySelector("tbody");
      if (body) {
        body.innerHTML = `<tr><th>negatif</th><td>-</td><td>-</td></tr><tr><th>positif</th><td>-</td><td>-</td></tr>`;
      }
    }
  }

  function renderConfusion(cm) {
    if (!confTable) return;
    const body = confTable.querySelector("tbody");
    if (!body) return;
    if (!Array.isArray(cm) || cm.length < 2) {
      body.innerHTML = `<tr><th>negatif</th><td>-</td><td>-</td></tr><tr><th>positif</th><td>-</td><td>-</td></tr>`;
      return;
    }
    const n0 = Array.isArray(cm[0]) ? cm[0] : [0, 0];
    const n1 = Array.isArray(cm[1]) ? cm[1] : [0, 0];
    body.innerHTML = `<tr><th>negatif</th><td>${n0[0] ?? 0}</td><td>${n0[1] ?? 0}</td></tr><tr><th>positif</th><td>${n1[0] ?? 0}</td><td>${n1[1] ?? 0}</td></tr>`;
  }

  function renderCharts(trueCounts, predCounts) {
    destroyCharts();
    if (!window.Chart) return;
    const trueData = [trueCounts.negatif || 0, trueCounts.positif || 0];
    const predData = [predCounts.negatif || 0, predCounts.positif || 0];
    const trueTotal = trueData[0] + trueData[1];
    const predTotal = predData[0] + predData[1];
    const safeTrue = trueTotal === 0 ? [1, 1] : trueData;
    const safePred = predTotal === 0 ? [1, 1] : predData;
    if (chartTrueEl) {
      chartTrue = new Chart(chartTrueEl, {
        type: "pie",
        data: { labels: ["Negatif", "Positif"], datasets: [{ data: safeTrue, backgroundColor: ["#dc3545", "#0d6efd"] }] },
        options: { plugins: { legend: { position: "bottom" } }, responsive: true },
      });
    }
    if (chartPredEl) {
      chartPred = new Chart(chartPredEl, {
        type: "pie",
        data: { labels: ["Negatif", "Positif"], datasets: [{ data: safePred, backgroundColor: ["#dc3545", "#0d6efd"] }] },
        options: { plugins: { legend: { position: "bottom" } }, responsive: true },
      });
    }
  }

  function renderFromSummary(data, filename) {
    const stats = data?.stats || {};
    const metrics = data?.metrics || {};
    const trueCounts = stats.true_label_counts || {};
    const predCounts = stats.pred_label_counts || {};
    if (statRaw) statRaw.textContent = stats.total_raw_data ?? 0;
    if (statProcessed) statProcessed.textContent = stats.total_preprocessed_data ?? 0;
    if (statVocab) statVocab.textContent = stats.vocab_size ?? "-";
    const accVal = metrics.accuracy !== null && metrics.accuracy !== undefined ? metrics.accuracy : null;
    if (statAccuracy) statAccuracy.textContent = accVal !== null ? (accVal * 100).toFixed(2) + "%" : "-";
    let macroF1 = metrics.macro_f1;
    if (macroF1 === undefined || macroF1 === null) {
      const rep = metrics.classification_report || {};
      macroF1 = rep["macro avg"]?.["f1-score"];
    }
    if (statMacroF1) statMacroF1.textContent = macroF1 !== undefined && macroF1 !== null ? Number(macroF1).toFixed(3) : "-";
    if (statEvaluated) statEvaluated.textContent = stats.total_rows_uploaded ?? stats.total_classified ?? 0;
    if (selectedInfo)
      selectedInfo.textContent = `Selected: ${filename || "None"} | created_at: ${data.created_at || "-"} | mode: ${data.mode || "-"}`;
    renderCharts(trueCounts, predCounts);
    renderConfusion(metrics.confusion_matrix);
  }

  async function fetchList() {
    try {
      const res = await fetch("/dashboard/evaluate/list");
      const data = await res.json();
      if (!res.ok || !data.ok) return;
      const items = data.items || [];
      if (selectEl) {
        selectEl.innerHTML = '<option value="">None (tidak tampilkan statistik)</option>';
        items.forEach((item) => {
          const opt = document.createElement("option");
          opt.value = item.filename;
          opt.textContent = `${item.filename} (${item.modified})`;
          selectEl.appendChild(opt);
        });
      }
    } catch (err) {
      // ignore
    }
  }

  async function loadSummary(filename) {
    if (!filename) {
      renderEmpty();
      return;
    }
    try {
      const res = await fetch(`/dashboard/evaluate/load/${encodeURIComponent(filename)}`);
      const data = await res.json();
      if (!res.ok || !data.ok) {
        renderEmpty();
        return;
      }
      renderFromSummary(data.data, filename);
    } catch (err) {
      renderEmpty();
    }
  }

  function init() {
    renderEmpty();
    fetchList();
    if (selectEl) {
      selectEl.addEventListener("change", () => {
        const val = selectEl.value;
        if (!val) renderEmpty();
        else loadSummary(val);
      });
    }
  }

  init();
})();
