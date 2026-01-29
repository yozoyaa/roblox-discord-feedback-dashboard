(() => {
  const form = document.getElementById("tfidfForm");
  const startBtn = document.getElementById("startBtn");
  const modePreset = document.getElementById("modePreset");
  const modeManual = document.getElementById("modeManual");

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

  if (modePreset) modePreset.addEventListener("change", onModeChange);
  if (modeManual) modeManual.addEventListener("change", onModeChange);

  if (form) {
    form.addEventListener("submit", () => {
      if (startBtn) {
        startBtn.disabled = true;
        startBtn.textContent = "Memproses...";
      }
    });
  }
})(); 
