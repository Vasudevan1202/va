/**
 * Virtual Atmosphere - Overview Dashboard Controller
 */

(function () {
  "use strict";

  let tempChart = null;
  let pressChart = null;
  let currentTempRange = "24h";
  let currentPressRange = "24h";

  // Chart configuration constants
  const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    interaction: {
      mode: "index",
      intersect: false
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "rgba(16, 38, 58, 0.95)",
        titleColor: "#51D8FF",
        bodyColor: "#FFFFFF",
        borderColor: "#243B50",
        borderWidth: 1,
        padding: 10,
        displayColors: false,
        callbacks: {
          title: function (items) {
            if (!items.length) return "";
            const d = new Date(items[0].raw.x);
            return d.toLocaleTimeString([], { hour12: false }) + " (" + d.toLocaleDateString() + ")";
          }
        }
      }
    },
    scales: {
      x: {
        type: "category",
        grid: { color: "rgba(36, 59, 80, 0.4)" },
        ticks: {
          color: "#91A9BF",
          maxTicksLimit: 8,
          font: { size: 11 }
        }
      },
      y: {
        grid: { color: "rgba(36, 59, 80, 0.4)" },
        ticks: {
          color: "#91A9BF",
          font: { size: 11 }
        }
      }
    }
  };

  function initCharts() {
    // Temperature Chart
    const tempCtx = document.getElementById("temperatureChart");
    if (tempCtx) {
      tempChart = new Chart(tempCtx, {
        type: "line",
        data: {
          labels: [],
          datasets: [{
            label: "Temperature (°C)",
            data: [],
            borderColor: "#51D8FF",
            backgroundColor: "rgba(81, 216, 255, 0.12)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 1,
            pointHoverRadius: 5
          }]
        },
        options: {
          ...CHART_DEFAULTS,
          plugins: {
            ...CHART_DEFAULTS.plugins,
            tooltip: {
              ...CHART_DEFAULTS.plugins.tooltip,
              callbacks: {
                ...CHART_DEFAULTS.plugins.tooltip.callbacks,
                label: function (ctx) {
                  return `Temperature: ${ctx.parsed.y.toFixed(2)} °C`;
                }
              }
            }
          }
        }
      });
    }

    // Atmospheric Pressure Chart
    const pressCtx = document.getElementById("pressureChart");
    if (pressCtx) {
      pressChart = new Chart(pressCtx, {
        type: "line",
        data: {
          labels: [],
          datasets: [{
            label: "Pressure (hPa)",
            data: [],
            borderColor: "#1677FF",
            backgroundColor: "rgba(22, 119, 255, 0.12)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 1,
            pointHoverRadius: 5
          }]
        },
        options: {
          ...CHART_DEFAULTS,
          plugins: {
            ...CHART_DEFAULTS.plugins,
            tooltip: {
              ...CHART_DEFAULTS.plugins.tooltip,
              callbacks: {
                ...CHART_DEFAULTS.plugins.tooltip.callbacks,
                label: function (ctx) {
                  return `Pressure: ${ctx.parsed.y.toFixed(2)} hPa`;
                }
              }
            }
          }
        }
      });
    }
  }

  function fetchLatestReadings() {
    fetch("/api/readings/latest")
      .then(res => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(data => {
        const latest = data.latest;
        const trend = data.trend || {};
        const today = data.today_stats || {};
        const sensor = data.sensor || {};
        const alertInfo = data.alert || {};

        const tempEl = document.getElementById("cardTempVal");
        const pressEl = document.getElementById("cardPressVal");
        if (tempEl) tempEl.classList.remove("va-skeleton", "skeleton-metric");
        if (pressEl) pressEl.classList.remove("va-skeleton", "skeleton-metric");

        if (latest) {
          // Temperature Card
          if (tempEl) tempEl.textContent = latest.temperature_c.toFixed(1);
          const tDelta = trend.temperature_delta_c || 0;
          const tBadge = document.getElementById("tempTrendBadge");
          const tVal = document.getElementById("tempTrendVal");
          if (tVal) tVal.textContent = Math.abs(tDelta).toFixed(2);

          if (tBadge) {
            if (tDelta > 0.05) {
              tBadge.className = "trend-badge trend-up";
              tBadge.firstElementChild.textContent = "▲";
            } else if (tDelta < -0.05) {
              tBadge.className = "trend-badge trend-down";
              tBadge.firstElementChild.textContent = "▼";
            } else {
              tBadge.className = "trend-badge trend-neutral";
              tBadge.firstElementChild.textContent = "–";
            }
          }

          // Pressure Card
          if (pressEl) pressEl.textContent = latest.pressure_hpa.toFixed(1);
          const pDelta = trend.pressure_delta_hpa || 0;
          const pBadge = document.getElementById("pressTrendBadge");
          const pVal = document.getElementById("pressTrendVal");
          if (pVal) pVal.textContent = Math.abs(pDelta).toFixed(2);

          if (pBadge) {
            if (pDelta > 0.1) {
              pBadge.className = "trend-badge trend-up";
              pBadge.firstElementChild.textContent = "▲";
            } else if (pDelta < -0.1) {
              pBadge.className = "trend-badge trend-down";
              pBadge.firstElementChild.textContent = "▼";
            } else {
              pBadge.className = "trend-badge trend-neutral";
              pBadge.firstElementChild.textContent = "–";
            }
          }
        } else {
          // No readings yet
          if (tempEl) tempEl.textContent = "--.-";
          if (pressEl) pressEl.textContent = "----.-";
        }

        // Today's Stats
        document.getElementById("tempMin").textContent = today.min_temp !== null ? today.min_temp.toFixed(1) + "°" : "--";
        document.getElementById("tempAvg").textContent = today.avg_temp !== null ? today.avg_temp.toFixed(1) + "°" : "--";
        document.getElementById("tempMax").textContent = today.max_temp !== null ? today.max_temp.toFixed(1) + "°" : "--";

        document.getElementById("pressMin").textContent = today.min_pressure !== null ? today.min_pressure.toFixed(1) : "--";
        document.getElementById("pressAvg").textContent = today.avg_pressure !== null ? today.avg_pressure.toFixed(1) : "--";
        document.getElementById("pressMax").textContent = today.max_pressure !== null ? today.max_pressure.toFixed(1) : "--";

        document.getElementById("cardTodayCount").textContent = today.count || 0;
        document.getElementById("cardLastCollectionTime").textContent = today.last_collection_time
          ? new Date(today.last_collection_time).toLocaleTimeString([], { hour12: false })
          : "--:--:--";

        // Sensor Card
        const sensorPill = document.getElementById("cardSensorStatusPill");
        const sensorText = document.getElementById("cardSensorStatusText");
        if (sensor.mode === "demo") {
          sensorPill.className = "status-pill demo py-1 px-2";
          sensorText.textContent = "Demo Simulated";
          document.getElementById("cardRecordMode").textContent = "Simulated";
        } else if (sensor.is_connected) {
          sensorPill.className = "status-pill online py-1 px-2";
          sensorText.textContent = "Online";
          document.getElementById("cardRecordMode").textContent = "Live I²C";
        } else {
          sensorPill.className = "status-pill offline py-1 px-2";
          sensorText.textContent = "Offline";
          document.getElementById("cardRecordMode").textContent = "Offline";
        }

        document.getElementById("cardSensorAddress").textContent = sensor.address || "I²C Bus 1";
        document.getElementById("cardDataFreshness").textContent = sensor.data_freshness_seconds !== null ? sensor.data_freshness_seconds + "s ago" : "--";
        document.getElementById("cardLastReadingTime").textContent = sensor.last_reading_time
          ? new Date(sensor.last_reading_time).toLocaleTimeString([], { hour12: false })
          : "--:--:--";

        // Alert Threshold Badge
        if (alertInfo.threshold_c !== undefined) {
          document.getElementById("tempThresholdBadge").textContent = `Threshold: ${alertInfo.threshold_c.toFixed(1)}°C`;
          document.getElementById("inputThreshold").value = alertInfo.threshold_c;
        }

        // Thermal amplitude & Baro delta
        if (today.max_temp !== null && today.min_temp !== null) {
          const amp = (today.max_temp - today.min_temp).toFixed(1);
          document.getElementById("summaryThermalAmplitude").textContent = `${amp} °C`;
        }
        if (today.max_pressure !== null && today.min_pressure !== null) {
          const bDelta = (today.max_pressure - today.min_pressure).toFixed(1);
          document.getElementById("summaryBaroDelta").textContent = `±${bDelta} hPa`;
        }
      })
      .catch(err => console.error("Error fetching latest telemetry:", err));
  }

  function fetchChartData(chartType, range) {
    const selectorId = chartType === "temp" ? "tempRangeSelector" : "pressRangeSelector";
    const group = document.getElementById(selectorId);
    const summaryEl = document.getElementById(chartType === "temp" ? "tempChartSummary" : "pressChartSummary");

    if (group) {
      group.querySelectorAll("button").forEach(b => b.disabled = true);
    }
    if (summaryEl) {
      summaryEl.innerHTML = `<span class="va-spinner va-spinner-sm me-1" aria-hidden="true"></span> Loading ${range} data…`;
    }

    fetch(`/api/readings?range=${range}`)
      .then(res => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(data => {
        const readings = data.readings || [];
        const summary = data.summary || {};

        const labels = readings.map(r => {
          const d = new Date(r.timestamp);
          return range === "7d" || range === "30d"
            ? (d.getMonth() + 1) + "/" + d.getDate() + " " + d.getHours() + "h"
            : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
        });

        if (chartType === "temp" && tempChart) {
          const values = readings.map(r => r.temperature_c);
          tempChart.data.labels = labels;
          tempChart.data.datasets[0].data = values;
          tempChart.update();

          if (summaryEl) {
            summaryEl.textContent = summary.count > 0
              ? `${summary.count} readings | Min: ${summary.temp_min}°C | Max: ${summary.temp_max}°C | Avg: ${summary.temp_avg}°C`
              : "No readings recorded in this range.";
          }
        } else if (chartType === "press" && pressChart) {
          const values = readings.map(r => r.pressure_hpa);
          pressChart.data.labels = labels;
          pressChart.data.datasets[0].data = values;
          pressChart.update();

          if (summaryEl) {
            summaryEl.textContent = summary.count > 0
              ? `${summary.count} readings | Min: ${summary.press_min} hPa | Max: ${summary.press_max} hPa | Avg: ${summary.press_avg} hPa`
              : "No readings recorded in this range.";
          }
        }
      })
      .catch(err => {
        console.error("Error loading chart data:", err);
        if (summaryEl) {
          summaryEl.textContent = "Error loading chart records. Select another interval to retry.";
        }
      })
      .finally(() => {
        if (group) {
          group.querySelectorAll("button").forEach(b => b.disabled = false);
        }
      });
  }

  function fetchRecentTable() {
    fetch("/api/readings/history?limit=10")
      .then(res => res.json())
      .then(data => {
        const tbody = document.getElementById("recentReadingsTbody");
        if (!tbody) return;

        const readings = data.readings || [];
        if (readings.length === 0) {
          tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-secondary">No records collected yet.</td></tr>`;
          return;
        }

        tbody.innerHTML = readings.map(r => `
          <tr>
            <td>${new Date(r.timestamp).toLocaleString()}</td>
            <td><strong>${r.temperature_c.toFixed(2)} °C</strong></td>
            <td><strong>${r.pressure_hpa.toFixed(2)} hPa</strong></td>
            <td><span class="badge-tag ${r.source}">${r.source}</span></td>
            <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
          </tr>
        `).join("");
      })
      .catch(err => console.error("Recent table error:", err));
  }

  function setupRangeSelectors() {
    // Temperature Range Buttons
    const tempGroup = document.getElementById("tempRangeSelector");
    if (tempGroup) {
      tempGroup.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", function () {
          tempGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
          this.classList.add("active");
          currentTempRange = this.getAttribute("data-range");
          fetchChartData("temp", currentTempRange);
        });
      });
    }

    // Pressure Range Buttons
    const pressGroup = document.getElementById("pressRangeSelector");
    if (pressGroup) {
      pressGroup.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", function () {
          pressGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
          this.classList.add("active");
          currentPressRange = this.getAttribute("data-range");
          fetchChartData("press", currentPressRange);
        });
      });
    }
  }

  function setupThresholdForm() {
    const form = document.getElementById("formThresholdConfig");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const input = document.getElementById("inputThreshold");
        const submitBtn = form.querySelector('button[type="submit"]');
        const feedback = document.getElementById("thresholdFeedback");
        const thresholdVal = parseFloat(input.value);

        if (window.VA && window.VA.setBtnLoading) {
          window.VA.setBtnLoading(submitBtn, true, "Saving…");
        }
        input.disabled = true;

        fetch("/api/settings/threshold", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ threshold_c: thresholdVal })
        })
          .then(res => res.json())
          .then(data => {
            if (data.success) {
              feedback.className = "small mt-2 text-success";
              feedback.textContent = data.message;
              if (window.VA && window.VA.announce) {
                window.VA.announce(data.message);
              }
              fetchLatestReadings();
            } else {
              feedback.className = "small mt-2 text-danger";
              feedback.textContent = data.error;
            }
          })
          .catch(err => {
            feedback.className = "small mt-2 text-danger";
            feedback.textContent = "Failed to update threshold. Please retry.";
          })
          .finally(() => {
            input.disabled = false;
            if (window.VA && window.VA.setBtnLoading) {
              window.VA.setBtnLoading(submitBtn, false);
            }
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    initCharts();
    setupRangeSelectors();
    setupThresholdForm();

    fetchLatestReadings();
    fetchChartData("temp", currentTempRange);
    fetchChartData("press", currentPressRange);
    fetchRecentTable();

    // Hook into global VA update cycle
    window.VA.onUpdate(function () {
      fetchLatestReadings();
      fetchChartData("temp", currentTempRange);
      fetchChartData("press", currentPressRange);
      fetchRecentTable();
    });
  });
})();
