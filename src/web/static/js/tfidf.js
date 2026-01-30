(() => {
  const form = document.getElementById("tfidfForm");
  const startBtn = document.getElementById("startBtn");
  const modePreset = document.getElementById("modePreset");
  const modeManual = document.getElementById("modeManual");
  const textColHidden = document.getElementById("text_col");
  const labelColHidden = document.getElementById("label_col");
  const textColDisplay = document.getElementById("textColDisplay");
  const labelColDisplay = document.getElementById("labelColDisplay");
  const textColSelect = document.getElementById("textColSelect");
  const labelColSelect = document.getElementById("labelColSelect");
  const trainInput = form?.querySelector('input[name="train_file"]');
  const testInput = form?.querySelector('input[name="test_file"]');
  const warningBox = document.getElementById("tfidfWarning");

  let trainHeaders = [];

  function setPresetDefaults() {
    const ngramMin = form?.querySelector('input[name="ngram_min"]');
    const ngramMax = form?.querySelector('input[name="ngram_max"]');
    const maxFeat = form?.querySelector('input[name="max_features"]');
    const minDf = form?.querySelector('input[name="min_df"]');
    const maxDf = form?.querySelector('input[name="max_df"]');
    const sublinear = form?.querySelector('input[name="sublinear_tf"]');
    if (ngramMin) ngramMin.value = "1";
    if (ngramMax) ngramMax.value = "2";
    if (maxFeat) maxFeat.value = "5000";
    if (minDf) minDf.value = "2";
    if (maxDf) maxDf.value = "0.8";
    if (sublinear) sublinear.checked = true;
  }

  function onModeChange() {
    if (modePreset?.checked) {
      setPresetDefaults();
    }
  }

  function updateDisplays() {
    if (textColDisplay && textColHidden) {
      textColDisplay.textContent = textColHidden.value || "-";
    }
    if (labelColDisplay && labelColHidden) {
      labelColDisplay.textContent = labelColHidden.value || "-";
    }
  }

  function chooseTextCol(headers) {
    const priorities = ["tokens_stemmed", "tokens_no_stopwords", "text_clean"];
    const hit = priorities.find((p) => headers.includes(p));
    return hit || headers[0] || "";
  }

  function chooseLabelCol(headers) {
    const lowerMap = headers.map((h) => h.toLowerCase());
    const priorities = ["sentimen", "label"];
    for (const target of priorities) {
      const idx = lowerMap.indexOf(target);
      if (idx !== -1) return headers[idx];
    }
    const fuzzy = headers.find((h) => /label|sentimen/i.test(h));
    return fuzzy || headers[0] || "";
  }

  function populateSelect(selectEl, headers, selected) {
    if (!selectEl) return;
    const placeholder = '<option value="">Pilih kolom</option>';
    selectEl.innerHTML = placeholder + headers.map((h) => `<option value="${h}">${h}</option>`).join("");
    if (selected) {
      selectEl.value = selected;
    }
  }

  function setColumns(textCol, labelCol) {
    if (textColHidden) textColHidden.value = textCol;
    if (labelColHidden) labelColHidden.value = labelCol;
    updateDisplays();
  }

  function handleHeaders(headers) {
    trainHeaders = headers;
    const textCol = chooseTextCol(headers);
    const labelCol = chooseLabelCol(headers);
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
      const headers = headerLine
        .split(",")
        .map((h) => h.trim())
        .filter((h) => h.length > 0);
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
    const messages = [];
    const infoMessages = [];
    const hasTrain = Boolean(trainInput?.files?.length);
    const hasTest = Boolean(testInput?.files?.length);
    if (!hasTrain) {
      messages.push("Upload Train data terlebih dahulu.");
    }
    if (!hasTest) {
      messages.push("Upload Test data terlebih dahulu.");
    }
    if (trainHeaders.length === 0) {
      messages.push("Header Train belum terbaca.");
    }
    const textCol = textColHidden?.value || "";
    const labelCol = labelColHidden?.value || "";
    if (trainHeaders.length > 0) {
      if (!trainHeaders.includes(textCol)) {
        messages.push(`Kolom teks "${textCol || "(kosong)"}" tidak ditemukan di header Train.`);
      }
      if (!trainHeaders.includes(labelCol)) {
        messages.push(`Kolom label "${labelCol || "(kosong)"}" tidak ditemukan di header Train.`);
      }
    }
    if (labelCol && labelCol.toLowerCase() !== "sentimen") {
      infoMessages.push('Kolom label bukan "sentimen". Pastikan nilainya hanya positif/negatif.');
    }

    const isValid = messages.length === 0;
    if (startBtn) startBtn.disabled = !isValid;
    const combined = [...messages, ...infoMessages];
    if (showMessage) {
      showWarning(combined);
    } else if (infoMessages.length > 0) {
      showWarning(combined);
    } else if (warningBox) {
      warningBox.classList.add("d-none");
      warningBox.textContent = "";
    }
    return isValid;
  }

  if (modePreset) modePreset.addEventListener("change", onModeChange);
  if (modeManual) modeManual.addEventListener("change", onModeChange);

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
        const val = textColSelect.value || textColHidden?.value;
        setColumns(val, labelColHidden?.value || "");
        validateForm();
      });
    }

    if (labelColSelect) {
      labelColSelect.addEventListener("change", () => {
        const val = labelColSelect.value || labelColHidden?.value;
        setColumns(textColHidden?.value || "", val);
        validateForm();
      });
    }

    updateDisplays();
    validateForm();

    form.addEventListener("submit", (e) => {
      const ok = validateForm(true);
      if (!ok) {
        e.preventDefault();
        return;
      }
      if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = "Memproses...";
      }
    });
  }
})(); 
