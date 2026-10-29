/**
 * Virtual Atmosphere (VA) - Core Application Script
 * Manages global time, mobile drawer, global alert banner, and telemetry polling.
 */

(function () {
  "use strict";

  // Global State
  window.VA = {
    pollingIntervalMs: 8000,
    pollingTimer: null,
    isAutoRefresh: true,
    lastStatus: null,
    listeners: [],
    loaderDismissed: false
  };

  // Screen reader accessible announcements
  window.VA.announce = function (message) {
    const liveEl = document.getElementById("vaA11yLive");
    if (liveEl) {
      liveEl.textContent = message;
    }
  };

  // Helper to safely set button loading state and avoid double-submissions
  window.VA.setBtnLoading = function (btn, isLoading, loadingText) {
    if (!btn) return;
    if (isLoading) {
      btn.dataset.originalContent = btn.innerHTML;
      btn.disabled = true;
      const text = loadingText || "Loading…";
      btn.innerHTML = `<span class="va-spinner va-spinner-sm me-1" aria-hidden="true"></span><span>${text}</span>`;
    } else {
      if (btn.dataset.originalContent) {
        btn.innerHTML = btn.dataset.originalContent;
      }
      btn.disabled = false;
    }
  };

  // Hide initial loading screen safely
  window.VA.hideAppLoader = function (statusMsg) {
    if (window.VA.loaderDismissed) return;
    window.VA.loaderDismissed = true;
    const loader = document.getElementById("vaAppLoader");
    const statusEl = document.getElementById("vaLoaderStatus");
    if (statusEl && statusMsg) {
      statusEl.textContent = statusMsg;
    }
    if (loader) {
      setTimeout(function () {
        loader.classList.add("loaded");
        setTimeout(function () {
          if (loader.parentNode) {
            loader.parentNode.removeChild(loader);
          }
        }, 500);
      }, 200);
    }
  };

  // Register state change listener
  window.VA.onUpdate = function (callback) {
    if (typeof callback === "function") {
      window.VA.listeners.push(callback);
    }
  };

  function updateClock() {
    const clockEl = document.getElementById("currentClock");
    const dateEl = document.getElementById("currentDate");
    if (!clockEl || !dateEl) return;

    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], { hour12: false });
    dateEl.textContent = now.toLocaleDateString([], {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric"
    });
  }

  function setupMobileNavigation() {
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("appSidebar");
    const backdrop = document.getElementById("sidebarBackdrop");

    if (menuToggle && sidebar && backdrop) {
      menuToggle.addEventListener("click", function () {
        sidebar.classList.toggle("show");
        backdrop.classList.toggle("show");
      });

      backdrop.addEventListener("click", function () {
        sidebar.classList.remove("show");
        backdrop.classList.remove("show");
      });
    }
  }

  function updateStatusHeader(data) {
    const pill = document.getElementById("sensorStatusPill");
    const text = document.getElementById("sensorStatusText");
    const demoBanner = document.getElementById("demoModeBanner");
    const alertBadge = document.getElementById("sidebarAlertBadge");

    if (!pill || !text) return;

    const s = data.sensor || {};
    const alertInfo = data.alert || {};

    if (s.mode === "demo" || s.mode === "simulated") {
      pill.className = "status-pill simulated";
      pill.setAttribute("title", "Simulated data active (Software-generated environmental model)");
      text.textContent = "Simulated";
      if (demoBanner) demoBanner.classList.remove("d-none");
    } else if (s.is_connected) {
      pill.className = "status-pill online";
      pill.setAttribute("title", `Connected to ${s.sensor_type || 'BME280'} on ${s.address || 'I²C'}`);
      text.textContent = "Hardware Live";
      if (demoBanner) demoBanner.classList.add("d-none");
    } else {
      pill.className = "status-pill unavailable";
      pill.setAttribute("title", s.last_error || "Hardware sensor unavailable");
      text.textContent = "Unavailable";
      if (demoBanner) demoBanner.classList.add("d-none");
    }

    // Global Alert Warning Banner Handling
    const alertContainer = document.getElementById("globalAlertContainer");
    const alertMsg = document.getElementById("globalAlertMessage");
    const alertBtn = document.getElementById("btnAcknowledgeAlert");

    if (alertInfo.has_active_alert && alertInfo.active_alert) {
      if (alertContainer) alertContainer.classList.remove("d-none");
      if (alertBadge) alertBadge.classList.remove("d-none");

      const act = alertInfo.active_alert;
      if (alertMsg) {
        alertMsg.textContent = `Temperature of ${act.measured_value.toFixed(1)}°C reached or exceeded the configured threshold (${act.threshold_value.toFixed(1)}°C) at ${new Date(act.timestamp).toLocaleTimeString()}.`;
      }

      if (alertBtn) {
        alertBtn.onclick = function () {
          fetch(`/api/alerts/${act.id}/acknowledge`, {
            method: "POST",
            headers: {
              "X-CSRF-Token": window.VA_CSRF_TOKEN || ""
            }
          })
            .then(r => r.json())
            .then(res => {
              if (res.success) {
                if (alertContainer) alertContainer.classList.add("d-none");
                pollGlobalStatus();
              }
            })
            .catch(err => console.error("Acknowledge error:", err));
        };
      }
    } else {
      if (alertContainer) alertContainer.classList.add("d-none");
      if (alertBadge) alertBadge.classList.add("d-none");
    }
  }

  function pollGlobalStatus() {
    const btnRefresh = document.getElementById("btnRefreshNow");
    if (btnRefresh && !btnRefresh.classList.contains("refreshing")) {
      btnRefresh.classList.add("refreshing");
      const icon = btnRefresh.querySelector("svg");
      if (icon) icon.classList.add("va-spinner");
    }

    fetch("/api/status")
      .then(res => {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(data => {
        window.VA.lastStatus = data;
        updateStatusHeader(data);
        // Notify page-specific listeners
        window.VA.listeners.forEach(fn => {
          try { fn(data); } catch (e) { console.error("Listener error:", e); }
        });
        window.VA.hideAppLoader("Monitoring active");
      })
      .catch(err => {
        console.warn("Status polling error:", err);
        const pill = document.getElementById("sensorStatusPill");
        const text = document.getElementById("sensorStatusText");
        if (pill && text) {
          pill.className = "status-pill offline";
          text.textContent = "API Disconnected";
        }
        window.VA.hideAppLoader("Offline fallback active");
      })
      .finally(() => {
        if (btnRefresh) {
          setTimeout(() => {
            btnRefresh.classList.remove("refreshing");
            btnRefresh.disabled = false;
            const icon = btnRefresh.querySelector("svg");
            if (icon) icon.classList.remove("va-spinner");
          }, 400);
        }
      });
  }

  function setupAutoRefresh() {
    const refreshSwitch = document.getElementById("autoRefreshSwitch");
    const btnRefreshNow = document.getElementById("btnRefreshNow");

    if (refreshSwitch) {
      refreshSwitch.addEventListener("change", function () {
        window.VA.isAutoRefresh = this.checked;
        if (window.VA.isAutoRefresh) {
          startPolling();
          window.VA.announce("Automatic refresh enabled");
        } else {
          stopPolling();
          window.VA.announce("Automatic refresh paused");
        }
      });
    }

    if (btnRefreshNow) {
      btnRefreshNow.addEventListener("click", function () {
        this.disabled = true;
        window.VA.announce("Refreshing telemetry data");
        pollGlobalStatus();
      });
    }

    startPolling();
  }

  function startPolling() {
    stopPolling();
    window.VA.pollingTimer = setInterval(function () {
      if (window.VA.isAutoRefresh) {
        pollGlobalStatus();
      }
    }, window.VA.pollingIntervalMs);
  }

  function stopPolling() {
    if (window.VA.pollingTimer) {
      clearInterval(window.VA.pollingTimer);
      window.VA.pollingTimer = null;
    }
  }

  function setupDemoSpike() {
    const btnSpike = document.getElementById("btnToggleDemoSpike");
    if (btnSpike) {
      btnSpike.addEventListener("click", function () {
        fetch("/api/demo/spike", {
          method: "POST",
          headers: {
            "X-CSRF-Token": window.VA_CSRF_TOKEN || ""
          }
        })
          .then(r => r.json())
          .then(res => {
            alert(res.message);
            pollGlobalStatus();
          })
          .catch(err => console.error("Spike toggle error:", err));
      });
    }
  }

  // Initialize on DOM load
  document.addEventListener("DOMContentLoaded", function () {
    updateClock();
    setInterval(updateClock, 1000);
    setupMobileNavigation();
    setupAutoRefresh();
    setupDemoSpike();
    pollGlobalStatus();

    // Safety fallback: ensure initial loader is never permanently covering the application
    setTimeout(function () {
      window.VA.hideAppLoader("System ready");
    }, 2200);
  });
})();
