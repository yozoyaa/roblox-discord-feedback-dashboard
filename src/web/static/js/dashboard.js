(() => {
  document.querySelectorAll(".progress-bar[data-pct]").forEach((el) => {
    const raw = (el.dataset.pct ?? "").toString().replace("%", "").replace(",", ".");
    const n = Number(raw);
    const pct = Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
    el.style.width = `${pct}%`;
    el.setAttribute("aria-valuenow", String(pct));
  });
})();
