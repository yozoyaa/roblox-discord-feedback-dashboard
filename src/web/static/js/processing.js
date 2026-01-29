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

  let jobId = root?.dataset.jobId || "";
  let steps = [];
  let stepIndex = 0;
  let done = false;
  let saved = false;

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
        target.meta.textContent = `${total} rows · ${headers.length} kolom`;
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

  if (form) {
    form.addEventListener("submit", (e) => {
      if (jobId && !saved) {
        e.preventDefault();
        log("Selesaikan atau save job yang berjalan sebelum mulai baru.");
        alert("Simpan atau batalkan job yang sedang berjalan sebelum memulai job baru.");
        return;
      }
      if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = "Membuat job...";
      }
    });
  }

  // init
  if (jobId) {
    stepCard.style.display = "block";
    previewCard.style.display = "block";
    log("Job processing dibuat. Klik Next Step untuk mulai.");
    fetchState();
  }
  refreshButtons();
})(); 
