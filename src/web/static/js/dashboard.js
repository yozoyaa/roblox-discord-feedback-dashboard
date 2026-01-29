(() => {
  // sentiment pie
  const pieEl = document.getElementById("sentimentPie");
  if (pieEl && window.Chart) {
    const positif = Number(pieEl.dataset.positif || 0) || 0;
    const negatif = Number(pieEl.dataset.negatif || 0) || 0;
    const netral = Number(pieEl.dataset.netral || 0) || 0;
    const total = positif + negatif + netral;
    const data = total === 0 ? [1, 1, 1] : [positif, negatif, netral];
    new Chart(pieEl, {
      type: "pie",
      data: {
        labels: ["Positif", "Negatif", "Netral"],
        datasets: [
          {
            data,
            backgroundColor: ["#0d6efd", "#dc3545", "#6c757d"],
          },
        ],
      },
      options: { responsive: true, plugins: { legend: { position: "bottom" } } },
    });
  }
})();
