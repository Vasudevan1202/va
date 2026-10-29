/**
 * Virtual Atmosphere - Historical Data Explorer Controller
 * Manages 4 Separated Historical Charts with Presets (1h-30d) and Custom Date Filtering
 */

(function () {
  "use strict";

  let histTempChart = null;
  let histHumChart = null;
  let histHeatChart = null;
  let histPressChart = null;

  let currentPage = 1;
  let pageSize = 25;
  let currentRangePreset = "24h";
  let filterStart = "";
  let filterEnd = "";
  let currentThresholdC = 35.0;

  /**
   * Initializes the 4 separated historical charts.
   */
  function initCharts() {
    if (!window.VACharts) {
      console.error("VACharts library not loaded.");
      return;
    }

    // 1. Ambient Temperature History Chart (id="historyChart" matches test suite)
    const tempCanvas = document.getElementById("historyChart");
    if (tempCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "temp",
        label: "Temperature History",
        unit: "°C",
        suggestedMin: 15,
        suggestedMax: 45,
        thresholdVal: currentThresholdC
      });
      histTempChart = new Chart(tempCanvas, cfg);
    }

    // 2. Relative Humidity History Chart
    const humCanvas = document.getElementById("historyHumChart");
    if (humCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "hum",
        label: "Humidity History",
        unit: "%",
        yMin: 0,
        yMax: 100
      });
      histHumChart = new Chart(humCanvas, cfg);
    }

    // 3. Calculated Heat Index History Chart
    const heatCanvas = document.getElementById("historyHeatChart");
    if (heatCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "heat",
        label: "Heat Index History",
        unit: "°C",
        suggestedMin: 20,
        suggestedMax: 50
      });
      histHeatChart = new Chart(heatCanvas, cfg);
    }

    // 4. Atmospheric Pressure History Chart
    const pressCanvas = document.getElementById("historyPressChart");
    if (pressCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "press",
        label: "Pressure History",
        unit: "hPa",
        suggestedMin: 980,
        suggestedMax: 1035
      });
      histPressChart = new Chart(pressCanvas, cfg);
    }
  }

  /**
   * Loads chronological readings for active range/custom dates and updates all 4 charts.
   */
  function loadChartData() {
    let url = "/api/readings?";
    if (filterStart || filterEnd) {
      if (filterStart) url += `start=${encodeURIComponent(filterStart)}&`;
      if (filterEnd) url += `end=${encodeURIComponent(filterEnd)}&`;
      url += "range=custom";
    } else {
      url += `range=${encodeURIComponent(currentRangePreset)}`;
    }

    const presetGroup = document.getElementById("historyPresetGroup");
    const tempOverlay = document.getElementById("historyChartEmptyOverlay");
    const humOverlay = document.getElementById("historyHumEmptyOverlay");
    const heatOverlay = document.getElementById("historyHeatEmptyOverlay");
    const pressOverlay = document.getElementById("historyPressEmptyOverlay");

    if (presetGroup) {
      presetGroup.querySelectorAll("button").forEach((b) => (b.disabled = true));
    }

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((data) => {
        const readings = data.readings || [];
        const summary = data.summary || {};
        const totalCount = data.total_count || readings.length;
        const activeRange = summary.range || currentRangePreset;

        if (summary.threshold_c !== undefined) {
          currentThresholdC = Number(summary.threshold_c);
        }

        // Update range label
        const rangeLabel = document.getElementById("chartRangeLabel");
        if (rangeLabel) {
          if (totalCount === 0) {
            rangeLabel.textContent = `No records found in range • Awaiting sensor telemetry`;
          } else {
            const downsampledNotice = data.is_downsampled ? ` (${readings.length} peak points)` : "";
            rangeLabel.textContent = `Showing ${totalCount} valid records${downsampledNotice} • Downsampled with peak preservation`;
          }
        }

        if (totalCount === 0 || readings.length === 0) {
          if (tempOverlay) tempOverlay.style.display = "flex";
          if (humOverlay) humOverlay.classList.remove("d-none");
          if (heatOverlay) heatOverlay.classList.remove("d-none");
          if (pressOverlay) pressOverlay.classList.remove("d-none");

          if (histTempChart) window.VACharts.updateChartData(histTempChart, [], () => null, activeRange, currentThresholdC);
          if (histHumChart) window.VACharts.updateChartData(histHumChart, [], () => null, activeRange);
          if (histHeatChart) window.VACharts.updateChartData(histHeatChart, [], () => null, activeRange);
          if (histPressChart) window.VACharts.updateChartData(histPressChart, [], () => null, activeRange);

          window.VACharts.updateChartStatsBar(document.getElementById("histTempStatsBar"), { count: 0, unit: "°C" });
          window.VACharts.updateChartStatsBar(document.getElementById("histHumStatsBar"), { count: 0, unit: "%" });
          window.VACharts.updateChartStatsBar(document.getElementById("histHeatStatsBar"), { count: 0, unit: "°C" });
          window.VACharts.updateChartStatsBar(document.getElementById("histPressStatsBar"), { unavailable: true, unavailableMsg: "No pressure records." });
          updateOverviewStats(summary);
          return;
        }

        // 1. Ambient Temperature Chart
        if (histTempChart) {
          if (summary.temp_count > 0) {
            if (tempOverlay) tempOverlay.style.display = "none";
          } else {
            if (tempOverlay) tempOverlay.style.display = "flex";
          }

          window.VACharts.updateChartData(
            histTempChart,
            readings,
            (r) => r.temperature_c,
            activeRange,
            summary.threshold_c || currentThresholdC
          );

          const tempBadge = document.getElementById("histTempAlertBadge");
          if (tempBadge) {
            const threshold = summary.threshold_c || currentThresholdC;
            if (summary.exceeded_count && summary.exceeded_count > 0) {
              tempBadge.className = "chart-badge danger";
              tempBadge.textContent = `⚠️ Exceeded (${summary.exceeded_count} samples ≥ ${threshold.toFixed(1)}°C)`;
            } else {
              tempBadge.className = "chart-badge success";
              tempBadge.textContent = `Safe Range (< ${threshold.toFixed(1)}°C)`;
            }
          }

          window.VACharts.updateChartStatsBar(document.getElementById("histTempStatsBar"), {
            latest: summary.temp_latest,
            latestTime: summary.temp_latest_time,
            min: summary.temp_min,
            max: summary.temp_max,
            avg: summary.temp_avg,
            count: summary.temp_count,
            unit: "°C"
          });
        }

        // 2. Relative Humidity Chart
        if (histHumChart) {
          if (summary.hum_count > 0) {
            if (humOverlay) humOverlay.classList.add("d-none");
          } else {
            if (humOverlay) humOverlay.classList.remove("d-none");
          }

          window.VACharts.updateChartData(
            histHumChart,
            readings,
            (r) => r.humidity_pct,
            activeRange
          );

          window.VACharts.updateChartStatsBar(document.getElementById("histHumStatsBar"), {
            latest: summary.hum_latest,
            latestTime: summary.hum_latest_time,
            min: summary.hum_min,
            max: summary.hum_max,
            avg: summary.hum_avg,
            count: summary.hum_count,
            unit: "%"
          });
        }

        // 3. Calculated Heat Index Chart
        if (histHeatChart) {
          if (summary.heat_count > 0) {
            if (heatOverlay) heatOverlay.classList.add("d-none");
          } else {
            if (heatOverlay) heatOverlay.classList.remove("d-none");
          }

          window.VACharts.updateChartData(
            histHeatChart,
            readings,
            (r) => r.heat_index_c,
            activeRange
          );

          const heatBadge = document.getElementById("histHeatRiskBadge");
          if (heatBadge) {
            if (summary.heat_latest !== null && summary.heat_latest !== undefined) {
              if (summary.heat_latest >= 51.7) {
                heatBadge.className = "chart-badge danger";
                heatBadge.textContent = "Extreme Danger";
              } else if (summary.heat_latest >= 40.0) {
                heatBadge.className = "chart-badge danger";
                heatBadge.textContent = "Danger (≥ 40°C)";
              } else if (summary.heat_latest >= 32.8) {
                heatBadge.className = "chart-badge warning";
                heatBadge.textContent = "Extreme Caution";
              } else if (summary.heat_latest >= 26.7) {
                heatBadge.className = "chart-badge warning";
                heatBadge.textContent = "Caution";
              } else {
                heatBadge.className = "chart-badge success";
                heatBadge.textContent = "Normal Comfort";
              }
            } else {
              heatBadge.className = "chart-badge secondary";
              heatBadge.textContent = "Below Stress Threshold";
            }
          }

          window.VACharts.updateChartStatsBar(document.getElementById("histHeatStatsBar"), {
            latest: summary.heat_latest,
            latestTime: summary.heat_latest_time,
            min: summary.heat_min,
            max: summary.heat_max,
            avg: summary.heat_avg,
            count: summary.heat_count,
            unit: "°C"
          });
        }

        // 4. Atmospheric Pressure Chart
        if (histPressChart) {
          const pressAvailable = summary.press_available === true && summary.press_count > 0;
          const pressBadge = document.getElementById("histPressStatusBadge");

          if (!pressAvailable) {
            if (pressOverlay) {
              pressOverlay.classList.remove("d-none");
              const pTitle = document.getElementById("histPressEmptyTitle");
              const pSub = document.getElementById("histPressEmptySub");
              if (pTitle) pTitle.textContent = "Barometric Sensor Unavailable";
              if (pSub) pSub.textContent = "No pressure readings recorded for this range. Physical BMP280 is disconnected or DHT11 pipeline is active.";
            }
            if (pressBadge) {
              pressBadge.className = "chart-badge secondary";
              pressBadge.textContent = "BMP280 Disconnected";
            }
            window.VACharts.updateChartData(histPressChart, [], () => null, activeRange);
            window.VACharts.updateChartStatsBar(document.getElementById("histPressStatsBar"), {
              unavailable: true,
              unavailableMsg: "No physical pressure records for this window."
            });
          } else {
            if (pressOverlay) pressOverlay.classList.add("d-none");
            if (pressBadge) {
              pressBadge.className = "chart-badge success";
              pressBadge.textContent = "BMP280 Connected";
            }

            window.VACharts.updateChartData(
              histPressChart,
              readings,
              (r) => r.pressure_hpa,
              activeRange
            );

            window.VACharts.updateChartStatsBar(document.getElementById("histPressStatsBar"), {
              latest: summary.press_latest,
              latestTime: summary.press_latest_time,
              min: summary.press_min,
              max: summary.press_max,
              avg: summary.press_avg,
              count: summary.press_count,
              unit: "hPa"
            });
          }
        }

        // Update Top Aggregated Overview Cards
        updateOverviewStats(summary);
      })
      .catch((err) => {
        console.error("Error loading historical charts:", err);
        if (tempOverlay) tempOverlay.style.display = "flex";
      })
      .finally(() => {
        if (presetGroup) {
          presetGroup.querySelectorAll("button").forEach((b) => (b.disabled = false));
        }
      });
  }

  /**
   * Updates top 4 aggregated overview statistics cards.
   */
  function updateOverviewStats(summary) {
    const sampleCountElem = document.getElementById("statSampleCount");
    if (sampleCountElem) sampleCountElem.textContent = summary.count || 0;

    const statTempRange = document.getElementById("statTempRange");
    const statTempAvg = document.getElementById("statTempAvg");
    if (statTempRange && statTempAvg) {
      if (summary.temp_min !== null && summary.temp_max !== null) {
        statTempRange.textContent = `${Number(summary.temp_min).toFixed(1)}° / ${Number(summary.temp_max).toFixed(1)}°C`;
        statTempAvg.textContent = `Avg: ${Number(summary.temp_avg).toFixed(1)}°C`;
      } else {
        statTempRange.textContent = "-- / -- °C";
        statTempAvg.textContent = "Avg: --";
      }
    }

    const statHumRange = document.getElementById("statHumRange");
    const statHumAvg = document.getElementById("statHumAvg");
    if (statHumRange && statHumAvg) {
      if (summary.hum_min !== null && summary.hum_max !== null) {
        statHumRange.textContent = `${Number(summary.hum_min).toFixed(0)}% / ${Number(summary.hum_max).toFixed(0)}%`;
        statHumAvg.textContent = `Avg: ${Number(summary.hum_avg).toFixed(0)}%`;
      } else {
        statHumRange.textContent = "-- / -- %";
        statHumAvg.textContent = "Avg: --";
      }
    }

    const statPressRange = document.getElementById("statPressRange");
    const statPressAvg = document.getElementById("statPressAvg");
    if (statPressRange && statPressAvg) {
      if (summary.press_min !== null && summary.press_max !== null) {
        statPressRange.textContent = `${Number(summary.press_min).toFixed(1)} / ${Number(summary.press_max).toFixed(1)} hPa`;
        statPressAvg.textContent = `Avg: ${Number(summary.press_avg).toFixed(1)} hPa`;
      } else {
        statPressRange.textContent = "-- / -- hPa";
        statPressAvg.textContent = "BMP280 Offline";
      }
    }
  }

  /**
   * Loads paginated table of readings.
   */
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
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((data) => {
        const tbody = document.getElementById("historyTbody");
        const pageInd = document.getElementById("pageIndicator");

        const readings = data.readings || [];
        if (summary) summary.textContent = `Showing ${readings.length} of ${data.total} records`;
        if (pageInd) pageInd.textContent = `Page ${data.page} of ${data.total_pages}`;

        if (prevBtn) prevBtn.disabled = !data.has_prev;
        if (nextBtn) nextBtn.disabled = !data.has_next;

        if (readings.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-secondary">No records found matching query criteria.</td></tr>`;
          return;
        }

        tbody.innerHTML = readings.map((r) => {
          const d = new Date(r.timestamp);
          const timeStr = `${d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })} ${d.toLocaleTimeString([], { hour12: false })}`;
          const humStr = (r.humidity_pct !== null && r.humidity_pct !== undefined) ? `${Number(r.humidity_pct).toFixed(1)}%` : '<span class="text-muted">–</span>';
          const hiStr = (r.heat_index_c !== null && r.heat_index_c !== undefined) ? `${Number(r.heat_index_c).toFixed(1)}°C` : '<span class="text-muted">–</span>';
          const pressStr = (r.pressure_hpa !== null && r.pressure_hpa !== undefined) ? `${Number(r.pressure_hpa).toFixed(1)} hPa` : '<span class="text-muted">–</span>';
          const srcBadge = r.source && r.source.includes("dht11") ? `<span class="badge bg-success bg-opacity-10 text-success">${r.source}</span>` : `<span class="badge bg-light text-muted">${r.source || "sensor"}</span>`;

          return `
            <tr>
              <td>#${r.id}</td>
              <td>${timeStr}</td>
              <td style="color: #dc2626; font-weight: 600;">${Number(r.temperature_c).toFixed(2)}</td>
              <td style="color: #0284c7; font-weight: 600;">${humStr}</td>
              <td>${pressStr}</td>
              <td style="color: #ea580c;">${hiStr}</td>
              <td>${srcBadge}</td>
              <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
            </tr>
          `;
        }).join("");

        updateExportLink();
      })
      .catch((err) => {
        console.error("History table error:", err);
        const tbody = document.getElementById("historyTbody");
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">Error retrieving table records. Please retry.</td></tr>`;
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
      url += `range=${encodeURIComponent(currentRangePreset)}`;
    }
    btn.setAttribute("href", url);
  }

  function setupFilters() {
    // Preset buttons
    const presetGroup = document.getElementById("historyPresetGroup");
    if (presetGroup) {
      presetGroup.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", function () {
          presetGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
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

    // Series toggles in historical section header
    const legendToggles = document.querySelectorAll("#historyLegendToggles .legend-item");
    legendToggles.forEach((item) => {
      item.addEventListener("click", function () {
        const target = this.getAttribute("data-target");
        let wrapper = null;
        if (target === "temp") wrapper = document.getElementById("histCardTempWrapper");
        if (target === "hum") wrapper = document.getElementById("histCardHumWrapper");
        if (target === "heat") wrapper = document.getElementById("histCardHeatWrapper");
        if (target === "press") wrapper = document.getElementById("histCardPressWrapper");

        if (wrapper) {
          const isHidden = wrapper.classList.toggle("d-none");
          this.classList.toggle("dimmed", isHidden);
        }
      });
    });

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
          presetGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        }

        currentPage = 1;
        loadChartData();
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
          presetGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
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
        pageSize = parseInt(this.value, 10);
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
    initCharts();
    setupFilters();
    loadChartData();
    loadHistoryTable();
  });
})();
