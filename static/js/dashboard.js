/**
 * Virtual Atmosphere (VA) - Sunset Warm Overview Dashboard Controller
 * Dual-Series Temperature & Humidity Microclimate Visualization
 * Turso libSQL Cloud Persistence & Honest Sensor Connectivity Reporting
 */

(function () {
  "use strict";

  let tempHumChart = null;
  let pressChart = null;
  let currentRange = "24h";
  let currentPressRange = "24h";
  let autoRefreshTimer = null;

  // Chart configuration constants for Sunset Warm Theme (WCAG AA compliant contrast)
  const SUNSET_CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    interaction: {
      mode: "index",
      intersect: false
    },
    plugins: {
      legend: { display: false }, // Rendered via reference-matching header legend
      tooltip: {
        backgroundColor: "rgba(255, 255, 255, 0.96)",
        titleColor: "#1f1412",
        bodyColor: "#5a463e",
        borderColor: "rgba(230, 210, 195, 0.9)",
        borderWidth: 1,
        padding: 10,
        boxPadding: 4,
        usePointStyle: true,
        callbacks: {
          title: function (items) {
            if (!items.length) return "";
            const rawTime = items[0].label;
            return "Time: " + rawTime;
          }
        }
      }
    },
    scales: {
      x: {
        grid: { color: "rgba(225, 200, 180, 0.3)" },
        ticks: {
          color: "#736259",
          maxTicksLimit: 7,
          font: { size: 11, family: "'Inter', sans-serif", weight: "500" }
        }
      },
      y: {
        grid: { color: "rgba(225, 200, 180, 0.3)" },
        ticks: {
          color: "#736259",
          font: { size: 11, family: "'Inter', sans-serif", weight: "500" }
        }
      }
    }
  };

  /**
   * Initializes the dual-series Temperature & Humidity line chart and Barometric Pressure chart.
   */
  function initCharts() {
    const tempCtx = document.getElementById("temperatureChart");
    if (tempCtx) {
      tempHumChart = new Chart(tempCtx, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "Temperature (°C)",
              data: [],
              borderColor: "#dc2626",
              backgroundColor: "rgba(220, 38, 38, 0.10)",
              borderWidth: 3,
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
              borderWidth: 3,
              tension: 0.35,
              fill: false,
              pointRadius: 3,
              pointHoverRadius: 6,
              pointBackgroundColor: "#0284c7",
              pointBorderColor: "#ffffff",
              pointBorderWidth: 1.5,
              yAxisID: "yHum"
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 350 },
          interaction: { mode: "index", intersect: false },
          layout: {
            padding: { top: 12, right: 16, bottom: 8, left: 8 }
          },
          plugins: {
            legend: { display: false },
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
                  if (ctx.dataset.yAxisID === "yTemp") {
                    return `Temperature: ${ctx.parsed.y.toFixed(1)} °C`;
                  } else if (ctx.dataset.yAxisID === "yHum") {
                    return `Relative Humidity: ${ctx.parsed.y.toFixed(0)}%`;
                  }
                  return `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`;
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
                maxTicksLimit: 8,
                font: { size: 12, weight: "600", family: "'Inter', sans-serif" }
              }
            },
            yTemp: {
              type: "linear",
              position: "left",
              title: {
                display: true,
                text: "Temperature (°C)",
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

    // Secondary: Atmospheric Pressure Chart
    const pressCtx = document.getElementById("pressureChart");
    if (pressCtx) {
      pressChart = new Chart(pressCtx, {
        type: "line",
        data: {
          labels: [],
          datasets: [{
            label: "Pressure (hPa)",
            data: [],
            borderColor: "#ea580c",
            backgroundColor: "rgba(234, 88, 12, 0.12)",
            borderWidth: 3,
            tension: 0.35,
            fill: true,
            pointRadius: 2,
            pointHoverRadius: 6,
            pointBackgroundColor: "#ea580c"
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 350 },
          interaction: { mode: "index", intersect: false },
          layout: {
            padding: { top: 12, right: 16, bottom: 8, left: 8 }
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "rgba(255, 255, 255, 0.98)",
              titleColor: "#1f1412",
              bodyColor: "#5a463e",
              borderColor: "rgba(230, 210, 195, 0.95)",
              borderWidth: 1.5,
              padding: 12,
              titleFont: { size: 13, weight: "700", family: "'Inter', sans-serif" },
              bodyFont: { size: 13, weight: "600", family: "'Inter', sans-serif" },
              callbacks: {
                title: function (items) {
                  return items.length ? "Timestamp: " + items[0].label : "";
                },
                label: function (ctx) {
                  return `Pressure: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) : '--'} hPa`;
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
                maxTicksLimit: 8,
                font: { size: 12, weight: "600", family: "'Inter', sans-serif" }
              }
            },
            y: {
              title: {
                display: true,
                text: "Atmospheric Pressure (hPa)",
                color: "#ea580c",
                font: { size: 13, weight: "700", family: "'Inter', sans-serif" }
              },
              grid: { color: "rgba(225, 200, 180, 0.35)" },
              ticks: {
                color: "#ea580c",
                font: { size: 12, weight: "600", family: "'Inter', sans-serif" },
                callback: function (val) { return val + " hPa"; }
              }
            }
          }
        }
      });
    }
  }

  /**
   * Fetches latest telemetry and updates cards, condition badges, and honest sensor status.
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
   * Updates all metrics, status indicators, and station diagnostic panels with incoming data.
   */
  function updateDashboardUI(data) {
    const latest = data.latest;
    const previous = data.previous;
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

    // Honest Sensor Connectivity Evaluation
    const isLive = freshness.is_live === true;
    const isStale = freshness.is_stale === true;
    const hasData = latest !== null && latest !== undefined;

    if (conditionsMeta) {
      if (hasData && latest.timestamp) {
        const d = new Date(latest.timestamp);
        conditionsMeta.textContent = `Last updated: ${d.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' })}, ${d.toLocaleTimeString([], { hour12: false })}`;
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
      } else if (alertInfo.has_active_alert || (latest.temperature_c >= (alertInfo.threshold_c || 35.0))) {
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

    // Barometric Pressure Card
    const pressValEl = document.getElementById("cardPressVal");
    const pressTrendBadge = document.getElementById("pressTrendBadge");
    const pressTrendVal = document.getElementById("pressTrendVal");
    if (pressValEl) {
      pressValEl.textContent = hasData && latest.pressure_hpa !== null && latest.pressure_hpa !== undefined ? Number(latest.pressure_hpa).toFixed(1) : "----.-";
    }
    if (pressTrendVal && trend.pressure_delta_hpa !== undefined) {
      pressTrendVal.textContent = Math.abs(trend.pressure_delta_hpa).toFixed(2);
      if (pressTrendBadge) {
        if (trend.pressure_delta_hpa > 0) {
          pressTrendBadge.className = "trend-badge trend-up";
        } else if (trend.pressure_delta_hpa < 0) {
          pressTrendBadge.className = "trend-badge trend-down";
        } else {
          pressTrendBadge.className = "trend-badge trend-neutral";
        }
      }
    }

    // Today's Stats
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

    const pressMinEl = document.getElementById("pressMin");
    const pressAvgEl = document.getElementById("pressAvg");
    const pressMaxEl = document.getElementById("pressMax");
    if (pressMinEl) pressMinEl.textContent = today.min_pressure !== null && today.min_pressure !== undefined ? today.min_pressure.toFixed(1) : "--";
    if (pressAvgEl) pressAvgEl.textContent = today.avg_pressure !== null && today.avg_pressure !== undefined ? today.avg_pressure.toFixed(1) : "--";
    if (pressMaxEl) pressMaxEl.textContent = today.max_pressure !== null && today.max_pressure !== undefined ? today.max_pressure.toFixed(1) : "--";

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

    // Today's count
    const countEl = document.getElementById("cardTodayCount");
    if (countEl) countEl.textContent = today.count || 0;

    const lastColEl = document.getElementById("cardLastCollectionTime");
    if (lastColEl && today.last_collection_time) {
      lastColEl.textContent = new Date(today.last_collection_time).toLocaleTimeString([], { hour12: false });
    }

    // Alert Threshold Form Sync
    if (alertInfo.threshold_c !== undefined) {
      const tThreshEl = document.getElementById("tempThresholdBadge");
      if (tThreshEl) tThreshEl.textContent = `Threshold: ${Number(alertInfo.threshold_c).toFixed(1)}°C`;
      const inThresh = document.getElementById("inputThreshold");
      if (inThresh) inThresh.value = alertInfo.threshold_c;
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
   * Fetches chronological readings and renders the dual-series Temperature & Humidity line chart.
   */
  async function fetchChartData(range) {
    const emptyOverlay = document.getElementById("tempChartEmptyOverlay");
    try {
      const res = await fetch(`/api/readings?range=${encodeURIComponent(range)}`);
      if (!res.ok) throw new Error("Failed to fetch range telemetry");
      const json = await res.json();
      const readings = json.readings || [];

      if (readings.length === 0) {
        if (emptyOverlay) emptyOverlay.classList.remove("d-none");
        if (tempHumChart) {
          tempHumChart.data.labels = [];
          tempHumChart.data.datasets[0].data = [];
          tempHumChart.data.datasets[1].data = [];
          tempHumChart.update();
        }
        if (pressChart) {
          pressChart.data.labels = [];
          pressChart.data.datasets[0].data = [];
          pressChart.update();
        }
        const summarySub = document.getElementById("combinedChartSummary");
        if (summarySub) {
          summarySub.textContent = `No real samples recorded in last ${range} • Awaiting incoming sensor telemetry`;
        }
        return;
      }

      if (emptyOverlay) emptyOverlay.classList.add("d-none");

      // Format timestamps into clean, readable X-axis labels
      const isMultiDay = (range === "7d" || range === "30d");
      const labels = readings.map((r) => {
        const d = new Date(r.timestamp);
        if (isMultiDay) {
          return `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}`;
        }
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
      });

      const tempData = readings.map((r) => (r.temperature_c !== null ? Number(r.temperature_c) : null));
      const humData = readings.map((r) => (r.humidity_pct !== null && r.humidity_pct !== undefined ? Number(r.humidity_pct) : null));
      const pressData = readings.map((r) => (r.pressure_hpa !== null ? Number(r.pressure_hpa) : null));

      if (tempHumChart) {
        tempHumChart.data.labels = labels;
        tempHumChart.data.datasets[0].data = tempData;
        tempHumChart.data.datasets[1].data = humData;
        tempHumChart.update();
      }

      if (pressChart) {
        pressChart.data.labels = labels;
        pressChart.data.datasets[0].data = pressData;
        pressChart.update();
      }

      // Update Summary Subtext
      const summarySub = document.getElementById("combinedChartSummary");
      if (summarySub && json.summary) {
        summarySub.textContent = `${readings.length} real samples recorded in last ${range} • Turso / SQLite telemetry pipeline`;
      }
    } catch (e) {
      console.warn("Could not refresh charts:", e);
      if (emptyOverlay) emptyOverlay.classList.remove("d-none");
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
        const pVal = r.pressure_hpa !== null ? Number(r.pressure_hpa).toFixed(1) + " hPa" : "--";
        const hiVal = r.heat_index_c !== null && r.heat_index_c !== undefined ? Number(r.heat_index_c).toFixed(1) + " °C" : "--";
        const srcBadge = r.source && r.source.includes("dht11") ? `<span class="badge bg-success bg-opacity-10 text-success">${r.source}</span>` : `<span class="badge bg-light text-muted">${r.source || 'sensor'}</span>`;
        return `
          <tr>
            <td><strong>${timeStr}</strong></td>
            <td style="color: #ef4444; font-weight: 600;">${tVal}</td>
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

  // Setup Event Listeners
  function setupListeners() {
    // Range selector buttons for Combined Chart
    const rangeBtns = document.querySelectorAll("#tempRangeSelector button");
    rangeBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        rangeBtns.forEach((b) => b.classList.remove("active"));
        this.classList.add("active");
        currentRange = this.getAttribute("data-range") || "24h";
        fetchChartData(currentRange);
      });
    });

    // Range selector for Pressure Chart
    const pressBtns = document.querySelectorAll("#pressRangeSelector button");
    pressBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        pressBtns.forEach((b) => b.classList.remove("active"));
        this.classList.add("active");
        currentPressRange = this.getAttribute("data-range") || "24h";
        fetchChartData(currentPressRange);
      });
    });

    // Immediate Refresh Button in Header
    const btnRefresh = document.getElementById("btnRefreshNow");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => {
        fetchLatestData();
        fetchChartData(currentRange);
        fetchRecentTable();
      });
    }

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
            if (feedback) feedback.innerHTML = `<span class="text-success fw-semibold">Threshold updated to ${val.toFixed(1)}°C</span>`;
            setTimeout(() => { if (feedback) feedback.innerHTML = ""; }, 4000);
            fetchLatestData();
          } else {
            if (feedback) feedback.innerHTML = `<span class="text-danger">${resData.error || 'Failed to update threshold'}</span>`;
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
    setupListeners();
    fetchLatestData();
    fetchChartData(currentRange);
    fetchRecentTable();

    // Auto-refresh polling every 10 seconds
    autoRefreshTimer = setInterval(() => {
      fetchLatestData();
      fetchRecentTable();
    }, 10000);

    // Refresh charts every 60 seconds
    setInterval(() => {
      fetchChartData(currentRange);
    }, 60000);
  });
})();
