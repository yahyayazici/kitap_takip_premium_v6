/* Etüt gelişim çizgisi — beyaz zemin, ışıltılı ince çizgi */
window.csLuminousLine = function (canvas, labels, values) {
  if (!canvas || !labels || !labels.length || typeof Chart === "undefined") return;
  const stroke = (c) => {
    const area = c.chart.chartArea;
    if (!area) return "#3ee0ff";
    const g = c.chart.ctx.createLinearGradient(area.left, 0, area.right, 0);
    g.addColorStop(0, "#3ee0ff");
    g.addColorStop(0.22, "#2f6ff3");
    g.addColorStop(0.46, "#1ed4a8");
    g.addColorStop(0.7, "#7eb6ff");
    g.addColorStop(1, "#3ee0ff");
    return g;
  };
  new Chart(canvas, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        data: values,
        borderColor: stroke,
        backgroundColor: (c) => {
          const area = c.chart.chartArea;
          if (!area) return "rgba(62,224,255,.08)";
          const g = c.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
          g.addColorStop(0, "rgba(62,224,255,.20)");
          g.addColorStop(1, "rgba(62,224,255,0)");
          return g;
        },
        tension: 0.42,
        fill: true,
        borderWidth: 1.25,
        pointRadius: 1.75,
        pointHoverRadius: 3.5,
        pointBackgroundColor: "#ffffff",
        pointBorderColor: "#3ee0ff",
        pointBorderWidth: 1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 28 } },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: "#15427f", font: { family: "Poppins", size: 13, weight: "600" } },
          grid: { display: false },
          border: { display: false },
        },
        y: { display: false, min: 0, max: 500, grid: { display: false }, border: { display: false } },
      },
    },
    plugins: [{
      id: "ledGlow",
      beforeDatasetsDraw(chart) {
        const meta = chart.getDatasetMeta(0);
        const line = meta.dataset;
        if (!line) return;
        const c = chart.ctx;
        const prevW = line.options.borderWidth;
        const prevC = line.options.borderColor;
        const halos = [
          ["rgba(62, 224, 255, .95)", 16],
          ["rgba(47, 111, 243, .8)", 12],
          ["rgba(30, 212, 168, .75)", 10],
        ];
        halos.forEach(([color, blur]) => {
          c.save();
          c.shadowColor = color;
          c.shadowBlur = blur;
          line.options.borderWidth = 1.25;
          line.options.borderColor = color;
          line.draw(c);
          c.restore();
        });
        line.options.borderWidth = prevW;
        line.options.borderColor = prevC;
      },
      afterDatasetsDraw(chart) {
        const area = chart.chartArea;
        const c = chart.ctx;
        const g = c.createLinearGradient(area.left, 0, area.right, 0);
        g.addColorStop(0, "#3ee0ff");
        g.addColorStop(0.35, "#2f6ff3");
        g.addColorStop(0.7, "#1ed4a8");
        g.addColorStop(1, "#7eb6ff");
        c.save();
        c.shadowColor = "rgba(62, 224, 255, .85)";
        c.shadowBlur = 6;
        c.strokeStyle = g;
        c.lineWidth = 1;
        c.beginPath();
        c.moveTo(area.left, area.bottom);
        c.lineTo(area.right, area.bottom);
        c.stroke();
        c.restore();
      },
    }, {
      id: "puanUstte",
      afterDatasetsDraw(chart) {
        const c = chart.ctx;
        const meta = chart.getDatasetMeta(0);
        c.save();
        c.fillStyle = "#15427f";
        c.font = "500 13px Poppins, sans-serif";
        c.textAlign = "center";
        meta.data.forEach((pt, i) => {
          const v = values[i];
          if (v == null) return;
          c.fillText(String(v).replace(".", ","), pt.x, pt.y - 10);
        });
        c.restore();
      },
    }],
  });
};

window.csNavyLine = function (canvas, values, dates) {
  if (!canvas || !values || !values.length || typeof Chart === "undefined") return;
  const nums = values.filter((v) => v != null);
  const lo = Math.min.apply(null, nums);
  const hi = Math.max.apply(null, nums);
  const pad = Math.max(16, (hi - lo) * 0.45);
  const min = Math.max(0, Math.floor((lo - pad) / 10) * 10);
  const max = Math.min(500, Math.ceil((hi + pad) / 10) * 10);
  const labels = values.map((_, i) => String(i + 1));
  const last = values.length - 1;
  new Chart(canvas, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        data: values,
        borderColor: "#ffffff",
        tension: 0.08,
        fill: false,
        borderWidth: 1.75,
        pointRadius: (c) => (c.dataIndex === last ? 5 : 3),
        pointHoverRadius: 6,
        pointBackgroundColor: (c) => (c.dataIndex === last ? "#e0c27a" : "#ffffff"),
        pointBorderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", axis: "x", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          intersect: false,
          displayColors: false,
          backgroundColor: "rgba(16, 32, 58, .78)",
          borderColor: "rgba(255,255,255,.14)",
          borderWidth: 1,
          cornerRadius: 12,
          padding: 12,
          titleColor: "rgba(240,244,252,.72)",
          titleFont: { family: "Poppins", size: 12, weight: "500" },
          bodyColor: "#ffffff",
          bodyFont: { family: "MontBlanc, Georgia, serif", size: 22, weight: "800" },
          callbacks: {
            title: (items) => {
              const i = items[0] ? items[0].dataIndex : 0;
              const ay = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
              const iso = (dates || [])[i] || "";
              let when = "";
              if (iso) {
                const p = iso.split("-");
                when = ", " + Number(p[2]) + " " + ay[Number(p[1]) - 1] + " " + p[0];
              }
              return (i + 1) + ". Deneme" + when;
            },
            label: (item) => {
              const v = item.parsed.y;
              if (v == null) return "";
              const n = Math.round(v * 10) / 10;
              return Number.isInteger(n) ? String(n) : String(n).replace(".", ",");
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "rgba(240,244,252,.62)", font: { family: "Poppins", size: 12 } },
          grid: { display: false },
          border: { display: false },
        },
        y: {
          position: "right",
          min: min,
          max: max,
          ticks: { color: "rgba(240,244,252,.45)", font: { family: "Poppins", size: 11 }, maxTicksLimit: 5 },
          grid: { color: "rgba(240,244,252,.22)", borderDash: [3, 5] },
          border: { display: false },
        },
      },
    },
    plugins: [{
      id: "hoverStem",
      afterDatasetsDraw(chart) {
        const active = chart.getActiveElements();
        if (!active.length) return;
        const pt = active[0].element;
        const { bottom } = chart.chartArea;
        const c = chart.ctx;
        c.save();
        c.strokeStyle = "rgba(255,255,255,.7)";
        c.lineWidth = 1;
        c.beginPath();
        c.moveTo(pt.x, pt.y + 8);
        c.lineTo(pt.x, bottom);
        c.stroke();
        c.restore();
      },
    }],
  });
};
