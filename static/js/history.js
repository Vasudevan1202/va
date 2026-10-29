/**
 * Virtual Atmosphere - Historical Data Explorer Controller
 */

(function () {
  "use strict";

  let historyChart = null;
  let currentPage = 1;
  let pageSize = 25;
  let currentRangePreset = "24h";
  let filterStart = "";
  let filterEnd = "";

  function initChart() {
    const ctx = document.getElementById("historyChart");
    if (!ctx) return;

    historyChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Temperature (°C)",
            data: [],
            borderColor: "#dc2626",
            backgroundColor: "rgba(220, 38, 38, 0.10)",
            borderWidth: 2.8,
            tension: 0.35,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: "#dc2626",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
            yAxisID: "yTemp"
          },
          {
            label: "Relative Humidity (%)",
            data: [],
            borderColor: "#0284c7",
            backgroundColor: "rgba(2, 132, 199, 0.08)",
            borderWidth: 2.8,
            tension: 0.35,
            fill: false,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: "#0284c7",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
            yAxisID: "yHum"
          },
          {
            label: "Heat Index (°C)",
            data: [],
            borderColor: "#ea580c",
            backgroundColor: "rgba(234, 88, 12, 0.05)",
            borderWidth: 2,
            borderDash: [5, 4],
            tension: 0.35,
            fill: false,
            pointRadius: 2.5,
            pointHoverRadius: 5,
            pointBackgroundColor: "#ea580c",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.2,
            yAxisID: "yTemp"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        layout: {
          padding: { top: 10, right: 14, bottom: 6, left: 6 }
        },
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: {
              color: "#1f1412",
              padding: 16,
              usePointStyle: true,
              font: { size: 13, family: "'Inter', sans-serif", weight: "700" }
            }
          },
          tooltip: {
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            titleColor: "#1f1412",
            bodyColor: "#5a463e",
            borderColor: "rgba(230, 210, 195, 0.95)",
            borderWidth: 1.5,
            padding: 12,
            boxPadding: 6,
            usePointStyle: true,
            titleFont: { size: 13, weight: "700", family: "'Inter', sans-serif" },
            bodyFont: { size: 13, weight: "600", family: "'Inter', sans-serif" },
            callbacks: {
              title: function (items) {
                return items.length ? "Timestamp: " + items[0].label : "";
              },
              label: function (ctx) {
                if (ctx.parsed.y === null || ctx.parsed.y === undefined) {
                  return `${ctx.dataset.label}: --`;
                }
                if (ctx.dataset.label.startsWith("Relative Humidity")) {
                  return `Relative Humidity: ${ctx.parsed.y.toFixed(1)}%`;
                }
                return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} °C`;
              }
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: "Time",
              color: "#5a463e",
              font: { size: 13, weight: "700", family: "'Inter', sans-serif" },
              padding: { top: 6 }
            },
            grid: { color: "rgba(225, 200, 180, 0.35)" },
            ticks: {
              color: "#5a463e",
              maxTicksLimit: 10,
              font: { size: 12, weight: "600", family: "'Inter', sans-serif" }
            }
          },
          yTemp: {
            type: "linear",
            position: "left",
            title: {
              display: true,
              text: "Temperature & Heat Index (°C)",
              color: "#dc2626",
              font: { size: 13, weight: "700", family: "'Inter', sans-serif" }
            },
            grid: { color: "rgba(225, 200, 180, 0.35)" },
            ticks: {
              color: "#dc2626",
              font: { size: 12, weight: "600", family: "'Inter', sans-serif" },
              callback: function (val) { return val + " °C"; }
            },
            suggestedMin: 15,
            suggestedMax: 45
          },
          yHum: {
            type: "linear",
            position: "right",
            title: {
              display: true,
              text: "Relative Humidity (%)",
              color: "#0284c7",
              font: { size: 13, weight: "700", family: "'Inter', sans-serif" }
            },
            grid: { drawOnChartArea: false },
            ticks: {
              color: "#0284c7",
              font: { size: 12, weight: "600", family: "'Inter', sans-serif" },
              callback: function (val) { return val + "%"; }
            },
            min: 0,
            max: 100
          }
        }
      }
    });

  }

  function loadChartData() {
    let url = `/api/readings?range=${currentRangePreset}`;
    const presetGroup = document.getElementById("historyPresetGroup");
    const emptyOverlay = document.getElementById("historyChartEmptyOverlay");
    if (presetGroup) {
      presetGroup.querySelectorAll("button").forEach(b => b.disabled = true);
    }

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(data => {
        const readings = data.readings || [];
        const summary = data.summary || {};

        if (readings.length === 0) {
          if (emptyOverlay) emptyOverlay.style.display = "flex";
        } else {
          if (emptyOverlay) emptyOverlay.style.display = "none";
        }

        const labels = readings.map(r => {
          const d = new Date(r.timestamp);
          return d.toLocaleDateString([], { month: "numeric", day: "numeric" }) + " " +
                 d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
        });

        const temps = readings.map(r => r.temperature_c);
        const hums = readings.map(r => r.humidity_pct);
        const heatIdx = readings.map(r => r.heat_index_c);

        if (historyChart) {
          historyChart.data.labels = labels;
          historyChart.data.datasets[0].data = temps;
          historyChart.data.datasets[1].data = hums;
          historyChart.data.datasets[2].data = heatIdx;
          historyChart.update();
        }

        // Update statistics cards
        const sampleCountElem = document.getElementById("statSampleCount");
        if (sampleCountElem) sampleCountElem.textContent = summary.count || 0;

        const statTempRange = document.getElementById("statTempRange");
        const statTempAvg = document.getElementById("statTempAvg");
        if (statTempRange && statTempAvg) {
          if (summary.temp_min !== null && summary.temp_max !== null) {
            statTempRange.textContent = `${summary.temp_min}° / ${summary.temp_max}°C`;
            statTempAvg.textContent = `Avg: ${summary.temp_avg}°C`;
          } else {
            statTempRange.textContent = "-- / -- °C";
            statTempAvg.textContent = "Avg: --";
          }
        }

        const statHumRange = document.getElementById("statHumRange");
        const statHumAvg = document.getElementById("statHumAvg");
        if (statHumRange && statHumAvg) {
          if (summary.hum_min !== null && summary.hum_max !== null) {
            statHumRange.textContent = `${summary.hum_min}% / ${summary.hum_max}%`;
            statHumAvg.textContent = `Avg: ${summary.hum_avg}%`;
          } else {
            statHumRange.textContent = "-- / -- %";
            statHumAvg.textContent = "Avg: --";
          }
        }

        const statPressRange = document.getElementById("statPressRange");
        const statPressAvg = document.getElementById("statPressAvg");
        if (statPressRange && statPressAvg) {
          if (summary.press_min !== null && summary.press_max !== null) {
            statPressRange.textContent = `${summary.press_min} / ${summary.press_max} hPa`;
            statPressAvg.textContent = `Avg: ${summary.press_avg} hPa`;
          } else {
            statPressRange.textContent = "-- / -- hPa";
            statPressAvg.textContent = "Avg: --";
          }
        }
      })
      .catch(err => {
        console.error("Error loading historical chart:", err);
        if (emptyOverlay) emptyOverlay.style.display = "flex";
      })
      .finally(() => {
        if (presetGroup) {
          presetGroup.querySelectorAll("button").forEach(b => b.disabled = false);
        }
      });
  }

  function loadHistoryTable() {
    let url = `/api/readings/history?page=${currentPage}&limit=${pageSize}`;
    if (filterStart) url += `&start=${encodeURIComponent(filterStart)}`;
    if (filterEnd) url += `&end=${encodeURIComponent(filterEnd)}`;

    const prevBtn = document.getElementById("btnPrevPage");
    const nextBtn = document.getElementById("btnNextPage");
    const summary = document.getElementById("historyTableSummary");
    if (prevBtn) prevBtn.disabled = true;
    if (nextBtn) nextBtn.disabled = true;
    if (summary) {
      summary.innerHTML = `<span class="va-spinner va-spinner-sm me-1" aria-hidden="true"></span> Fetching records…`;
    }

    fetch(url)
      .then(r => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(data => {
        const tbody = document.getElementById("historyTbody");
        const pageInd = document.getElementById("pageIndicator");

        const readings = data.readings || [];
        if (summary) summary.textContent = `Showing ${readings.length} of ${data.total} records`;
        if (pageInd) pageInd.textContent = `Page ${data.page} of ${data.total_pages}`;
        if (window.VA && window.VA.announce) {
          window.VA.announce(`Loaded page ${data.page} of ${data.total_pages}, ${readings.length} records`);
        }

        if (prevBtn) prevBtn.disabled = !data.has_prev;
        if (nextBtn) nextBtn.disabled = !data.has_next;

        if (readings.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-secondary">No records found matching query criteria.</td></tr>`;
          return;
        }

        tbody.innerHTML = readings.map(r => {
          const humStr = (r.humidity_pct !== null && r.humidity_pct !== undefined) ? `${r.humidity_pct.toFixed(1)}%` : '<span class="text-secondary">–</span>';
          const hiStr = (r.heat_index_c !== null && r.heat_index_c !== undefined) ? `${r.heat_index_c.toFixed(1)}°` : '<span class="text-secondary">–</span>';
          const pressStr = (r.pressure_hpa !== null && r.pressure_hpa !== undefined) ? `${r.pressure_hpa.toFixed(2)} hPa` : '<span class="text-secondary">–</span>';
          return `
            <tr>
              <td>#${r.id}</td>
              <td>${new Date(r.timestamp).toLocaleString()}</td>
              <td class="text-cyan fw-bold">${r.temperature_c.toFixed(2)}</td>
              <td class="text-white">${humStr}</td>
              <td class="text-white fw-semibold">${pressStr}</td>
              <td>${hiStr}</td>
              <td><span class="badge-tag ${r.source}">${r.source}</span></td>
              <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
            </tr>
          `;
        }).join("");

        // Update CSV Export link
        updateExportLink();
      })
      .catch(err => {
        console.error("History table error:", err);
        const tbody = document.getElementById("historyTbody");
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-danger">Error retrieving table records. Please retry.</td></tr>`;
        }
        if (summary) summary.textContent = "Error querying records";
        if (prevBtn) prevBtn.disabled = currentPage <= 1;
        if (nextBtn) nextBtn.disabled = false;
      });
  }

  function updateExportLink() {
    const btn = document.getElementById("btnHistoryExportCSV");
    if (!btn) return;
    let url = "/api/readings/export.csv?";
    if (filterStart || filterEnd) {
      if (filterStart) url += `start=${encodeURIComponent(filterStart)}&`;
      if (filterEnd) url += `end=${encodeURIComponent(filterEnd)}&`;
      url += "range=all";
    } else {
      url += `range=${currentRangePreset}`;
    }
    btn.setAttribute("href", url);

    // Attach click feedback once
    if (!btn.dataset.feedbackAttached) {
      btn.dataset.feedbackAttached = "true";
      btn.addEventListener("click", function () {
        const origHtml = this.innerHTML;
        this.innerHTML = `<span class="va-spinner va-spinner-sm me-1" aria-hidden="true"></span> Preparing CSV…`;
        if (window.VA && window.VA.announce) {
          window.VA.announce("Preparing CSV export download");
        }
        setTimeout(() => {
          this.innerHTML = origHtml;
        }, 1800);
      });
    }
  }

  function setupFilters() {
    // Preset buttons
    const presetGroup = document.getElementById("historyPresetGroup");
    if (presetGroup) {
      presetGroup.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", function () {
          presetGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
          this.classList.add("active");
          currentRangePreset = this.getAttribute("data-range");
          filterStart = "";
          filterEnd = "";
          document.getElementById("filterStartDate").value = "";
          document.getElementById("filterEndDate").value = "";
          currentPage = 1;
          loadChartData();
          loadHistoryTable();
        });
      });
    }

    // Custom date filter form
    const form = document.getElementById("historyFilterForm");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const startVal = document.getElementById("filterStartDate").value;
        const endVal = document.getElementById("filterEndDate").value;

        if (startVal) filterStart = new Date(startVal).toISOString();
        if (endVal) filterEnd = new Date(endVal).toISOString();

        if (presetGroup) {
          presetGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
        }

        currentPage = 1;
        loadHistoryTable();
      });
    }

    // Reset button
    const resetBtn = document.getElementById("btnResetFilter");
    if (resetBtn) {
      resetBtn.addEventListener("click", function () {
        document.getElementById("filterStartDate").value = "";
        document.getElementById("filterEndDate").value = "";
        filterStart = "";
        filterEnd = "";
        currentRangePreset = "24h";
        if (presetGroup) {
          presetGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
          const btn24 = presetGroup.querySelector('[data-range="24h"]');
          if (btn24) btn24.classList.add("active");
        }
        currentPage = 1;
        loadChartData();
        loadHistoryTable();
      });
    }

    // Page size select
    const pageSizeSelect = document.getElementById("pageSizeSelect");
    if (pageSizeSelect) {
      pageSizeSelect.addEventListener("change", function () {
        pageSize = parseInt(this.value);
        currentPage = 1;
        loadHistoryTable();
      });
    }

    // Pagination buttons
    document.getElementById("btnPrevPage").addEventListener("click", function () {
      if (currentPage > 1) {
        currentPage--;
        loadHistoryTable();
      }
    });

    document.getElementById("btnNextPage").addEventListener("click", function () {
      currentPage++;
      loadHistoryTable();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initChart();
    setupFilters();
    loadChartData();
    loadHistoryTable();
  });
})();
