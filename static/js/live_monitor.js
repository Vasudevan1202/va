/**
 * Virtual Atmosphere - Live Monitor Telemetry Controller
 */

(function () {
  "use strict";

  const streamRecords = [];
  const MAX_STREAM_ROWS = 20;

  function updateLiveReadings() {
    fetch("/api/readings/latest")
      .then(r => r.json())
      .then(data => {
        const latest = data.latest;
        const sensor = data.sensor || {};
        const alertInfo = data.alert || {};

        if (latest) {
          document.getElementById("liveTempVal").textContent = latest.temperature_c.toFixed(1);
          document.getElementById("livePressVal").textContent = latest.pressure_hpa.toFixed(1);

          // Threshold info
          if (alertInfo.threshold_c) {
            document.getElementById("liveTempThresholdInfo").textContent = `Threshold: ${alertInfo.threshold_c.toFixed(1)}°C`;
            const tempStatus = document.getElementById("liveTempStatus");
            const tempStatusText = document.getElementById("liveTempStatusText");

            if (latest.temperature_c >= alertInfo.threshold_c) {
              tempStatus.className = "status-pill offline";
              tempStatusText.textContent = "WARNING: Elevated Temperature";
            } else {
              tempStatus.className = "status-pill online";
              tempStatusText.textContent = "Normal Safe Range";
            }
          }

          // Barometric scale
          const pressStatusText = document.getElementById("livePressStatusText");
          if (latest.pressure_hpa > 1020) {
            pressStatusText.textContent = "High Pressure (Anticyclone)";
          } else if (latest.pressure_hpa < 1005) {
            pressStatusText.textContent = "Low Pressure (Cyclone/Depression)";
          } else {
            pressStatusText.textContent = "Nominal Barometric Range";
          }

          // Add to stream log if unique
          if (!streamRecords.some(r => r.id === latest.id)) {
            streamRecords.unshift(latest);
            if (streamRecords.length > MAX_STREAM_ROWS) {
              streamRecords.pop();
            }
            renderStreamTable();
          }
        }

        // Diagnostics
        const diagPill = document.getElementById("diagSensorPill");
        const diagStatusText = document.getElementById("diagStatusText");

        if (sensor.mode === "demo") {
          diagPill.className = "status-pill demo";
          diagStatusText.textContent = "Demo Simulated";
          document.getElementById("diagMode").textContent = "Demo (Simulated)";
        } else if (sensor.is_connected) {
          diagPill.className = "status-pill online";
          diagStatusText.textContent = "Connected (I²C)";
          document.getElementById("diagMode").textContent = "Live Hardware";
        } else {
          diagPill.className = "status-pill offline";
          diagStatusText.textContent = "Sensor Offline";
          document.getElementById("diagMode").textContent = "Live Hardware (Disconnected)";
        }

        document.getElementById("diagAddress").textContent = sensor.address || "0x76 / 0x77";
        document.getElementById("diagFreshness").textContent = sensor.data_freshness_seconds !== null ? sensor.data_freshness_seconds + "s ago" : "--";
        document.getElementById("diagErrorCount").textContent = sensor.consecutive_errors;
      })
      .catch(err => console.error("Live monitor update error:", err));
  }

  function renderStreamTable() {
    const tbody = document.getElementById("liveStreamTbody");
    const counter = document.getElementById("streamCounter");
    if (!tbody) return;

    if (counter) counter.textContent = `${streamRecords.length} pulses received`;

    if (streamRecords.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-secondary">Awaiting initial sensor pulse...</td></tr>`;
      return;
    }

    tbody.innerHTML = streamRecords.map(r => `
      <tr>
        <td>${new Date(r.timestamp).toLocaleTimeString([], { hour12: false })}</td>
        <td class="text-cyan fw-bold">${r.temperature_c.toFixed(2)}</td>
        <td class="text-white fw-semibold">${r.pressure_hpa.toFixed(2)}</td>
        <td><span class="badge-tag ${r.source}">${r.source}</span></td>
        <td><span class="badge-tag ${r.validity_status}">${r.validity_status}</span></td>
      </tr>
    `).join("");
  }

  function setupIntervalSelector() {
    const group = document.getElementById("livePollingIntervalGroup");
    if (!group) return;

    group.querySelectorAll("button").forEach(btn => {
      btn.addEventListener("click", function () {
        group.querySelectorAll("button").forEach(b => b.classList.remove("active"));
        this.classList.add("active");
        const intervalSec = parseInt(this.getAttribute("data-interval"));
        window.VA.pollingIntervalMs = intervalSec * 1000;
        // Re-start polling timer with new frequency
        if (window.VA.pollingTimer) {
          clearInterval(window.VA.pollingTimer);
          window.VA.pollingTimer = setInterval(updateLiveReadings, window.VA.pollingIntervalMs);
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    updateLiveReadings();
    setupIntervalSelector();

    // Live monitor has a fast 4s default refresh for smooth gauges
    setInterval(updateLiveReadings, 4000);
  });
})();
