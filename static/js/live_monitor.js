/**
 * Virtual Atmosphere - Live Monitor Telemetry Controller
 * Manages 4 Real-Time Streaming Charts, Threshold Tracking, and Live Pipeline Health
 */

(function () {
  "use strict";

  let liveTempChart = null;
  let liveHumChart = null;
  let liveHeatChart = null;
  let livePressChart = null;

  let currentRange = "1h";
  let pollingIntervalMs = 5000;
  let pollTimer = null;
  let chartSyncTimer = null;
  let currentThresholdC = 35.0;

  const streamRecords = [];
  const MAX_STREAM_ROWS = 25;

  /**
   * Initializes the 4 separated live telemetry charts.
   */
  function initLiveCharts() {
    if (!window.VACharts) {
      console.error("VACharts library not loaded.");
      return;
    }

    // 1. Live Ambient Temperature
    const tempCanvas = document.getElementById("liveTempChart");
    if (tempCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "temp",
        label: "Ambient Temperature",
        unit: "°C",
        suggestedMin: 15,
        suggestedMax: 45,
        thresholdVal: currentThresholdC
      });
      liveTempChart = new Chart(tempCanvas, cfg);
    }

    // 2. Live Relative Humidity
    const humCanvas = document.getElementById("liveHumChart");
    if (humCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "hum",
        label: "Relative Humidity",
        unit: "%",
        yMin: 0,
        yMax: 100
      });
      liveHumChart = new Chart(humCanvas, cfg);
    }

    // 3. Live Calculated Heat Index
    const heatCanvas = document.getElementById("liveHeatChart");
    if (heatCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "heat",
        label: "Calculated Heat Index",
        unit: "°C",
        suggestedMin: 20,
        suggestedMax: 50
      });
      liveHeatChart = new Chart(heatCanvas, cfg);
    }

    // 4. Live Atmospheric Pressure
    const pressCanvas = document.getElementById("livePressChart");
    if (pressCanvas) {
      const cfg = window.VACharts.buildChartConfig({
        type: "press",
        label: "Atmospheric Pressure",
        unit: "hPa",
        suggestedMin: 980,
        suggestedMax: 1035
      });
      livePressChart = new Chart(pressCanvas, cfg);
    }
  }

  /**
   * Fetches latest reading for rapid live gauges, pulse table, and connectivity evaluation.
   */
  async function fetchLivePulse() {
    try {
      const res = await fetch("/api/readings/latest");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();

      const latest = data.latest;
      const sensor = data.sensor || {};
      const alertInfo = data.alert || {};
      const freshness = data.freshness || {};

      if (alertInfo.threshold_c !== undefined) {
        currentThresholdC = Number(alertInfo.threshold_c);
      }

      const isLive = freshness.is_live === true;
      const isStale = freshness.is_stale === true;
      const hasData = latest !== null && latest !== undefined;

      const tempValEl = document.getElementById("liveTempVal");
      const humValEl = document.getElementById("liveHumVal");
      const pressValEl = document.getElementById("livePressVal");

      const tempStatus = document.getElementById("liveTempStatus");
      const tempStatusText = document.getElementById("liveTempStatusText");
      const humStatus = document.getElementById("liveHumStatus");
      const humStatusText = document.getElementById("liveHumStatusText");
      const pressStatus = document.getElementById("livePressStatus");
      const pressStatusText = document.getElementById("livePressStatusText");
      const heatInfo = document.getElementById("liveHeatIndexInfo");

      if (hasData) {
        const tVal = latest.temperature_c !== null ? Number(latest.temperature_c).toFixed(1) : "--.-";
        const hVal = (latest.humidity_pct !== null && latest.humidity_pct !== undefined) ? Number(latest.humidity_pct).toFixed(1) : "--.-";
        const pVal = (latest.pressure_hpa !== null && latest.pressure_hpa !== undefined) ? Number(latest.pressure_hpa).toFixed(1) : "----.-";

        if (tempValEl) tempValEl.textContent = isStale ? `${tVal} (Stale)` : tVal;
        if (humValEl) humValEl.textContent = isStale ? `${hVal} (Stale)` : hVal;
        if (pressValEl) pressValEl.textContent = isStale ? `${pVal} (Stale)` : pVal;

        if (heatInfo) {
          heatInfo.textContent = (latest.heat_index_c !== null && latest.heat_index_c !== undefined) ? `Heat Index: ${Number(latest.heat_index_c).toFixed(1)}°C` : "Heat Index: --°C";
        }

        // Temperature status & threshold evaluation
        if (tempStatus && tempStatusText) {
          if (isStale) {
            tempStatus.className = "status-pill offline";
            tempStatusText.textContent = "Sensor Offline (Stale Reading)";
          } else if (latest.temperature_c >= currentThresholdC) {
            tempStatus.className = "status-pill offline";
            tempStatusText.textContent = `WARNING: ≥ ${currentThresholdC.toFixed(1)}°C Exceeded`;
          } else {
            tempStatus.className = "status-pill online";
            tempStatusText.textContent = "Normal Safe Range";
          }
        }

        // Humidity status
        if (humStatus && humStatusText) {
          if (isStale) {
            humStatus.className = "status-pill offline";
            humStatusText.textContent = "DHT11 Offline";
          } else {
            humStatus.className = "status-pill online";
            humStatusText.textContent = latest.humidity_pct !== null ? "DHT11 Active" : "No Humidity";
          }
        }

        // Pressure status
        if (pressStatus && pressStatusText) {
          if (latest.pressure_hpa === null || latest.pressure_hpa === undefined) {
            pressStatus.className = "status-pill offline";
            pressStatusText.textContent = "BMP280 Disconnected";
          } else if (isStale) {
            pressStatus.className = "status-pill offline";
            pressStatusText.textContent = "Pressure Stale";
          } else {
            pressStatus.className = "status-pill online";
            pressStatusText.textContent = "Nominal Barometric Range";
          }
        }

        // Append to live incoming telemetry pulse log if newer
        if (!streamRecords.some((r) => r.id === latest.id)) {
          streamRecords.unshift(latest);
          if (streamRecords.length > MAX_STREAM_ROWS) {
            streamRecords.pop();
          }
          renderStreamTable();
        }
      } else {
        if (tempValEl) tempValEl.textContent = "--.-";
        if (humValEl) humValEl.textContent = "--.-";
        if (pressValEl) pressValEl.textContent = "----.-";

        if (tempStatus) tempStatus.className = "status-pill offline";
        if (tempStatusText) tempStatusText.textContent = "No Live Reading";
        if (humStatus) humStatus.className = "status-pill offline";
        if (humStatusText) humStatusText.textContent = "Awaiting Sensor";
        if (pressStatus) pressStatus.className = "status-pill offline";
        if (pressStatusText) pressStatusText.textContent = "BMP280 Disconnected";
      }

      // Threshold Info Label
      const threshInfo = document.getElementById("liveTempThresholdInfo");
      if (threshInfo) threshInfo.textContent = `Threshold: ${currentThresholdC.toFixed(1)}°C`;

      // Hardware Diagnostic Panel
      const diagPill = document.getElementById("diagSensorPill");
      const diagStatusText = document.getElementById("diagStatusText");
      const diagSensorName = document.getElementById("diagSensorName");
      const diagFreshness = document.getElementById("diagFreshness");
      const diagErrorCount = document.getElementById("diagErrorCount");
      const diagMode = document.getElementById("diagMode");

      if (diagSensorName) {
        diagSensorName.textContent = (latest && latest.sensor_type === "dht11") ? "DHT11 Hygrometer" : (sensor.sensor_type || "DHT11 / BMP280");
      }
      if (diagFreshness) {
        diagFreshness.textContent = freshness.age_seconds !== null && freshness.age_seconds !== undefined ? `${Math.round(freshness.age_seconds)}s ago` : "--";
      }
      if (diagErrorCount) {
        diagErrorCount.textContent = sensor.consecutive_errors || 0;
      }
      if (diagMode) {
        diagMode.textContent = sensor.mode === "demo" ? "Demo (Simulated)" : "Live Hardware";
      }
      if (diagPill && diagStatusText) {
        if (sensor.mode === "demo") {
          diagPill.className = "status-pill demo";
          diagStatusText.textContent = "Demo Mode";
        } else if (isLive) {
          diagPill.className = "status-pill online";
          diagStatusText.textContent = "Hardware Connected";
        } else {
          diagPill.className = "status-pill offline";
          diagStatusText.textContent = "Hardware Standby";
        }
      }
    } catch (err) {
      console.warn("Live pulse fetch error:", err);
    }
  }

  /**
   * Fetches chronological readings for the active range and updates all 4 live charts.
   */
  async function syncLiveCharts(range) {
    const tempOverlay = document.getElementById("liveTempEmptyOverlay");
    const humOverlay = document.getElementById("liveHumEmptyOverlay");
    const heatOverlay = document.getElementById("liveHeatEmptyOverlay");
    const pressOverlay = document.getElementById("livePressEmptyOverlay");

    try {
      const res = await fetch(`/api/readings?range=${encodeURIComponent(range)}`);
      if (!res.ok) throw new Error("Failed to fetch live chart readings");
      const json = await res.json();
      const readings = json.readings || [];
      const summary = json.summary || {};
      const totalCount = json.total_count || readings.length;

      const summarySub = document.getElementById("liveChartSummary");
      if (summarySub) {
        if (totalCount === 0) {
          summarySub.textContent = `No physical telemetry recorded in last ${range} • Awaiting incoming pulse`;
        } else {
          const downsampleNotice = json.is_downsampled ? ` (${readings.length} peak points)` : "";
          summarySub.textContent = `${totalCount} source readings over last ${range}${downsampleNotice} • Auto-refreshing live`;
        }
      }

      if (totalCount === 0 || readings.length === 0) {
        if (tempOverlay) tempOverlay.classList.remove("d-none");
        if (humOverlay) humOverlay.classList.remove("d-none");
        if (heatOverlay) heatOverlay.classList.remove("d-none");
        if (pressOverlay) pressOverlay.classList.remove("d-none");

        if (liveTempChart) window.VACharts.updateChartData(liveTempChart, [], () => null, range, currentThresholdC);
        if (liveHumChart) window.VACharts.updateChartData(liveHumChart, [], () => null, range);
        if (liveHeatChart) window.VACharts.updateChartData(liveHeatChart, [], () => null, range);
        if (livePressChart) window.VACharts.updateChartData(livePressChart, [], () => null, range);

        window.VACharts.updateChartStatsBar(document.getElementById("liveTempStatsBar"), { count: 0, unit: "°C" });
        window.VACharts.updateChartStatsBar(document.getElementById("liveHumStatsBar"), { count: 0, unit: "%" });
        window.VACharts.updateChartStatsBar(document.getElementById("liveHeatStatsBar"), { count: 0, unit: "°C" });
        window.VACharts.updateChartStatsBar(document.getElementById("livePressStatsBar"), { unavailable: true, unavailableMsg: "No physical pressure readings recorded." });
        return;
      }

      // 1. Live Ambient Temperature Chart
      if (liveTempChart) {
        if (summary.temp_count > 0) {
          if (tempOverlay) tempOverlay.classList.add("d-none");
        } else {
          if (tempOverlay) tempOverlay.classList.remove("d-none");
        }

        window.VACharts.updateChartData(
          liveTempChart,
          readings,
          (r) => r.temperature_c,
          range,
          summary.threshold_c || currentThresholdC
        );

        const tempBadge = document.getElementById("liveTempAlertBadge");
        if (tempBadge) {
          const threshold = summary.threshold_c || currentThresholdC;
          if (summary.exceeded_count && summary.exceeded_count > 0) {
            tempBadge.className = "chart-badge danger";
            tempBadge.textContent = `⚠️ Exceeded (${summary.exceeded_count} readings ≥ ${threshold.toFixed(1)}°C)`;
          } else {
            tempBadge.className = "chart-badge success";
            tempBadge.textContent = `Normal Range (< ${threshold.toFixed(1)}°C)`;
          }
        }

        window.VACharts.updateChartStatsBar(document.getElementById("liveTempStatsBar"), {
          latest: summary.temp_latest,
          latestTime: summary.temp_latest_time,
          min: summary.temp_min,
          max: summary.temp_max,
          avg: summary.temp_avg,
          count: summary.temp_count,
          unit: "°C"
        });
      }

      // 2. Live Relative Humidity Chart
      if (liveHumChart) {
        if (summary.hum_count > 0) {
          if (humOverlay) humOverlay.classList.add("d-none");
        } else {
          if (humOverlay) humOverlay.classList.remove("d-none");
        }

        window.VACharts.updateChartData(
          liveHumChart,
          readings,
          (r) => r.humidity_pct,
          range
        );

        window.VACharts.updateChartStatsBar(document.getElementById("liveHumStatsBar"), {
          latest: summary.hum_latest,
          latestTime: summary.hum_latest_time,
          min: summary.hum_min,
          max: summary.hum_max,
          avg: summary.hum_avg,
          count: summary.hum_count,
          unit: "%"
        });
      }

      // 3. Live Heat Index Chart
      if (liveHeatChart) {
        if (summary.heat_count > 0) {
          if (heatOverlay) heatOverlay.classList.add("d-none");
        } else {
          if (heatOverlay) heatOverlay.classList.remove("d-none");
        }

        window.VACharts.updateChartData(
          liveHeatChart,
          readings,
          (r) => r.heat_index_c,
          range
        );

        const heatBadge = document.getElementById("liveHeatRiskBadge");
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

        window.VACharts.updateChartStatsBar(document.getElementById("liveHeatStatsBar"), {
          latest: summary.heat_latest,
          latestTime: summary.heat_latest_time,
          min: summary.heat_min,
          max: summary.heat_max,
          avg: summary.heat_avg,
          count: summary.heat_count,
          unit: "°C"
        });
      }

      // 4. Live Atmospheric Pressure Chart
      if (livePressChart) {
        const pressAvailable = summary.press_available === true && summary.press_count > 0;
        const pressBadge = document.getElementById("livePressStatusBadge");

        if (!pressAvailable) {
          if (pressOverlay) {
            pressOverlay.classList.remove("d-none");
            const pTitle = document.getElementById("livePressEmptyTitle");
            const pSub = document.getElementById("livePressEmptySub");
            if (pTitle) pTitle.textContent = "Barometric Sensor Unavailable";
            if (pSub) pSub.textContent = "No pressure readings recorded. Physical BMP280 is disconnected or DHT11 pipeline is active.";
          }
          if (pressBadge) {
            pressBadge.className = "chart-badge secondary";
            pressBadge.textContent = "BMP280 Disconnected";
          }
          window.VACharts.updateChartData(livePressChart, [], () => null, range);
          window.VACharts.updateChartStatsBar(document.getElementById("livePressStatsBar"), {
            unavailable: true,
            unavailableMsg: "Pressure sensor disconnected or not recorded."
          });
        } else {
          if (pressOverlay) pressOverlay.classList.add("d-none");
          if (pressBadge) {
            pressBadge.className = "chart-badge success";
            pressBadge.textContent = "BMP280 Live";
          }

          window.VACharts.updateChartData(
            livePressChart,
            readings,
            (r) => r.pressure_hpa,
            range
          );

          window.VACharts.updateChartStatsBar(document.getElementById("livePressStatsBar"), {
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
    } catch (err) {
      console.warn("Could not sync live charts:", err);
    }
  }

  /**
   * Renders incoming live telemetry log table.
   */
  function renderStreamTable() {
    const tbody = document.getElementById("liveStreamTbody");
    const counter = document.getElementById("streamCounter");
    if (!tbody) return;

    if (counter) counter.textContent = `${streamRecords.length} readings received`;

    if (streamRecords.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-secondary">Awaiting initial sensor pulse...</td></tr>`;
      return;
    }

    tbody.innerHTML = streamRecords.map((r) => {
      const d = new Date(r.timestamp);
      const timeStr = d.toLocaleTimeString([], { hour12: false });
      const humStr = (r.humidity_pct !== null && r.humidity_pct !== undefined) ? `${Number(r.humidity_pct).toFixed(1)}%` : '<span class="text-secondary">–</span>';
      const hiStr = (r.heat_index_c !== null && r.heat_index_c !== undefined) ? `${Number(r.heat_index_c).toFixed(1)}°` : '<span class="text-secondary">–</span>';
      const pressStr = (r.pressure_hpa !== null && r.pressure_hpa !== undefined) ? `${Number(r.pressure_hpa).toFixed(1)}` : '<span class="text-secondary">–</span>';
      return `
        <tr>
          <td><strong>${timeStr}</strong></td>
          <td style="color: #dc2626; font-weight: 600;">${Number(r.temperature_c).toFixed(2)}</td>
          <td style="color: #0284c7; font-weight: 600;">${humStr}</td>
          <td style="color: #ea580c;">${hiStr}</td>
          <td>${pressStr}</td>
          <td><span class="badge-tag ${r.source}">${r.source}</span></td>
          <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
        </tr>
      `;
    }).join("");
  }

  /**
   * Sets up range selector buttons and interactive clickable legend toggles.
   */
  function setupControls() {
    // Range selector
    const rangeBtns = document.querySelectorAll("#liveRangeSelector button");
    rangeBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        rangeBtns.forEach((b) => b.classList.remove("active"));
        this.classList.add("active");
        currentRange = this.getAttribute("data-range") || "1h";
        syncLiveCharts(currentRange);
      });
    });

    // Legend toggles
    const legendToggles = document.querySelectorAll("#liveLegendToggles .legend-item");
    legendToggles.forEach((item) => {
      item.addEventListener("click", function () {
        const target = this.getAttribute("data-target");
        let wrapper = null;
        if (target === "temp") wrapper = document.getElementById("liveCardTempWrapper");
        if (target === "hum") wrapper = document.getElementById("liveCardHumWrapper");
        if (target === "heat") wrapper = document.getElementById("liveCardHeatWrapper");
        if (target === "press") wrapper = document.getElementById("liveCardPressWrapper");

        if (wrapper) {
          const isHidden = wrapper.classList.toggle("d-none");
          this.classList.toggle("dimmed", isHidden);
        }
      });
    });

    // Polling interval selector
    const intervalGroup = document.getElementById("livePollingIntervalGroup");
    if (intervalGroup) {
      intervalGroup.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", function () {
          intervalGroup.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
          this.classList.add("active");
          const intervalSec = parseInt(this.getAttribute("data-interval"), 10) || 5;
          pollingIntervalMs = intervalSec * 1000;

          if (pollTimer) clearInterval(pollTimer);
          pollTimer = setInterval(fetchLivePulse, pollingIntervalMs);
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initLiveCharts();
    setupControls();
    fetchLivePulse();
    syncLiveCharts(currentRange);

    // High frequency pulse polling for gauges & stream
    pollTimer = setInterval(fetchLivePulse, pollingIntervalMs);

    // Periodic chart resync every 15 seconds
    chartSyncTimer = setInterval(() => {
      syncLiveCharts(currentRange);
    }, 15000);
  });
})();
