/**
 * Virtual Atmosphere (VA) - Unified Professional Environmental Charting Engine
 * Built on Chart.js v4 (UMD) with WCAG AA compliance, monotone interpolation,
 * threshold horizontal reference lines, interactive tooltips, and honest gap handling.
 */

(function (root, factory) {
  if (typeof define === "function" && define.amd) {
    define(["Chart"], factory);
  } else if (typeof module === "object" && module.exports) {
    module.exports = factory(require("chart.js"));
  } else {
    root.VACharts = factory(root.Chart);
  }
})(typeof self !== "undefined" ? self : this, function (Chart) {
  "use strict";

  if (!Chart) {
    console.error("VACharts requires Chart.js to be loaded first.");
    return {};
  }

  // Register Custom Horizontal Threshold Reference Line Plugin
  const ThresholdLinePlugin = {
    id: "vaThresholdLine",
    afterDraw: function (chart, args, options) {
      if (!options || options.value === undefined || options.value === null) return;
      const thresholdVal = Number(options.value);
      if (isNaN(thresholdVal)) return;

      const yAxis = chart.scales.y;
      if (!yAxis) return;

      const yPos = yAxis.getPixelForValue(thresholdVal);
      const chartArea = chart.chartArea;
      if (!chartArea) return;

      if (yPos < chartArea.top || yPos > chartArea.bottom) return;

      const ctx = chart.ctx;
      ctx.save();

      // Draw dashed reference line
      ctx.strokeStyle = options.lineColor || "#dc2626";
      ctx.lineWidth = options.lineWidth || 1.8;
      ctx.setLineDash(options.dash || [6, 4]);
      ctx.beginPath();
      ctx.moveTo(chartArea.left, yPos);
      ctx.lineTo(chartArea.right, yPos);
      ctx.stroke();

      // Threshold label badge
      const labelText = options.label || `Alert Threshold: ${thresholdVal.toFixed(1)}°C`;
      ctx.font = "600 11px 'Inter', sans-serif";
      const textMetrics = ctx.measureText(labelText);
      const padX = 6;
      const padY = 3;
      const rectW = textMetrics.width + padX * 2;
      const rectH = 18;
      const rectX = chartArea.right - rectW - 4;
      const rectY = Math.max(chartArea.top + 2, yPos - rectH - 3);

      ctx.fillStyle = "rgba(220, 38, 38, 0.12)";
      ctx.fillRect(rectX, rectY, rectW, rectH);
      ctx.strokeStyle = "rgba(220, 38, 38, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([]);
      ctx.strokeRect(rectX, rectY, rectW, rectH);

      ctx.fillStyle = "#b91c1c";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(labelText, rectX + padX, rectY + rectH / 2);

      ctx.restore();
    }
  };

  Chart.register(ThresholdLinePlugin);

  // Common Color Tokens (Sunset Warm Palette)
  const PALETTE = {
    temp: {
      border: "#dc2626",
      bg: "rgba(220, 38, 38, 0.08)",
      point: "#dc2626"
    },
    hum: {
      border: "#0284c7",
      bg: "rgba(2, 132, 199, 0.08)",
      point: "#0284c7"
    },
    heat: {
      border: "#ea580c",
      bg: "rgba(234, 88, 12, 0.08)",
      point: "#ea580c"
    },
    press: {
      border: "#8b5cf6",
      bg: "rgba(139, 92, 246, 0.08)",
      point: "#8b5cf6"
    },
    grid: "rgba(225, 200, 180, 0.32)",
    axisText: "#5a463e",
    headingText: "#1f1412"
  };

  /**
   * Formats ISO timestamp into clean local time string based on multi-day range.
   */
  function formatTimestamp(isoString, isMultiDay) {
    if (!isoString) return "";
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      if (isMultiDay) {
        return `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}`;
      }
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    } catch (e) {
      return isoString;
    }
  }

  /**
   * Detailed tooltip date-time string in user's local timezone.
   */
  function formatTooltipDateTime(isoString) {
    if (!isoString) return "";
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString;
      return d.toLocaleDateString([], {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric"
      }) + " at " + d.toLocaleTimeString([], { hour12: false });
    } catch (e) {
      return isoString;
    }
  }

  /**
   * Builds standardized Chart.js configuration for a single environmental metric.
   */
  function buildChartConfig(options) {
    const {
      type = "temp", // "temp" | "hum" | "heat" | "press"
      label,
      unit,
      yMin,
      yMax,
      suggestedMin,
      suggestedMax,
      thresholdVal = null,
      isDashed = false
    } = options;

    const colors = PALETTE[type] || PALETTE.temp;

    return {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: label,
            data: [],
            borderColor: colors.border,
            backgroundColor: colors.bg,
            borderWidth: 2.2,
            borderDash: isDashed ? [6, 4] : [],
            fill: true,
            // Monotone cubic interpolation prevents artificial overshoots
            cubicInterpolationMode: "monotone",
            tension: 0.1,
            spanGaps: false, // Honestly show gaps in missing data
            // Scriptable point radius: 0 for dense graphs; 4 for threshold violation; 2.5 for very small datasets
            pointRadius: function (ctx) {
              const val = ctx.raw;
              if (val === null || val === undefined) return 0;
              const threshold = ctx.chart.options.plugins?.vaThresholdLine?.value;
              if (type === "temp" && threshold !== null && threshold !== undefined && val >= threshold) {
                return 4.5;
              }
              const total = ctx.chart.data.labels ? ctx.chart.data.labels.length : 0;
              return total <= 15 ? 2.5 : 0;
            },
            pointHoverRadius: 6,
            pointHitRadius: 10,
            pointBackgroundColor: function (ctx) {
              const val = ctx.raw;
              const threshold = ctx.chart.options.plugins?.vaThresholdLine?.value;
              if (type === "temp" && threshold !== null && threshold !== undefined && val >= threshold) {
                return "#dc2626";
              }
              return colors.point;
            },
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
            rawReadings: [] // Attaches source objects for tooltip inspection
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        interaction: {
          mode: "index",
          intersect: false
        },
        layout: {
          padding: { top: 12, right: 14, bottom: 6, left: 6 }
        },
        plugins: {
          legend: {
            display: false // Using custom interactive clickable legend
          },
          vaThresholdLine: {
            value: thresholdVal,
            label: thresholdVal ? `Threshold: ${Number(thresholdVal).toFixed(1)}°C` : null,
            lineColor: "#dc2626"
          },
          tooltip: {
            enabled: true,
            backgroundColor: "rgba(255, 255, 255, 0.98)",
            titleColor: "#1f1412",
            bodyColor: "#5a463e",
            borderColor: "rgba(230, 210, 195, 0.95)",
            borderWidth: 1.5,
            padding: 12,
            boxPadding: 6,
            usePointStyle: true,
            titleFont: { size: 12, weight: "700", family: "'Inter', sans-serif" },
            bodyFont: { size: 13, weight: "600", family: "'Inter', sans-serif" },
            callbacks: {
              title: function (items) {
                if (!items.length) return "";
                const chart = items[0].chart;
                const idx = items[0].dataIndex;
                const rawObj = chart.data.datasets[0].rawReadings ? chart.data.datasets[0].rawReadings[idx] : null;
                if (rawObj && rawObj.timestamp) {
                  return formatTooltipDateTime(rawObj.timestamp);
                }
                return "Time: " + items[0].label;
              },
              label: function (ctx) {
                const val = ctx.parsed.y;
                if (val === null || val === undefined) {
                  return `${ctx.dataset.label}: No reading (Data gap)`;
                }

                const chart = ctx.chart;
                const idx = ctx.dataIndex;
                const rawObj = chart.data.datasets[0].rawReadings ? chart.data.datasets[0].rawReadings[idx] : null;
                const source = rawObj ? (rawObj.source || rawObj.sensor_type || "hardware") : "hardware";

                let mainLine = `${label}: ${Number(val).toFixed(type === "hum" ? 1 : 2)} ${unit}`;
                return mainLine;
              },
              afterLabel: function (ctx) {
                const val = ctx.parsed.y;
                if (val === null || val === undefined) return null;

                const chart = ctx.chart;
                const idx = ctx.dataIndex;
                const rawObj = chart.data.datasets[0].rawReadings ? chart.data.datasets[0].rawReadings[idx] : null;
                const source = rawObj ? (rawObj.source || rawObj.sensor_type || "hardware") : "sensor";

                const lines = [`Source: ${source}`];

                const threshold = chart.options.plugins?.vaThresholdLine?.value;
                if (type === "temp" && threshold !== null && threshold !== undefined && val >= threshold) {
                  lines.push(`⚠️ Exceeds Threshold (${threshold.toFixed(1)}°C)`);
                }

                if (type === "heat" && rawObj && rawObj.heat_risk) {
                  lines.push(`Category: ${rawObj.heat_risk.category || 'Normal'}`);
                }

                return lines;
              }
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: "Local Time",
              color: PALETTE.axisText,
              font: { size: 12, weight: "600", family: "'Inter', sans-serif" },
              padding: { top: 6 }
            },
            grid: {
              color: PALETTE.grid
            },
            ticks: {
              color: PALETTE.axisText,
              maxTicksLimit: 8,
              maxRotation: 0,
              autoSkip: true,
              font: { size: 11, weight: "600", family: "'Inter', sans-serif" }
            }
          },
          y: {
            title: {
              display: true,
              text: `${label} (${unit})`,
              color: colors.border,
              font: { size: 12, weight: "700", family: "'Inter', sans-serif" }
            },
            grid: {
              color: PALETTE.grid
            },
            ticks: {
              color: colors.border,
              font: { size: 11, weight: "600", family: "'Inter', sans-serif" },
              callback: function (val) {
                return `${val} ${unit}`;
              }
            },
            min: yMin !== undefined ? yMin : undefined,
            max: yMax !== undefined ? yMax : undefined,
            suggestedMin: suggestedMin,
            suggestedMax: suggestedMax
          }
        }
      }
    };
  }

  /**
   * Updates an existing Chart.js instance with new readings and range metadata.
   */
  function updateChartData(chart, readings, valueExtractor, rangeCode, thresholdVal) {
    if (!chart) return;

    if (thresholdVal !== undefined && chart.options.plugins?.vaThresholdLine) {
      chart.options.plugins.vaThresholdLine.value = thresholdVal;
      chart.options.plugins.vaThresholdLine.label = thresholdVal ? `Threshold: ${Number(thresholdVal).toFixed(1)}°C` : null;
    }

    if (!readings || readings.length === 0) {
      chart.data.labels = [];
      chart.data.datasets[0].data = [];
      chart.data.datasets[0].rawReadings = [];
      chart.update();
      return;
    }

    const isMultiDay = rangeCode === "7d" || rangeCode === "30d" || rangeCode === "custom";

    const labels = readings.map((r) => {
      if (r.is_gap) return "";
      return formatTimestamp(r.timestamp, isMultiDay);
    });

    const dataPoints = readings.map((r) => {
      if (r.is_gap) return null;
      const v = valueExtractor(r);
      return v !== null && v !== undefined ? Number(v) : null;
    });

    chart.data.labels = labels;
    chart.data.datasets[0].data = dataPoints;
    chart.data.datasets[0].rawReadings = readings;

    chart.update();
  }

  /**
   * Updates the compact statistics summary bar beneath each chart card.
   */
  function updateChartStatsBar(containerEl, stats) {
    if (!containerEl) return;

    const {
      latest,
      latestTime,
      min,
      max,
      avg,
      count,
      unit,
      source = "DHT11",
      unavailable = false,
      unavailableMsg = null
    } = stats;

    if (unavailable) {
      containerEl.innerHTML = `
        <div class="chart-stats-strip unavailable d-flex justify-content-between align-items-center flex-wrap gap-2 text-muted small">
          <span><span class="badge bg-secondary bg-opacity-10 text-muted">Offline</span> ${unavailableMsg || 'Sensor unavailable or not recorded'}</span>
          <span>Valid Samples: <strong class="text-dark">0</strong></span>
        </div>
      `;
      return;
    }

    const fmt = (v, digits = 1) => (v !== null && v !== undefined && !isNaN(v) ? Number(v).toFixed(digits) + " " + unit : "--");
    const fmtTime = (ts) => {
      if (!ts) return "--:--";
      try {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour12: false });
      } catch (e) {
        return "--:--";
      }
    };

    containerEl.innerHTML = `
      <div class="chart-stats-strip d-flex justify-content-between align-items-center flex-wrap gap-2 small">
        <div>Latest: <strong class="text-dark">${fmt(latest)}</strong> <span class="text-muted" style="font-size: 11px;">(${fmtTime(latestTime)})</span></div>
        <div>Min: <strong class="text-dark">${fmt(min)}</strong></div>
        <div>Avg: <strong class="text-dark">${fmt(avg)}</strong></div>
        <div>Max: <strong class="text-dark">${fmt(max)}</strong></div>
        <div>Samples: <strong class="text-dark">${count || 0}</strong></div>
      </div>
    `;
  }

  /**
   * Controls empty / unavailable / loading overlays on a chart card.
   */
  function setChartOverlay(overlayEl, state, message) {
    if (!overlayEl) return;
    if (state === "none") {
      overlayEl.classList.add("d-none");
      return;
    }

    overlayEl.classList.remove("d-none");
    const titleEl = overlayEl.querySelector(".chart-empty-title");
    const subEl = overlayEl.querySelector(".chart-empty-sub");

    if (state === "unavailable") {
      if (titleEl) titleEl.textContent = "Sensor Not Connected";
      if (subEl) subEl.textContent = message || "No readings recorded for this sensor. Ensure physical sensor is attached.";
    } else if (state === "empty") {
      if (titleEl) titleEl.textContent = "No Readings Available";
      if (subEl) subEl.textContent = message || "No readings found in database for the selected time window.";
    } else if (state === "loading") {
      if (titleEl) titleEl.textContent = "Loading Telemetry";
      if (subEl) subEl.textContent = message || "Fetching data from Turso / SQLite pipeline...";
    }
  }

  return {
    PALETTE,
    formatTimestamp,
    formatTooltipDateTime,
    buildChartConfig,
    updateChartData,
    updateChartStatsBar,
    setChartOverlay
  };
});
