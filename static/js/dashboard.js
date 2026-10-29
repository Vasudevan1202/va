/**
 * Virtual Atmosphere - Overview Dashboard Controller
 * Extended with Hyperlocal Weather Station & Heat-Risk Intelligence
 */

(function () {
  "use strict";

  let tempChart = null;
  let humChart = null;
  let pressChart = null;
  let currentTempRange = "24h";
  let currentHumRange = "24h";
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
            const d = new Date(items[0].raw.x || items[0].label);
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
    // 1. Temperature Chart
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
                  return `Temperature: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '--'} °C`;
                }
              }
            }
          }
        }
      });
    }

    // 2. Relative Humidity Chart
    const humCtx = document.getElementById("humidityChart");
    if (humCtx) {
      humChart = new Chart(humCtx, {
        type: "line",
        data: {
          labels: [],
          datasets: [{
            label: "Relative Humidity (%)",
            data: [],
            borderColor: "#32D583",
            backgroundColor: "rgba(50, 213, 131, 0.12)",
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
                  return `Relative Humidity: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) : '--'} %`;
                }
              }
            }
          },
          scales: {
            ...CHART_DEFAULTS.scales,
            y: {
              ...CHART_DEFAULTS.scales.y,
              min: 0,
              max: 100,
              ticks: {
                ...CHART_DEFAULTS.scales.y.ticks,
                callback: function (val) {
                  return val + "%";
                }
              }
            }
          }
        }
      });
    }

    // 3. Atmospheric Pressure Chart
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
                  return `Pressure: ${ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '--'} hPa`;
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
        const heatRisk = data.heat_risk;

        const tempEl = document.getElementById("cardTempVal");
        const humEl = document.getElementById("cardHumidityVal");
        const pressEl = document.getElementById("cardPressVal");
        if (tempEl) tempEl.classList.remove("va-skeleton", "skeleton-metric");
        if (humEl) humEl.classList.remove("va-skeleton", "skeleton-metric");
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

          // Relative Humidity Card
          const humVal = (latest.humidity_pct !== null && latest.humidity_pct !== undefined)
            ? latest.humidity_pct
            : (data.dht11 && (data.dht11.humidity_percent !== undefined ? data.dht11.humidity_percent : data.dht11.humidity_pct));

          if (humEl) {
            if (humVal !== null && humVal !== undefined) {
              humEl.textContent = Number(humVal).toFixed(1);
              const hDelta = trend.humidity_delta_pct || 0;
              const hBadge = document.getElementById("humTrendBadge");
              const hVal = document.getElementById("humTrendVal");
              if (hVal) hVal.textContent = Math.abs(hDelta).toFixed(1);

              if (hBadge) {
                if (hDelta > 0.5) {
                  hBadge.className = "trend-badge trend-up";
                  hBadge.firstElementChild.textContent = "▲";
                } else if (hDelta < -0.5) {
                  hBadge.className = "trend-badge trend-down";
                  hBadge.firstElementChild.textContent = "▼";
                } else {
                  hBadge.className = "trend-badge trend-neutral";
                  hBadge.firstElementChild.textContent = "–";
                }
              }
            } else {
              humEl.textContent = "--.-";
            }
          }

          // Pressure Card (BMP280 barometer)
          const pressVal = (latest.pressure_hpa !== null && latest.pressure_hpa !== undefined)
            ? latest.pressure_hpa
            : (data.bmp280 && data.bmp280.pressure_hpa !== null && data.bmp280.pressure_hpa !== undefined
              ? data.bmp280.pressure_hpa
              : null);

          if (pressEl) {
            pressEl.textContent = (pressVal !== null) ? pressVal.toFixed(1) : "----.-";
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
          }

          // Heat-Risk Assessment Card
          const hiEl = document.getElementById("cardHeatIndexVal");
          const hiBadge = document.getElementById("cardHeatRiskBadge");
          const hiAdvisory = document.getElementById("cardHeatRiskAdvisory");
          const hiBasis = document.getElementById("cardHeatRiskBasis");
          const hiUnit = document.getElementById("cardHeatIndexUnit");

          if (heatRisk) {
            if (hiBadge) {
              hiBadge.className = `badge bg-${heatRisk.badge_class || 'secondary'}`;
              hiBadge.textContent = heatRisk.category || "Normal";
            }
            if (hiEl) {
              if (heatRisk.heat_index_c !== null && heatRisk.heat_index_c !== undefined) {
                hiEl.textContent = heatRisk.heat_index_c.toFixed(1);
                if (hiUnit) hiUnit.style.display = "inline";
              } else {
                hiEl.textContent = heatRisk.category === "Normal" ? "Normal" : "--";
                if (hiUnit) hiUnit.style.display = heatRisk.category === "Normal" ? "none" : "inline";
              }
            }
            if (hiAdvisory) {
              hiAdvisory.textContent = heatRisk.advisory || "Ambient conditions within baseline comfort.";
            }
            if (hiBasis) {
              hiBasis.textContent = heatRisk.formula_basis || "NOAA / NWS Heat Risk criteria";
              hiBasis.title = heatRisk.formula_basis || "";
            }
          } else if (latest.heat_index_c !== null && latest.heat_index_c !== undefined) {
            if (hiEl) {
              hiEl.textContent = latest.heat_index_c.toFixed(1);
              if (hiUnit) hiUnit.style.display = "inline";
            }
            if (hiBadge) {
              hiBadge.className = "badge bg-warning";
              hiBadge.textContent = "Elevated";
            }
          } else {
            if (hiEl) {
              hiEl.textContent = "--.-";
              if (hiUnit) hiUnit.style.display = "inline";
            }
            if (hiBadge) {
              hiBadge.className = "badge bg-secondary";
              hiBadge.textContent = "Awaiting";
            }
          }

          // GPS Coordinates Card
          const gpsCoords = document.getElementById("cardGpsCoords");
          const gpsStatus = document.getElementById("cardGpsStatus");
          const statLat = document.getElementById("statLat");
          const statLon = document.getElementById("statLon");
          const gpsMeta = document.getElementById("cardGpsMeta");

          if (latest.latitude !== null && latest.latitude !== undefined &&
              latest.longitude !== null && latest.longitude !== undefined) {
            const latStr = `${Math.abs(latest.latitude).toFixed(4)}° ${latest.latitude >= 0 ? 'N' : 'S'}`;
            const lonStr = `${Math.abs(latest.longitude).toFixed(4)}° ${latest.longitude >= 0 ? 'E' : 'W'}`;
            if (gpsCoords) gpsCoords.textContent = `${latStr}, ${lonStr}`;
            if (statLat) statLat.textContent = latStr;
            if (statLon) statLon.textContent = lonStr;
            if (gpsStatus) {
              gpsStatus.className = "badge bg-success";
              gpsStatus.textContent = "GPS Locked";
            }
            if (gpsMeta) gpsMeta.textContent = "Hyperlocal GPS telemetry active";
          } else {
            if (gpsCoords) gpsCoords.textContent = "Station Fix Standby";
            if (statLat) statLat.textContent = "--";
            if (statLon) statLon.textContent = "--";
            if (gpsStatus) {
              gpsStatus.className = "badge bg-secondary";
              gpsStatus.textContent = "Awaiting Fix";
            }
            if (gpsMeta) gpsMeta.textContent = "u-blox NEO-6M receiver awaiting satellite fix";
          }

        } else {
          // No readings yet
          if (tempEl) tempEl.textContent = "--.-";
          if (humEl) humEl.textContent = "--.-";
          if (pressEl) pressEl.textContent = "----.-";
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
        if (humMinEl) humMinEl.textContent = today.min_humidity !== null && today.min_humidity !== undefined ? today.min_humidity.toFixed(1) + "%" : "--";
        if (humAvgEl) humAvgEl.textContent = today.avg_humidity !== null && today.avg_humidity !== undefined ? today.avg_humidity.toFixed(1) + "%" : "--";
        if (humMaxEl) humMaxEl.textContent = today.max_humidity !== null && today.max_humidity !== undefined ? today.max_humidity.toFixed(1) + "%" : "--";

        const pressMinEl = document.getElementById("pressMin");
        const pressAvgEl = document.getElementById("pressAvg");
        const pressMaxEl = document.getElementById("pressMax");
        if (pressMinEl) pressMinEl.textContent = today.min_pressure !== null && today.min_pressure !== undefined ? today.min_pressure.toFixed(1) : "--";
        if (pressAvgEl) pressAvgEl.textContent = today.avg_pressure !== null && today.avg_pressure !== undefined ? today.avg_pressure.toFixed(1) : "--";
        if (pressMaxEl) pressMaxEl.textContent = today.max_pressure !== null && today.max_pressure !== undefined ? today.max_pressure.toFixed(1) : "--";

        const countEl = document.getElementById("cardTodayCount");
        if (countEl) countEl.textContent = today.count || 0;

        const lastColEl = document.getElementById("cardLastCollectionTime");
        if (lastColEl) {
          lastColEl.textContent = today.last_collection_time
            ? new Date(today.last_collection_time).toLocaleTimeString([], { hour12: false })
            : "--:--:--";
        }

        // Sensor & Active Source Card
        const sensorPill = document.getElementById("cardSensorStatusPill");
        const sensorText = document.getElementById("cardSensorStatusText");
        const recordMode = document.getElementById("cardRecordMode");
        const activeSource = (latest && latest.source) ? latest.source : (sensor.data_source || sensor.mode);

        if (activeSource === "hardware" && sensor.is_connected) {
          if (sensorPill) sensorPill.className = "status-pill online py-1 px-2";
          if (sensorText) sensorText.textContent = "Hardware Station";
          if (recordMode) recordMode.textContent = "Live Hardware";
        } else if (activeSource === "simulated" || activeSource === "demo") {
          if (sensorPill) sensorPill.className = "status-pill simulated py-1 px-2";
          if (sensorText) sensorText.textContent = "Simulated Test Data";
          if (recordMode) recordMode.textContent = "Simulated";
        } else {
          if (sensorPill) sensorPill.className = "status-pill unavailable py-1 px-2";
          if (sensorText) sensorText.textContent = "Hardware Unavailable";
          if (recordMode) recordMode.textContent = "Offline";
        }

        const modelEl = document.getElementById("cardSensorModel");
        if (modelEl) modelEl.textContent = sensor.sensor_type || "BME280";

        const addrEl = document.getElementById("cardSensorAddress");
        if (addrEl) addrEl.textContent = sensor.address || "I²C Bus 1";

        const freshEl = document.getElementById("cardDataFreshness");
        if (freshEl) freshEl.textContent = sensor.data_freshness_seconds !== null && sensor.data_freshness_seconds !== undefined ? sensor.data_freshness_seconds + "s ago" : "--";

        const lastReadEl = document.getElementById("cardLastReadingTime");
        if (lastReadEl) {
          lastReadEl.textContent = sensor.last_reading_time
            ? new Date(sensor.last_reading_time).toLocaleTimeString([], { hour12: false })
            : "--:--:--";
        }

        // Alert Threshold Badge
        if (alertInfo.threshold_c !== undefined) {
          const tThreshEl = document.getElementById("tempThresholdBadge");
          if (tThreshEl) tThreshEl.textContent = `Threshold: ${alertInfo.threshold_c.toFixed(1)}°C`;
          const inThresh = document.getElementById("inputThreshold");
          if (inThresh) inThresh.value = alertInfo.threshold_c;
        }

        // Thermal amplitude & Baro delta
        const thermAmp = document.getElementById("summaryThermalAmplitude");
        if (thermAmp && today.max_temp !== null && today.min_temp !== null && today.max_temp !== undefined && today.min_temp !== undefined) {
          const amp = (today.max_temp - today.min_temp).toFixed(1);
          thermAmp.textContent = `${amp} °C`;
        }
        const baroDelta = document.getElementById("summaryBaroDelta");
        if (baroDelta && today.max_pressure !== null && today.min_pressure !== null && today.max_pressure !== undefined && today.min_pressure !== undefined) {
          const bDelta = (today.max_pressure - today.min_pressure).toFixed(1);
          baroDelta.textContent = `±${bDelta} hPa`;
        }

        // Dedicated DHT11 Metrics Card
        const dht = data.dht11 || (latest && (latest.sensor_type === 'dht11' || (latest.source && latest.source.includes('dht11'))) ? latest : null);
        const dhtTempVal = document.getElementById("dht11TempVal");
        const dhtHumVal = document.getElementById("dht11HumVal");
        const dhtSource = document.getElementById("dht11Source");
        const dhtLastUpdated = document.getElementById("dht11LastUpdated");
        const dhtStatusPill = document.getElementById("dht11StatusPill");
        const dhtStatusText = document.getElementById("dht11StatusText");

        if (dht) {
          if (dhtTempVal) dhtTempVal.textContent = (dht.temperature_c !== null && dht.temperature_c !== undefined) ? Number(dht.temperature_c).toFixed(1) : "--.-";
          const hVal = dht.humidity_percent !== undefined ? dht.humidity_percent : dht.humidity_pct;
          if (dhtHumVal) dhtHumVal.textContent = (hVal !== null && hVal !== undefined) ? Number(hVal).toFixed(1) : "--.-";
          if (dhtSource) {
            dhtSource.textContent = dht.source || "dht11";
            dhtSource.title = `Source: ${dht.source || "dht11"}`;
          }
          const dhtTime = dht.timestamp ? new Date(dht.timestamp) : null;
          if (dhtLastUpdated) {
            dhtLastUpdated.textContent = dhtTime
              ? dhtTime.toLocaleTimeString([], { hour12: false })
              : "--:--:--";
            if (dhtTime) dhtLastUpdated.title = dhtTime.toISOString();
          }

          if (dhtStatusPill) {
            const ageSec = dhtTime ? (Date.now() - dhtTime.getTime()) / 1000 : 999999;
            if (ageSec < 180) {
              dhtStatusPill.className = "status-pill online py-1 px-2";
              if (dhtStatusText) dhtStatusText.textContent = "Ingesting";
            } else if (ageSec < 3600) {
              dhtStatusPill.className = "status-pill demo py-1 px-2";
              if (dhtStatusText) dhtStatusText.textContent = "Standby";
            } else {
              dhtStatusPill.className = "status-pill unavailable py-1 px-2";
              if (dhtStatusText) dhtStatusText.textContent = "Idle";
            }
          }
        }

        // Storage & Cloud Persistence Diagnostic
        const storageEl = document.getElementById("cardStorageStatus");
        const dbStats = data.database;
        if (storageEl && dbStats) {
          if (dbStats.storage_backend === "turso") {
            storageEl.textContent = "Turso libSQL (Durable Cloud)";
            storageEl.className = "text-success fw-semibold";
          } else if (dbStats.storage_backend === "postgres") {
            storageEl.textContent = "PostgreSQL (Durable Cloud)";
            storageEl.className = "text-success fw-semibold";
          } else if (dbStats.is_persistent === false) {
            storageEl.textContent = "SQLite (/tmp Ephemeral)";
            storageEl.className = "text-warning fw-semibold";
            storageEl.title = dbStats.persistence_notice || "Ephemeral serverless storage: records will reset on container cold starts.";
          } else {
            storageEl.textContent = "SQLite WAL";
            storageEl.className = "text-white";
          }
        }
      })
      .catch(err => console.error("Error fetching latest telemetry:", err));
  }

  function fetchChartData(chartType, range) {
    let selectorId = "tempRangeSelector";
    let summaryId = "tempChartSummary";
    if (chartType === "hum") {
      selectorId = "humRangeSelector";
      summaryId = "humChartSummary";
    } else if (chartType === "press") {
      selectorId = "pressRangeSelector";
      summaryId = "pressChartSummary";
    }

    const group = document.getElementById(selectorId);
    const summaryEl = document.getElementById(summaryId);

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
            summaryEl.textContent = summary.count > 0 && summary.temp_min !== null
              ? `${summary.count} readings | Min: ${summary.temp_min}°C | Max: ${summary.temp_max}°C | Avg: ${summary.temp_avg}°C`
              : "No readings recorded in this range.";
          }
        } else if (chartType === "hum" && humChart) {
          const values = readings.map(r => (r.humidity_pct !== null && r.humidity_pct !== undefined ? r.humidity_pct : null));
          humChart.data.labels = labels;
          humChart.data.datasets[0].data = values;
          humChart.update();

          if (summaryEl) {
            summaryEl.textContent = summary.count > 0 && summary.hum_min !== null
              ? `${summary.count} readings | Min: ${summary.hum_min}% | Max: ${summary.hum_max}% | Avg: ${summary.hum_avg}%`
              : "No humidity readings recorded in this range.";
          }
        } else if (chartType === "press" && pressChart) {
          const values = readings.map(r => r.pressure_hpa);
          pressChart.data.labels = labels;
          pressChart.data.datasets[0].data = values;
          pressChart.update();

          if (summaryEl) {
            summaryEl.textContent = summary.count > 0 && summary.press_min !== null
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
          tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-secondary">No records collected yet.</td></tr>`;
          return;
        }

        tbody.innerHTML = readings.map(r => {
          const humText = (r.humidity_pct !== null && r.humidity_pct !== undefined) ? `${r.humidity_pct.toFixed(1)} %` : `<span class="text-secondary">–</span>`;
          const pressText = (r.pressure_hpa !== null && r.pressure_hpa !== undefined) ? `${r.pressure_hpa.toFixed(2)} hPa` : `<span class="text-secondary">–</span>`;
          return `
            <tr>
              <td>${new Date(r.timestamp).toLocaleString()}</td>
              <td><strong>${r.temperature_c.toFixed(2)} °C</strong></td>
              <td><strong>${humText}</strong></td>
              <td><strong>${pressText}</strong></td>
              <td>${hiText}</td>
              <td><span class="badge-tag ${r.source}">${r.source}</span></td>
              <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
            </tr>
          `;
        }).join("");
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

    // Humidity Range Buttons
    const humGroup = document.getElementById("humRangeSelector");
    if (humGroup) {
      humGroup.querySelectorAll("button").forEach(btn => {
        btn.addEventListener("click", function () {
          humGroup.querySelectorAll("button").forEach(b => b.classList.remove("active"));
          this.classList.add("active");
          currentHumRange = this.getAttribute("data-range");
          fetchChartData("hum", currentHumRange);
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
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": window.VA_CSRF_TOKEN || ""
          },
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
    fetchChartData("hum", currentHumRange);
    fetchChartData("press", currentPressRange);
    fetchRecentTable();

    // Hook into global VA update cycle
    window.VA.onUpdate(function () {
      fetchLatestReadings();
      fetchChartData("temp", currentTempRange);
      fetchChartData("hum", currentHumRange);
      fetchChartData("press", currentPressRange);
      fetchRecentTable();
    });
  });
})();
