// src/web/static/js/files.js

(function () {
  const checkAll = document.getElementById("checkAll");
  const rowChecks = Array.from(document.querySelectorAll(".rowCheck"));
  const btnDownload = document.getElementById("btnDownload");
  const btnDelete = document.getElementById("btnDelete");
  const selectedInfo = document.getElementById("selectedInfo");

  if (rowChecks.length === 0) return;

  function updateButtons() {
    const selectedCount = rowChecks.filter((c) => c.checked).length;
    if (selectedInfo) selectedInfo.textContent = `${selectedCount} selected`;
    if (btnDownload) btnDownload.disabled = selectedCount === 0;
    if (btnDelete) btnDelete.disabled = selectedCount === 0;
  }

  if (checkAll) {
    checkAll.addEventListener("change", () => {
      rowChecks.forEach((c) => (c.checked = checkAll.checked));
      updateButtons();
    });
  }

  rowChecks.forEach((c) =>
    c.addEventListener("change", () => {
      if (checkAll) checkAll.checked = rowChecks.every((x) => x.checked);
      updateButtons();
    })
  );

  updateButtons();
})();
