/**
 * Virtual Atmosphere (VA) - Professional Environmental Dashboard Controller
 * 4 Dedicated Measurement Charts: Temperature, Humidity, Heat Index, Pressure
 * Clean Responsive Layout, Monotone Interpolation, Honest Gap & Offline Reporting
 */

(function () {
  "use strict";

  let tempChart = null;
  let humChart = null;
  let heatChart = null;
  let pressChart = null;
  let forecastChart = null;

  let currentRange = "24h";
  let currentThresholdC = 35.0;
  let currentForecastHorizon = 15;
  let isFetchingCharts = false;

  /**
   * Initializes all four separated environmental monitoring charts.
   */
  function initCharts() {
    if (!window.VACharts) {
      console.error("VACharts library not loaded.");
      return;
    }

    // 1. Ambient Temperature Chart
    const tempCanvas = document.getElementById("temperatureChart");
    if (tempCanvas) {
      const tempCfg = window.VACharts.buildChartConfig({
        type: "temp",
        label: "Ambient Temperature",
        unit: "°C",
        suggestedMin: 15,
        suggestedMax: 45,
        thresholdVal: currentThresholdC
      });
      tempChart = new Chart(tempCanvas, tempCfg);
    }

    // 2. Relative Humidity Chart
    const humCanvas = document.getElementById("humidityChart");
    if (humCanvas) {
      const humCfg = window.VACharts.buildChartConfig({
        type: "hum",
        label: "Relative Humidity",
        unit: "%",
        yMin: 0,
        yMax: 100
      });
      humChart = new Chart(humCanvas, humCfg);
    }

    // 3. Calculated Heat Index Chart
    const heatCanvas = document.getElementById("heatIndexChart");
    if (heatCanvas) {
      const heatCfg = window.VACharts.buildChartConfig({
        type: "heat",
        label: "Calculated Heat Index",
        unit: "°C",
        suggestedMin: 20,
        suggestedMax: 50,
        isDashed: false
      });
      heatChart = new Chart(heatCanvas, heatCfg);
    }

    // 4. Atmospheric Pressure Chart
    const pressCanvas = document.getElementById("pressureChart");
    if (pressCanvas) {
      const pressCfg = window.VACharts.buildChartConfig({
        type: "press",
        label: "Atmospheric Pressure",
        unit: "hPa",
        suggestedMin: 980,
        suggestedMax: 1035
      });
      pressChart = new Chart(pressCanvas, pressCfg);
    }
  }

  /**
   * Fetches latest telemetry status and updates cards, condition badges, and honest connectivity.
   */
  async function fetchLatestData() {
    try {
      const res = await fetch("/api/readings/latest");
      if (!res.ok) throw new Error("Failed to fetch latest readings");
      const data = await res.json();
      updateDashboardUI(data);
    } catch (err) {
      console.warn("Telemetry fetch error:", err);
      renderOfflineUI();
    }
  }

  /**
   * Updates all metrics, condition cards, status indicators, and station diagnostics.
   */
  function updateDashboardUI(data) {
    const latest = data.latest;
    const trend = data.trend || {};
    const today = data.today_stats || {};
    const alertInfo = data.alert || {};
    const sensor = data.sensor || {};
    const freshness = data.freshness || {};

    const conditionsMeta = document.getElementById("conditionsLastUpdated");
    const conditionsPill = document.getElementById("currentConditionsPill");
    const conditionsPillText = document.getElementById("currentConditionsStatusText");

    const sidebarDot = document.getElementById("sidebarStatusDot");
    const sidebarTitle = document.getElementById("sidebarStatusTitle");
    const sidebarSub = document.getElementById("sidebarStatusSub");

    // Sync safety threshold
    if (alertInfo.threshold_c !== undefined) {
      currentThresholdC = Number(alertInfo.threshold_c);
      const tThreshEl = document.getElementById("tempThresholdBadge");
      if (tThreshEl) tThreshEl.textContent = `Threshold: ${currentThresholdC.toFixed(1)}°C`;
      const inThresh = document.getElementById("inputThreshold");
      if (inThresh) inThresh.value = currentThresholdC;
    }

    // Honest Sensor Connectivity Evaluation
    const isLive = freshness.is_live === true;
    const isStale = freshness.is_stale === true;
    const hasData = latest !== null && latest !== undefined;

    if (conditionsMeta) {
      if (hasData && latest.timestamp) {
        const d = new Date(latest.timestamp);
        conditionsMeta.textContent = `Last updated: ${d.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" })}, ${d.toLocaleTimeString([], { hour12: false })}`;
      } else {
        conditionsMeta.textContent = "Last updated: No real sensor records found";
      }
    }

    // Status Pill & Sidebar Status Synchronization
    if (isLive) {
      if (conditionsPill) conditionsPill.className = "live-status-pill online";
      if (conditionsPillText) conditionsPillText.textContent = "Live Data";

      if (sidebarDot) sidebarDot.className = "status-indicator-dot online";
      if (sidebarTitle) sidebarTitle.textContent = "Sensor Online";
      if (sidebarSub) sidebarSub.textContent = (latest && latest.sensor_type === "dht11") ? "Raspberry Pi DHT11" : (sensor.sensor_type || "Raspberry Pi DHT11");
    } else if (isStale && hasData) {
      if (conditionsPill) conditionsPill.className = "live-status-pill stale";
      if (conditionsPillText) conditionsPillText.textContent = "Sensor Offline";

      if (sidebarDot) sidebarDot.className = "status-indicator-dot warning";
      if (sidebarTitle) sidebarTitle.textContent = "Sensor Offline";
      const ageStr = freshness.age_seconds ? Math.round(freshness.age_seconds / 60) + "m ago" : "stale";
      if (sidebarSub) sidebarSub.textContent = `Stale reading (${ageStr})`;
    } else {
      if (conditionsPill) conditionsPill.className = "live-status-pill offline";
      if (conditionsPillText) conditionsPillText.textContent = "No Live Reading";

      if (sidebarDot) sidebarDot.className = "status-indicator-dot offline";
      if (sidebarTitle) sidebarTitle.textContent = "Sensor Offline";
      if (sidebarSub) sidebarSub.textContent = "Awaiting ingestion telemetry";
    }

    // Temperature Condition Card
    const tempValEl = document.getElementById("cardTempVal");
    const tempStatusEl = document.getElementById("tempConditionStatus");
    if (tempValEl) {
      tempValEl.textContent = hasData && latest.temperature_c !== null ? Number(latest.temperature_c).toFixed(1) : "--.-";
    }
    if (tempStatusEl) {
      if (!hasData) {
        tempStatusEl.textContent = "No Data";
        tempStatusEl.className = "card-metric-status text-muted";
      } else if (alertInfo.has_active_alert || (latest.temperature_c >= currentThresholdC)) {
        tempStatusEl.textContent = "High";
        tempStatusEl.className = "card-metric-status text-danger fw-bold";
      } else {
        tempStatusEl.textContent = "Normal";
        tempStatusEl.className = "card-metric-status text-success fw-semibold";
      }
    }

    // Humidity Condition Card
    const humValEl = document.getElementById("cardHumidityVal");
    const humStatusEl = document.getElementById("humConditionStatus");
    if (humValEl) {
      humValEl.textContent = hasData && latest.humidity_pct !== null && latest.humidity_pct !== undefined ? Number(latest.humidity_pct).toFixed(0) : "--";
    }
    if (humStatusEl) {
      if (!hasData || latest.humidity_pct === null) {
        humStatusEl.textContent = "No Data";
        humStatusEl.className = "card-metric-status text-muted";
      } else if (latest.humidity_pct >= 70) {
        humStatusEl.textContent = "High";
        humStatusEl.className = "card-metric-status text-warning fw-semibold";
      } else if (latest.humidity_pct <= 30) {
        humStatusEl.textContent = "Dry";
        humStatusEl.className = "card-metric-status text-warning fw-semibold";
      } else {
        humStatusEl.textContent = "Normal";
        humStatusEl.className = "card-metric-status text-success fw-semibold";
      }
    }

    // Heat Index Card
    const heatValEl = document.getElementById("cardHeatIndexVal");
    const heatStatusEl = document.getElementById("heatIndexConditionStatus");
    const heatAdvisoryEl = document.getElementById("cardHeatRiskAdvisory");
    const heatRisk = data.heat_risk;

    if (heatValEl) {
      if (hasData && latest.heat_index_c !== null && latest.heat_index_c !== undefined) {
        heatValEl.textContent = Number(latest.heat_index_c).toFixed(1);
      } else {
        heatValEl.textContent = "--.-";
      }
    }
    if (heatStatusEl) {
      if (!hasData || latest.heat_index_c === null) {
        heatStatusEl.textContent = "Normal";
        heatStatusEl.className = "card-metric-status text-muted";
      } else if (heatRisk && heatRisk.category) {
        heatStatusEl.textContent = heatRisk.category;
        heatStatusEl.style.color = (heatRisk.category === "Danger" || heatRisk.category === "Extreme Caution") ? "#dc2626" : "#ea580c";
      } else {
        heatStatusEl.textContent = "Normal";
        heatStatusEl.className = "card-metric-status text-success";
      }
    }
    if (heatAdvisoryEl) {
      if (heatRisk && heatRisk.advisory) {
        heatAdvisoryEl.textContent = heatRisk.advisory;
      } else if (hasData && latest.heat_index_c) {
        heatAdvisoryEl.textContent = "Calculated via NOAA Rothfusz formula";
      } else {
        heatAdvisoryEl.textContent = "Below thermal stress threshold (T < 26.7°C or RH < 40%)";
      }
    }

    // Today's Stats in Top Cards
    const tempMinEl = document.getElementById("tempMin");
    const tempAvgEl = document.getElementById("tempAvg");
    const tempMaxEl = document.getElementById("tempMax");
    if (tempMinEl) tempMinEl.textContent = today.min_temp !== null && today.min_temp !== undefined ? today.min_temp.toFixed(1) + "°" : "--";
    if (tempAvgEl) tempAvgEl.textContent = today.avg_temp !== null && today.avg_temp !== undefined ? today.avg_temp.toFixed(1) + "°" : "--";
    if (tempMaxEl) tempMaxEl.textContent = today.max_temp !== null && today.max_temp !== undefined ? today.max_temp.toFixed(1) + "°" : "--";

    const humMinEl = document.getElementById("humMin");
    const humAvgEl = document.getElementById("humAvg");
    const humMaxEl = document.getElementById("humMax");
    if (humMinEl) humMinEl.textContent = today.min_humidity !== null && today.min_humidity !== undefined ? today.min_humidity.toFixed(0) + "%" : "--";
    if (humAvgEl) humAvgEl.textContent = today.avg_humidity !== null && today.avg_humidity !== undefined ? today.avg_humidity.toFixed(0) + "%" : "--";
    if (humMaxEl) humMaxEl.textContent = today.max_humidity !== null && today.max_humidity !== undefined ? today.max_humidity.toFixed(0) + "%" : "--";

    // Dedicated DHT11 Pipeline Card
    const dht = data.dht11 || (latest && (latest.sensor_type === "dht11" || (latest.source && latest.source.includes("dht11"))) ? latest : null);
    const dhtTempVal = document.getElementById("dht11TempVal");
    const dhtHumVal = document.getElementById("dht11HumVal");
    const dhtSource = document.getElementById("dht11Source");
    const dhtLastUpdated = document.getElementById("dht11LastUpdated");
    const dhtStatusPill = document.getElementById("dht11StatusPill");
    const dhtStatusText = document.getElementById("dht11StatusText");

    if (dht) {
      if (dhtTempVal) dhtTempVal.textContent = (dht.temperature_c !== null && dht.temperature_c !== undefined) ? Number(dht.temperature_c).toFixed(1) : "--.-";
      const hVal = dht.humidity_percent !== undefined ? dht.humidity_percent : dht.humidity_pct;
      if (dhtHumVal) dhtHumVal.textContent = (hVal !== null && hVal !== undefined) ? Number(hVal).toFixed(0) : "--";
      if (dhtSource) dhtSource.textContent = dht.source || "dht11";
      if (dhtLastUpdated && dht.timestamp) {
        dhtLastUpdated.textContent = new Date(dht.timestamp).toLocaleTimeString([], { hour12: false });
      }
      if (dhtStatusPill) {
        const dhtAge = dht.timestamp ? (Date.now() - new Date(dht.timestamp).getTime()) / 1000 : 999999;
        if (dhtAge < 180) {
          dhtStatusPill.className = "status-pill online py-1 px-2";
          if (dhtStatusText) dhtStatusText.textContent = "Ingesting";
        } else {
          dhtStatusPill.className = "status-pill offline py-1 px-2";
          if (dhtStatusText) dhtStatusText.textContent = "Idle";
        }
      }
    }

    // Storage Status Diagnostic
    const storageEl = document.getElementById("cardStorageStatus");
    if (storageEl) {
      const db = data.database || {};
      if (db.storage_backend === "turso") {
        storageEl.textContent = "Turso libSQL (Durable Cloud)";
        storageEl.style.color = "#16a34a";
      } else if (db.is_persistent === false) {
        storageEl.textContent = "SQLite (/tmp Ephemeral)";
        storageEl.style.color = "#ea580c";
      } else {
        storageEl.textContent = "SQLite WAL (Local Persistent)";
        storageEl.style.color = "#1f1412";
      }
    }

    // Today's sample count
    const countEl = document.getElementById("cardTodayCount");
    if (countEl) countEl.textContent = today.count || 0;

    const lastColEl = document.getElementById("cardLastCollectionTime");
    if (lastColEl && today.last_collection_time) {
      lastColEl.textContent = new Date(today.last_collection_time).toLocaleTimeString([], { hour12: false });
    }

    // Global Alert Banner
    const globalAlert = document.getElementById("globalAlertContainer");
    if (globalAlert) {
      if (alertInfo.has_active_alert && alertInfo.active_alert) {
        globalAlert.classList.remove("d-none");
        const msgEl = document.getElementById("globalAlertMessage");
        if (msgEl) {
          msgEl.textContent = `Temperature of ${alertInfo.active_alert.measured_value}°C has exceeded the safety threshold of ${alertInfo.threshold_c}°C.`;
        }
      } else {
        globalAlert.classList.add("d-none");
      }
    }
  }

  function renderOfflineUI() {
    const conditionsPill = document.getElementById("currentConditionsPill");
    const conditionsPillText = document.getElementById("currentConditionsStatusText");
    const sidebarDot = document.getElementById("sidebarStatusDot");
    const sidebarTitle = document.getElementById("sidebarStatusTitle");
    const sidebarSub = document.getElementById("sidebarStatusSub");

    if (conditionsPill) conditionsPill.className = "live-status-pill offline";
    if (conditionsPillText) conditionsPillText.textContent = "Sensor Offline";
    if (sidebarDot) sidebarDot.className = "status-indicator-dot offline";
    if (sidebarTitle) sidebarTitle.textContent = "Sensor Offline";
    if (sidebarSub) sidebarSub.textContent = "Server connection standby";
  }

  /**
   * Fetches chronological readings and updates all 4 separated environmental charts.
   */
  async function fetchChartData(range) {
    if (isFetchingCharts) return;
    isFetchingCharts = true;

    const tempOverlay = document.getElementById("tempChartEmptyOverlay");
    const humOverlay = document.getElementById("humChartEmptyOverlay");
    const heatOverlay = document.getElementById("heatChartEmptyOverlay");
    const pressOverlay = document.getElementById("pressChartEmptyOverlay");

    try {
      const res = await fetch(`/api/readings?range=${encodeURIComponent(range)}`);
      if (!res.ok) throw new Error("Failed to fetch range telemetry");
      const json = await res.json();
      const readings = json.readings || [];
      const summary = json.summary || {};
      const totalCount = json.total_count || readings.length;

      // Update Section Header Summary
      const summarySub = document.getElementById("combinedChartSummary");
      if (summarySub) {
        if (totalCount === 0) {
          summarySub.textContent = `No real samples recorded in last ${range} • Awaiting incoming sensor telemetry`;
        } else {
          const downsampleNotice = json.is_downsampled ? ` (${readings.length} visible peaks/transitions)` : "";
          summarySub.textContent = `${totalCount} source readings in last ${range}${downsampleNotice} • Turso / SQLite live pipeline`;
        }
      }

      // If entire dataset is empty
      if (totalCount === 0 || readings.length === 0) {
        if (tempOverlay) tempOverlay.classList.remove("d-none");
        if (humOverlay) humOverlay.classList.remove("d-none");
        if (heatOverlay) heatOverlay.classList.remove("d-none");
        if (pressOverlay) pressOverlay.classList.remove("d-none");

        if (tempChart) window.VACharts.updateChartData(tempChart, [], () => null, range, currentThresholdC);
        if (humChart) window.VACharts.updateChartData(humChart, [], () => null, range);
        if (heatChart) window.VACharts.updateChartData(heatChart, [], () => null, range);
        if (pressChart) window.VACharts.updateChartData(pressChart, [], () => null, range);

        // Clear stats bars
        window.VACharts.updateChartStatsBar(document.getElementById("tempChartStatsBar"), { count: 0, unit: "°C" });
        window.VACharts.updateChartStatsBar(document.getElementById("humChartStatsBar"), { count: 0, unit: "%" });
        window.VACharts.updateChartStatsBar(document.getElementById("heatChartStatsBar"), { count: 0, unit: "°C" });
        window.VACharts.updateChartStatsBar(document.getElementById("pressChartStatsBar"), { unavailable: true, unavailableMsg: "No pressure readings recorded." });
        return;
      }

      // 1. Ambient Temperature Chart Update
      if (tempChart) {
        const tempReadingsCount = summary.temp_count || 0;
        if (tempReadingsCount === 0) {
          if (tempOverlay) tempOverlay.classList.remove("d-none");
        } else {
          if (tempOverlay) tempOverlay.classList.add("d-none");
        }

        window.VACharts.updateChartData(
          tempChart,
          readings,
          (r) => r.temperature_c,
          range,
          summary.threshold_c || currentThresholdC
        );

        // Update Temperature Alert Exceedance Badge
        const tempAlertBadge = document.getElementById("tempThresholdAlertBadge");
        if (tempAlertBadge) {
          const threshold = summary.threshold_c || currentThresholdC;
          if (summary.exceeded_count && summary.exceeded_count > 0) {
            tempAlertBadge.className = "chart-badge danger";
            tempAlertBadge.textContent = `⚠️ Exceeded (${summary.exceeded_count} samples ≥ ${threshold.toFixed(1)}°C)`;
          } else {
            tempAlertBadge.className = "chart-badge success";
            tempAlertBadge.textContent = `Normal Safe Range (< ${threshold.toFixed(1)}°C)`;
          }
        }

        // Update Temperature Stats Bar
        window.VACharts.updateChartStatsBar(document.getElementById("tempChartStatsBar"), {
          latest: summary.temp_latest,
          latestTime: summary.temp_latest_time,
          min: summary.temp_min,
          max: summary.temp_max,
          avg: summary.temp_avg,
          count: summary.temp_count,
          unit: "°C"
        });
      }

      // 2. Relative Humidity Chart Update
      if (humChart) {
        const humCount = summary.hum_count || 0;
        if (humCount === 0) {
          if (humOverlay) humOverlay.classList.remove("d-none");
        } else {
          if (humOverlay) humOverlay.classList.add("d-none");
        }

        window.VACharts.updateChartData(
          humChart,
          readings,
          (r) => r.humidity_pct,
          range
        );

        // Update Humidity Stats Bar
        window.VACharts.updateChartStatsBar(document.getElementById("humChartStatsBar"), {
          latest: summary.hum_latest,
          latestTime: summary.hum_latest_time,
          min: summary.hum_min,
          max: summary.hum_max,
          avg: summary.hum_avg,
          count: summary.hum_count,
          unit: "%"
        });
      }

      // 3. Calculated Heat Index Chart Update
      if (heatChart) {
        const heatCount = summary.heat_count || 0;
        if (heatCount === 0) {
          if (heatOverlay) heatOverlay.classList.remove("d-none");
        } else {
          if (heatOverlay) heatOverlay.classList.add("d-none");
        }

        window.VACharts.updateChartData(
          heatChart,
          readings,
          (r) => r.heat_index_c,
          range
        );

        // Update Heat Risk Category Badge
        const heatBadge = document.getElementById("heatIndexRiskCategoryBadge");
        if (heatBadge) {
          if (summary.heat_latest !== null && summary.heat_latest !== undefined) {
            if (summary.heat_latest >= 51.7) {
              heatBadge.className = "chart-badge danger";
              heatBadge.textContent = "Extreme Danger (≥ 51.7°C)";
            } else if (summary.heat_latest >= 40.0) {
              heatBadge.className = "chart-badge danger";
              heatBadge.textContent = "Danger (40–51°C)";
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

        // Update Heat Index Stats Bar
        window.VACharts.updateChartStatsBar(document.getElementById("heatChartStatsBar"), {
          latest: summary.heat_latest,
          latestTime: summary.heat_latest_time,
          min: summary.heat_min,
          max: summary.heat_max,
          avg: summary.heat_avg,
          count: summary.heat_count,
          unit: "°C"
        });
      }

      // 4. Atmospheric Pressure Chart Update
      if (pressChart) {
        const pressAvailable = summary.press_available === true && summary.press_count > 0;
        const pressBadge = document.getElementById("pressureStatusBadge");

        if (!pressAvailable) {
          // Clean informative empty state explaining sensor is disconnected
          if (pressOverlay) {
            pressOverlay.classList.remove("d-none");
            const pTitle = document.getElementById("pressChartEmptyTitle");
            const pSub = document.getElementById("pressChartEmptySub");
            if (pTitle) pTitle.textContent = "Barometric Pressure Sensor Unavailable";
            if (pSub) pSub.textContent = "No pressure readings recorded. Physical BMP280 sensor is not connected or DHT11 hygrometer pipeline is active (DHT11 records temperature and humidity only).";
          }
          if (pressBadge) {
            pressBadge.className = "chart-badge secondary";
            pressBadge.textContent = "BMP280 Disconnected";
          }
          window.VACharts.updateChartData(pressChart, [], () => null, range);
          window.VACharts.updateChartStatsBar(document.getElementById("pressChartStatsBar"), {
            unavailable: true,
            unavailableMsg: "No physical pressure readings recorded. BMP280 is disconnected."
          });
        } else {
          if (pressOverlay) pressOverlay.classList.add("d-none");
          if (pressBadge) {
            pressBadge.className = "chart-badge success";
            pressBadge.textContent = "BMP280 Connected";
          }

          window.VACharts.updateChartData(
            pressChart,
            readings,
            (r) => r.pressure_hpa,
            range
          );

          window.VACharts.updateChartStatsBar(document.getElementById("pressChartStatsBar"), {
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

      // Update Microclimate Analysis in Section 5
      const ampEl = document.getElementById("summaryThermalAmplitude");
      const baroDeltaEl = document.getElementById("summaryBaroDelta");
      if (ampEl) {
        if (summary.temp_min !== null && summary.temp_max !== null) {
          const spread = Math.abs(summary.temp_max - summary.temp_min).toFixed(1);
          ampEl.textContent = `${spread} °C`;
        } else {
          ampEl.textContent = "-- °C";
        }
      }
      if (baroDeltaEl) {
        if (summary.press_min !== null && summary.press_max !== null) {
          const delta = Math.abs(summary.press_max - summary.press_min).toFixed(1);
          baroDeltaEl.textContent = `${delta} hPa`;
        } else {
          baroDeltaEl.textContent = "-- hPa";
        }
      }
    } catch (e) {
      console.warn("Could not refresh charts:", e);
      if (tempOverlay) tempOverlay.classList.remove("d-none");
    } finally {
      isFetchingCharts = false;
    }
  }

  /**
   * Loads recent readings table rows.
   */
  async function fetchRecentTable() {
    try {
      const res = await fetch("/api/readings/history?page=1&limit=10");
      if (!res.ok) return;
      const data = await res.json();
      const tbody = document.getElementById("recentReadingsTbody");
      if (!tbody) return;

      const readings = data.readings || [];
      if (readings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">No measurements logged yet. Live data from Arduino/Pi will appear here.</td></tr>`;
        return;
      }

      tbody.innerHTML = readings.map((r) => {
        const d = new Date(r.timestamp);
        const timeStr = `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${d.toLocaleTimeString([], { hour12: false })}`;
        const tVal = r.temperature_c !== null ? Number(r.temperature_c).toFixed(1) + " °C" : "--";
        const hVal = r.humidity_pct !== null && r.humidity_pct !== undefined ? Number(r.humidity_pct).toFixed(0) + " %" : "--";
        const pVal = r.pressure_hpa !== null ? Number(r.pressure_hpa).toFixed(1) + " hPa" : '<span class="text-muted">–</span>';
        const hiVal = r.heat_index_c !== null && r.heat_index_c !== undefined ? Number(r.heat_index_c).toFixed(1) + " °C" : '<span class="text-muted">–</span>';
        const srcBadge = r.source && r.source.includes("dht11") ? `<span class="badge bg-success bg-opacity-10 text-success">${r.source}</span>` : `<span class="badge bg-light text-muted">${r.source || "sensor"}</span>`;
        return `
          <tr>
            <td><strong>${timeStr}</strong></td>
            <td style="color: #dc2626; font-weight: 600;">${tVal}</td>
            <td style="color: #0284c7; font-weight: 600;">${hVal}</td>
            <td>${pVal}</td>
            <td style="color: #ea580c;">${hiVal}</td>
            <td>${srcBadge}</td>
            <td><span class="text-success small fw-semibold">Valid</span></td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.warn("Could not fetch recent table:", e);
    }
  }

  /**
   * Initializes the experimental local microclimate forecast trajectory chart.
   */
  function initForecastChart() {
    const canvas = document.getElementById("forecastTrajectoryChart");
    if (!canvas || !window.Chart) return;

    forecastChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Observed Temp (°C)",
            data: [],
            borderColor: "#f25c38",
            backgroundColor: "rgba(242, 92, 56, 0.08)",
            borderWidth: 2.2,
            cubicInterpolationMode: "monotone",
            pointRadius: 2.5,
            pointBackgroundColor: "#f25c38",
            yAxisID: "y"
          },
          {
            label: "Forecast Temp (°C)",
            data: [],
            borderColor: "#dc2626",
            borderDash: [6, 4],
            borderWidth: 2.2,
            pointRadius: 5,
            pointBackgroundColor: "#dc2626",
            pointHoverRadius: 7,
            yAxisID: "y"
          },
          {
            label: "80% Temp Upper Bound",
            data: [],
            borderColor: "rgba(220, 38, 38, 0.45)",
            borderDash: [3, 3],
            borderWidth: 1,
            pointRadius: 3,
            fill: false,
            yAxisID: "y"
          },
          {
            label: "80% Temp Lower Bound",
            data: [],
            borderColor: "rgba(220, 38, 38, 0.45)",
            borderDash: [3, 3],
            borderWidth: 1,
            pointRadius: 3,
            fill: "-1",
            backgroundColor: "rgba(220, 38, 38, 0.10)",
            yAxisID: "y"
          },
          {
            label: "Observed Humidity (%)",
            data: [],
            borderColor: "#0284c7",
            backgroundColor: "rgba(2, 132, 199, 0.08)",
            borderWidth: 2.2,
            cubicInterpolationMode: "monotone",
            pointRadius: 2.5,
            pointBackgroundColor: "#0284c7",
            yAxisID: "y1"
          },
          {
            label: "Forecast Humidity (%)",
            data: [],
            borderColor: "#0369a1",
            borderDash: [6, 4],
            borderWidth: 2.2,
            pointRadius: 5,
            pointBackgroundColor: "#0369a1",
            pointHoverRadius: 7,
            yAxisID: "y1"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        interaction: { mode: "index", intersect: false },
        layout: { padding: { top: 10, right: 10, bottom: 5, left: 5 } },
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: {
              boxWidth: 12,
              font: { size: 11, family: "'Inter', sans-serif" },
              filter: function (item) {
                return !item.text.includes("Bound");
              }
            }
          },
          tooltip: {
            enabled: true,
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            titleColor: "#1f1412",
            bodyColor: "#5a463e",
            borderColor: "rgba(230, 210, 195, 0.95)",
            borderWidth: 1.5,
            padding: 10,
            usePointStyle: true,
            callbacks: {
              label: function (ctx) {
                const val = ctx.parsed.y;
                if (val === null || val === undefined) return null;
                const dsLabel = ctx.dataset.label || "";
                if (dsLabel.includes("Temp")) {
                  return ` ${dsLabel}: ${val.toFixed(1)}°C`;
                }
                return ` ${dsLabel}: ${val.toFixed(1)}%`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { maxRotation: 0, font: { size: 11 } }
          },
          y: {
            type: "linear",
            display: true,
            position: "left",
            title: { display: true, text: "Temperature (°C)", font: { size: 11, weight: "600" } },
            grid: { color: "rgba(0,0,0,0.05)" },
            ticks: { font: { size: 11 } }
          },
          y1: {
            type: "linear",
            display: true,
            position: "right",
            title: { display: true, text: "Humidity (%)", font: { size: 11, weight: "600" } },
            grid: { drawOnChartArea: false },
            min: 0,
            max: 100,
            ticks: { font: { size: 11 } }
          }
        }
      }
    });
  }

  /**
   * Fetches local microclimate forecast data and updates UI metrics, status, and chart.
   */
  async function fetchForecastData() {
    const emptyOverlay = document.getElementById("forecastEmptyOverlay");
    const emptyTitle = document.getElementById("forecastEmptyTitle");
    const emptySub = document.getElementById("forecastEmptySub");
    const statusPill = document.getElementById("forecastStatusPill");
    const statusText = document.getElementById("forecastStatusText");

    try {
      const res = await fetch(`/api/forecast?horizon=${currentForecastHorizon}m&include_history=true`);
      if (!res.ok) throw new Error("Forecast API HTTP " + res.status);
      const data = await res.json();

      const obsTempEl = document.getElementById("forecastObsTemp");
      const obsHumEl = document.getElementById("forecastObsHum");
      const obsTimeEl = document.getElementById("forecastObsTime");
      const obsAgeEl = document.getElementById("forecastObsAge");

      if (data.sensor && data.sensor.last_reading_time) {
        if (obsTimeEl) {
          const d = new Date(data.sensor.last_reading_time);
          obsTimeEl.textContent = isNaN(d.getTime()) ? data.sensor.last_reading_time : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        }
      }
      if (data.sensor && data.sensor.data_age_seconds !== null && data.sensor.data_age_seconds !== undefined) {
        if (obsAgeEl) {
          const sec = data.sensor.data_age_seconds;
          obsAgeEl.textContent = sec < 60 ? `${Math.round(sec)}s ago` : `${Math.round(sec / 60)}m ago`;
          obsAgeEl.className = data.sensor.freshness === "fresh" ? "badge bg-success text-white" : "badge bg-warning text-dark";
        }
      }

      if (data.is_available && data.forecast) {
        if (emptyOverlay) emptyOverlay.classList.add("d-none");

        if (statusPill && statusText) {
          statusPill.className = "status-pill online py-1 px-2";
          statusText.textContent = `Active ${data.forecast.horizon_minutes}m Horizon`;
        }

        if (obsTempEl && data.forecast.observed) obsTempEl.textContent = data.forecast.observed.temperature_c.toFixed(1);
        if (obsHumEl && data.forecast.observed) obsHumEl.textContent = data.forecast.observed.humidity_pct.toFixed(1);

        const predTempEl = document.getElementById("forecastPredTemp");
        const predHumEl = document.getElementById("forecastPredHum");
        const tempDeltaBadge = document.getElementById("forecastTempDeltaBadge");
        const humDeltaBadge = document.getElementById("forecastHumDeltaBadge");
        const intervalText = document.getElementById("forecastIntervalText");

        const predTemp = data.forecast.temperature.predicted_c;
        const deltaTemp = data.forecast.temperature.change_c;
        const predHum = data.forecast.humidity.predicted_pct;
        const deltaHum = data.forecast.humidity.change_pct;

        if (predTempEl) predTempEl.textContent = predTemp.toFixed(1);
        if (tempDeltaBadge) {
          const sign = deltaTemp > 0 ? "+" : "";
          tempDeltaBadge.textContent = `${sign}${deltaTemp.toFixed(1)}°C`;
          tempDeltaBadge.className = deltaTemp > 0.3 ? "badge bg-danger ms-1" : (deltaTemp < -0.3 ? "badge bg-info ms-1" : "badge bg-secondary ms-1");
        }

        if (predHumEl) predHumEl.textContent = predHum.toFixed(1);
        if (humDeltaBadge) {
          const sign = deltaHum > 0 ? "+" : "";
          humDeltaBadge.textContent = `${sign}${deltaHum.toFixed(1)}%`;
          humDeltaBadge.className = deltaHum > 1.0 ? "badge bg-primary ms-1" : (deltaHum < -1.0 ? "badge bg-warning ms-1" : "badge bg-secondary ms-1");
        }

        if (intervalText) {
          const lower = data.forecast.temperature.lower_bound_c;
          const upper = data.forecast.temperature.upper_bound_c;
          intervalText.textContent = `${lower.toFixed(1)}°C – ${upper.toFixed(1)}°C`;
        }

        const btSamples = document.getElementById("forecastBacktestSamples");
        const btTempMetrics = document.getElementById("forecastTempMetrics");
        const btHumMetrics = document.getElementById("forecastHumMetrics");
        const btSkillText = document.getElementById("forecastSkillText");

        if (data.backtest && data.backtest.status === "active") {
          if (btSamples) btSamples.textContent = `${data.backtest.samples_evaluated} Samples`;
          if (btTempMetrics && data.backtest.temperature) {
            btTempMetrics.textContent = `${data.backtest.temperature.mae_c.toFixed(2)}°C / ${data.backtest.temperature.rmse_c.toFixed(2)}°C`;
          }
          if (btHumMetrics && data.backtest.humidity) {
            btHumMetrics.textContent = `${data.backtest.humidity.mae_pct.toFixed(1)}% / ${data.backtest.humidity.rmse_pct.toFixed(1)}%`;
          }
          if (btSkillText) btSkillText.textContent = data.backtest.summary || "Backtested vs persistence baseline.";
        } else {
          if (btSamples) btSamples.textContent = "Provisional";
          if (btTempMetrics) btTempMetrics.textContent = "Accumulating";
          if (btHumMetrics) btHumMetrics.textContent = "Accumulating";
          if (btSkillText) btSkillText.textContent = (data.backtest && data.backtest.explanation) || "Evaluating rolling-origin backtest...";
        }

        // Update trajectory chart
        if (forecastChart && data.history_series && data.history_series.length > 0) {
          const history = data.history_series;
          const labels = [];
          const obsTempData = [];
          const obsHumData = [];

          history.forEach(pt => {
            const dt = new Date(pt.timestamp);
            const timeStr = isNaN(dt.getTime()) ? pt.timestamp.substring(11, 16) : dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            labels.push(timeStr);
            obsTempData.push(pt.temperature_c);
            obsHumData.push(pt.humidity_pct);
          });

          const targetDt = new Date(data.forecast.target_timestamp);
          const targetLabel = isNaN(targetDt.getTime()) ? `+${data.forecast.horizon_minutes}m` : targetDt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " (Forecast)";
          labels.push(targetLabel);

          const n = labels.length;
          const forecastTempData = new Array(n).fill(null);
          const forecastHumData = new Array(n).fill(null);
          const upperTempData = new Array(n).fill(null);
          const lowerTempData = new Array(n).fill(null);

          const lastIdx = n - 2;
          forecastTempData[lastIdx] = obsTempData[lastIdx];
          forecastTempData[n - 1] = predTemp;

          forecastHumData[lastIdx] = obsHumData[lastIdx];
          forecastHumData[n - 1] = predHum;

          upperTempData[lastIdx] = obsTempData[lastIdx];
          upperTempData[n - 1] = data.forecast.temperature.upper_bound_c;

          lowerTempData[lastIdx] = obsTempData[lastIdx];
          lowerTempData[n - 1] = data.forecast.temperature.lower_bound_c;

          forecastChart.data.labels = labels;
          forecastChart.data.datasets[0].data = obsTempData;
          forecastChart.data.datasets[1].data = forecastTempData;
          forecastChart.data.datasets[2].data = upperTempData;
          forecastChart.data.datasets[3].data = lowerTempData;
          forecastChart.data.datasets[4].data = obsHumData;
          forecastChart.data.datasets[5].data = forecastHumData;

          forecastChart.update("none");
        }

      } else {
        if (emptyOverlay) emptyOverlay.classList.remove("d-none");
        if (emptyTitle) {
          emptyTitle.textContent = data.status === "stale_sensor" ? "Sensor Telemetry Stale" : (data.status === "offline" ? "Sensor Offline" : "Insufficient Telemetry History");
        }
        if (emptySub) {
          emptySub.textContent = (data.sufficiency && data.sufficiency.reason) || "Requires at least 15 minutes of continuous sensor observations.";
        }
        if (statusPill && statusText) {
          statusPill.className = data.status === "stale_sensor" ? "status-pill stale py-1 px-2" : "status-pill demo py-1 px-2";
          statusText.textContent = data.status === "stale_sensor" ? "Stale Sensor" : (data.status === "offline" ? "Offline" : "Insufficient History");
        }

        const predTempEl = document.getElementById("forecastPredTemp");
        const predHumEl = document.getElementById("forecastPredHum");
        const tempDeltaBadge = document.getElementById("forecastTempDeltaBadge");
        const humDeltaBadge = document.getElementById("forecastHumDeltaBadge");
        const intervalText = document.getElementById("forecastIntervalText");

        if (predTempEl) predTempEl.textContent = "--.-";
        if (predHumEl) predHumEl.textContent = "--.-";
        if (tempDeltaBadge) { tempDeltaBadge.textContent = "--"; tempDeltaBadge.className = "badge bg-secondary ms-1"; }
        if (humDeltaBadge) { humDeltaBadge.textContent = "--"; humDeltaBadge.className = "badge bg-secondary ms-1"; }
        if (intervalText) intervalText.textContent = "Awaiting continuous telemetry";
      }

    } catch (err) {
      console.warn("Forecast fetch error:", err);
      if (emptyOverlay) emptyOverlay.classList.remove("d-none");
      if (emptyTitle) emptyTitle.textContent = "Forecast Temporarily Unavailable";
      if (emptySub) emptySub.textContent = "Could not communicate with the local forecasting engine.";
    }
  }

  // Setup Event Listeners
  function setupListeners() {
    // Range selector buttons
    const rangeBtns = document.querySelectorAll("#tempRangeSelector button");
    rangeBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        rangeBtns.forEach((b) => b.classList.remove("active"));
        this.classList.add("active");
        currentRange = this.getAttribute("data-range") || "24h";
        fetchChartData(currentRange);
      });
    });

    // Interactive Clickable Legend Toggles
    const legendToggles = document.querySelectorAll("#dashboardLegendToggles .legend-item");
    legendToggles.forEach((item) => {
      item.addEventListener("click", function () {
        const target = this.getAttribute("data-target");
        let wrapper = null;
        if (target === "temp") wrapper = document.getElementById("cardChartTempWrapper");
        if (target === "hum") wrapper = document.getElementById("cardChartHumWrapper");
        if (target === "heat") wrapper = document.getElementById("cardChartHeatWrapper");
        if (target === "press") wrapper = document.getElementById("cardChartPressWrapper");

        if (wrapper) {
          const isHidden = wrapper.classList.toggle("d-none");
          this.classList.toggle("dimmed", isHidden);
        }
      });
    });

    // Immediate Refresh Button in Header
    const btnRefresh = document.getElementById("btnRefreshNow");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => {
        fetchLatestData();
        fetchChartData(currentRange);
        fetchRecentTable();
        fetchForecastData();
      });
    }

    // Forecast Horizon Selector Buttons (15m, 30m, 60m)
    const forecastHorizonBtns = document.querySelectorAll("#forecastHorizonSelector button");
    forecastHorizonBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        forecastHorizonBtns.forEach((b) => b.classList.remove("active"));
        this.classList.add("active");
        const horizonVal = parseInt(this.getAttribute("data-horizon") || "15", 10);
        currentForecastHorizon = isNaN(horizonVal) ? 15 : horizonVal;

        const horizonLabel = document.getElementById("forecastCardHorizonLabel");
        if (horizonLabel) horizonLabel.textContent = `${currentForecastHorizon}m`;

        fetchForecastData();
      });
    });

    // Threshold Form Submission
    const thresholdForm = document.getElementById("formThresholdConfig");
    if (thresholdForm) {
      thresholdForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const input = document.getElementById("inputThreshold");
        const feedback = document.getElementById("thresholdFeedback");
        if (!input) return;

        const val = parseFloat(input.value);
        if (isNaN(val) || val < 0 || val > 70) {
          if (feedback) feedback.innerHTML = `<span class="text-danger">Threshold must be between 0°C and 70°C.</span>`;
          return;
        }

        try {
          const csrf = window.VA_CSRF_TOKEN || "";
          const res = await fetch("/api/settings/threshold", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrf
            },
            body: JSON.stringify({ threshold_c: val })
          });
          const resData = await res.json();
          if (res.ok && resData.success) {
            currentThresholdC = val;
            if (feedback) feedback.innerHTML = `<span class="text-success fw-semibold">Threshold updated to ${val.toFixed(1)}°C</span>`;
            setTimeout(() => { if (feedback) feedback.innerHTML = ""; }, 4000);
            fetchLatestData();
            fetchChartData(currentRange);
          } else {
            if (feedback) feedback.innerHTML = `<span class="text-danger">${resData.error || "Failed to update threshold"}</span>`;
          }
        } catch (err) {
          if (feedback) feedback.innerHTML = `<span class="text-danger">Network error saving threshold.</span>`;
        }
      });
    }
  }

  // Initialize Dashboard Controller
  document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    initForecastChart();
    setupListeners();
    fetchLatestData();
    fetchChartData(currentRange);
    fetchRecentTable();
    fetchForecastData();

    // Auto-refresh telemetry polling every 10 seconds
    setInterval(() => {
      fetchLatestData();
      fetchRecentTable();
    }, 10000);

    // Refresh charts and forecast every 30 seconds
    setInterval(() => {
      fetchChartData(currentRange);
      fetchForecastData();
    }, 30000);
  });
})();
