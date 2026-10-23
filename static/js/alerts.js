/**
 * Virtual Atmosphere - Temperature Alerts Controller
 */

(function () {
  "use strict";

  let currentStatusFilter = "all";

  function loadAlerts() {
    fetch(`/api/alerts?status=${currentStatusFilter}`)
      .then(r => r.json())
      .then(data => {
        const tbody = document.getElementById("alertsTbody");
        const alerts = data.alerts || [];

        if (tbody) {
          if (alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-secondary">No alerts recorded under status filter: <strong>${currentStatusFilter}</strong>.</td></tr>`;
          } else {
            tbody.innerHTML = alerts.map(a => {
              const badgeClass = a.status === "active" ? "invalid" : (a.status === "acknowledged" ? "demo" : "valid");
              const ackText = a.acknowledged_at ? new Date(a.acknowledged_at).toLocaleTimeString() : "–";
              const actionBtn = a.status === "active"
                ? `<button class="va-btn va-btn-danger va-btn-sm btn-ack-inline" data-id="${a.id}">Acknowledge</button>`
                : `<span class="text-muted small">None</span>`;

              return `
                <tr>
                  <td>#${a.id}</td>
                  <td>${new Date(a.timestamp).toLocaleString()}</td>
                  <td><code class="text-white">${a.alert_type}</code></td>
                  <td class="text-danger fw-bold">${a.measured_value.toFixed(1)} °C</td>
                  <td class="text-secondary">${a.threshold_value.toFixed(1)} °C</td>
                  <td><span class="badge-tag ${badgeClass}">${a.status}</span></td>
                  <td>${ackText}</td>
                  <td>${actionBtn}</td>
                </tr>
              `;
            }).join("");

            // Attach inline acknowledge handlers
            tbody.querySelectorAll(".btn-ack-inline").forEach(btn => {
              btn.addEventListener("click", function () {
                const id = this.getAttribute("data-id");
                acknowledgeAlert(id);
              });
            });
          }
        }
      })
      .catch(err => console.error("Error loading alerts list:", err));
  }

  function loadSpotlightStatus() {
    fetch("/api/status")
      .then(r => r.json())
      .then(data => {
        const alertInfo = data.alert || {};
        const noAlertBox = document.getElementById("spotlightNoAlert");
        const activeAlertBox = document.getElementById("spotlightActiveAlert");
        const pill = document.getElementById("spotlightStatusPill");
        const text = document.getElementById("spotlightStatusText");

        if (alertInfo.threshold_c) {
          document.getElementById("inputAlertThreshold").value = alertInfo.threshold_c;
        }

        if (alertInfo.has_active_alert && alertInfo.active_alert) {
          const act = alertInfo.active_alert;
          if (noAlertBox) noAlertBox.classList.add("d-none");
          if (activeAlertBox) activeAlertBox.classList.remove("d-none");

          pill.className = "status-pill offline";
          text.textContent = "ACTIVE WARNING";

          document.getElementById("spotlightMeasured").textContent = `${act.measured_value.toFixed(1)} °C`;
          document.getElementById("spotlightThreshold").textContent = `${act.threshold_value.toFixed(1)} °C`;
          document.getElementById("spotlightTimestamp").textContent = new Date(act.timestamp).toLocaleTimeString();

          const ackBtn = document.getElementById("btnSpotlightAcknowledge");
          if (ackBtn) {
            ackBtn.onclick = function () {
              acknowledgeAlert(act.id);
            };
          }
        } else {
          if (noAlertBox) noAlertBox.classList.remove("d-none");
          if (activeAlertBox) activeAlertBox.classList.add("d-none");

          pill.className = "status-pill online";
          text.textContent = "Nominal / Safe Range";
        }
      })
      .catch(err => console.error("Spotlight error:", err));
  }

  function acknowledgeAlert(alertId) {
    fetch(`/api/alerts/${alertId}/acknowledge`, { method: "POST" })
      .then(r => r.json())
      .then(res => {
        if (res.success) {
          loadSpotlightStatus();
          loadAlerts();
        } else {
          alert(res.error || "Failed to acknowledge alert.");
        }
      })
      .catch(err => console.error("Acknowledge error:", err));
  }

  function setupStatusFilter() {
    const group = document.getElementById("alertFilterGroup");
    if (!group) return;

    group.querySelectorAll("button").forEach(btn => {
      btn.addEventListener("click", function () {
        group.querySelectorAll("button").forEach(b => b.classList.remove("active"));
        this.classList.add("active");
        currentStatusFilter = this.getAttribute("data-status");
        loadAlerts();
      });
    });
  }

  function setupThresholdForm() {
    const form = document.getElementById("formAlertThreshold");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const input = document.getElementById("inputAlertThreshold");
      const feedback = document.getElementById("alertsThresholdFeedback");
      const val = parseFloat(input.value);

      fetch("/api/settings/threshold", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threshold_c: val })
      })
        .then(r => r.json())
        .then(res => {
          if (res.success) {
            feedback.className = "small mt-2 text-success";
            feedback.textContent = res.message;
            loadSpotlightStatus();
            loadAlerts();
          } else {
            feedback.className = "small mt-2 text-danger";
            feedback.textContent = res.error;
          }
        })
        .catch(err => {
          feedback.className = "small mt-2 text-danger";
          feedback.textContent = "Network error updating threshold.";
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupStatusFilter();
    setupThresholdForm();
    loadSpotlightStatus();
    loadAlerts();

    // Hook into global VA update cycle
    window.VA.onUpdate(function () {
      loadSpotlightStatus();
      loadAlerts();
    });
  });
})();
