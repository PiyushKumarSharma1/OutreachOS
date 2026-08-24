window.addEventListener('DOMContentLoaded', () => {
  const node = document.getElementById('chart-data');
  const funnelCanvas = document.getElementById('funnelChart');
  const stateCanvas = document.getElementById('stateChart');
  if (!node || typeof Chart === 'undefined') return;

  const data = JSON.parse(node.textContent);

  // Funnel - horizontal bar
  new Chart(funnelCanvas, {
    type: 'bar',
    data: {
      labels: data.funnel_labels,
      datasets: [{
        data: data.funnel_values,
        backgroundColor: (ctx) => {
          const grad = ctx.chart.ctx.createLinearGradient(0, 0, 400, 0);
          grad.addColorStop(0, '#3b5bdb');
          grad.addColorStop(1, '#5a7cff');
          return grad;
        },
        borderRadius: 6,
        barThickness: 28,
        maxBarThickness: 32,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { right: 16 } },
      plugins: {
        legend: { display: false },
        title: { display: true, text: 'Pipeline Funnel', color: '#57534e', font: { size: 13, weight: '600' }, padding: { bottom: 16 } },
        tooltip: {
          backgroundColor: '#1c1b1a', titleColor: '#fafafa', bodyColor: '#fafafa',
          borderColor: '#d6d3cd', borderWidth: 1, padding: 12, cornerRadius: 8,
          displayColors: false,
        }
      },
      scales: {
        x: { grid: { color: 'rgba(28,27,26,0.04)' }, ticks: { color: '#57534e', precision: 0, font: { size: 11 } } },
        y: { grid: { display: false }, ticks: { color: '#57534e', font: { size: 12 } } },
      },
      animation: { duration: 900, easing: 'easeOutCubic' },
    },
  });

  // Outreach States - doughnut
  new Chart(stateCanvas, {
    type: 'doughnut',
    data: {
      labels: data.state_labels,
      datasets: [{
        data: data.state_values,
        backgroundColor: ['#059669','#dc2626','#3b5bdb','#d97706','#6366f1','#a78bfa','#64748b','#f0abfc'],
        borderColor: '#ffffff',
        borderWidth: 3,
        hoverOffset: 8,
        hoverBorderWidth: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '66%',
      plugins: {
        legend: { position: 'right', labels: { color: '#57534e', boxWidth: 10, padding: 16, font: { size: 11, weight: '500' }, usePointStyle: true, pointStyle: 'circle' } },
        title: { display: true, text: 'Outreach States', color: '#57534e', font: { size: 13, weight: '600' }, padding: { bottom: 16 } },
        tooltip: {
          backgroundColor: '#1c1b1a', titleColor: '#fafafa', bodyColor: '#fafafa',
          borderColor: '#d6d3cd', borderWidth: 1, padding: 12, cornerRadius: 8,
          displayColors: true,
        }
      },
      animation: { animateRotate: true, animateScale: true, duration: 900, easing: 'easeOutCubic' },
    },
  });
});