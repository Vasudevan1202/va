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
            borderColor: "#51D8FF",
            backgroundColor: "rgba(81, 216, 255, 0.08)",
            borderWidth: 2,
            yAxisID: "yTemp",
            tension: 0.3,
            fill: false,
            pointRadius: 1
          },
          {
            label: "Pressure (hPa)",
            data: [],
            borderColor: "#1677FF",
            backgroundColor: "rgba(22, 119, 255, 0.08)",
            borderWidth: 2,
            yAxisID: "yPress",
            tension: 0.3,
            fill: false,
            pointRadius: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            display: true,
            labels: { color: "#FFFFFF", font: { size: 12 } }
          },
          tooltip: {
            backgroundColor: "rgba(16, 38, 58, 0.95)",
            titleColor: "#51D8FF",
            borderColor: "#243B50",
            borderWidth: 1,
            padding: 10
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(36, 59, 80, 0.4)" },
            ticks: { color: "#91A9BF", maxTicksLimit: 10 }
          },
          yTemp: {
            type: "linear",
            position: "left",
            title: { display: true, text: "Temperature (°C)", color: "#51D8FF" },
            grid: { color: "rgba(36, 59, 80, 0.4)" },
            ticks: { color: "#51D8FF" }
          },
          yPress: {
            type: "linear",
            position: "right",
            title: { display: true, text: "Pressure (hPa)", color: "#1677FF" },
            grid: { drawOnChartArea: false },
            ticks: { color: "#1677FF" }
          }
        }
      }
    });
  }

  function loadChartData() {
    let url = `/api/readings?range=${currentRangePreset}`;
    const presetGroup = document.getElementById("historyPresetGroup");
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

        const labels = readings.map(r => {
          const d = new Date(r.timestamp);
          return d.toLocaleDateString([], { month: "numeric", day: "numeric" }) + " " +
                 d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
        });

        const temps = readings.map(r => r.temperature_c);
        const pressures = readings.map(r => r.pressure_hpa);

        if (historyChart) {
          historyChart.data.labels = labels;
          historyChart.data.datasets[0].data = temps;
          historyChart.data.datasets[1].data = pressures;
          historyChart.update();
        }

        // Update statistics cards
        document.getElementById("statSampleCount").textContent = summary.count || 0;
        if (summary.temp_min !== null && summary.temp_max !== null) {
          document.getElementById("statTempRange").textContent = `${summary.temp_min}° / ${summary.temp_max}°`;
          document.getElementById("statTempAvg").textContent = `Avg: ${summary.temp_avg}°C`;
        } else {
          document.getElementById("statTempRange").textContent = "-- / --";
          document.getElementById("statTempAvg").textContent = "Avg: --";
        }

        if (summary.press_min !== null && summary.press_max !== null) {
          document.getElementById("statPressRange").textContent = `${summary.press_min} / ${summary.press_max}`;
          document.getElementById("statPressAvg").textContent = `Avg: ${summary.press_avg} hPa`;
        } else {
          document.getElementById("statPressRange").textContent = "-- / --";
          document.getElementById("statPressAvg").textContent = "Avg: --";
        }
      })
      .catch(err => {
        console.error("Error loading historical chart:", err);
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
          tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-secondary">No records found matching query criteria.</td></tr>`;
          return;
        }

        tbody.innerHTML = readings.map(r => `
          <tr>
            <td>#${r.id}</td>
            <td>${new Date(r.timestamp).toLocaleString()}</td>
            <td class="text-cyan fw-bold">${r.temperature_c.toFixed(2)}</td>
            <td class="text-white fw-semibold">${r.pressure_hpa.toFixed(2)}</td>
            <td><span class="badge-tag ${r.source}">${r.source}</span></td>
            <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
          </tr>
        `).join("");

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
