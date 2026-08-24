window.addEventListener("DOMContentLoaded", () => {
  const node = document.getElementById("chart-data");
  const funnelCanvas = document.getElementById("funnelChart");
  const stateCanvas = document.getElementById("stateChart");
  if (!node || typeof Chart === "undefined") return;
  const data = JSON.parse(node.textContent);

  const grad = funnelCanvas.getContext("2d").createLinearGradient(0, 0, 320, 0);
  grad.addColorStop(0, "#6366f1");
  grad.addColorStop(1, "#22d3ee");

  new Chart(funnelCanvas, {
    type: "bar",
    data: {
      labels: data.funnel_labels,
      datasets: [{
        data: data.funnel_values,
        backgroundColor: grad,
        borderRadius: 8,
        barThickness: 26,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, title: { display: true, text: "Pipeline Funnel", color: "#98a2b8", font: { size: 13 } } },
      scales: {
        x: { grid: { color: "rgba(255,255,255,.05)" }, ticks: { color: "#5b657c", precision: 0 } },
        y: { grid: { display: false }, ticks: { color: "#98a2b8" } },
      },
      animation: { duration: 900, easing: "easeOutQuart" },
    },
  });

  new Chart(stateCanvas, {
    type: "doughnut",
    data: {
      labels: data.state_labels,
      datasets: [{
        data: data.state_values,
        backgroundColor: ["#34d399","#fb7185","#22d3ee","#fbbf24","#6366f1","#a78bfa","#64748b","#f0abfc"],
        borderColor: "rgba(7,10,18,.9)",
        borderWidth: 3,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "62%",
      plugins: {
        legend: { position: "right", labels: { color: "#98a2b8", boxWidth: 10, font: { size: 11 } } },
        title: { display: true, text: "Outreach States", color: "#98a2b8", font: { size: 13 } },
      },
      animation: { animateRotate: true, duration: 900 },
    },
  });
});
