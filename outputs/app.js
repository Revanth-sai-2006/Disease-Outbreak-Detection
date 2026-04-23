const REFRESH_SECONDS = 90;
    let countdown = REFRESH_SECONDS;
    let currentOutlook = null;
    let recentAlerts = [];
    let selectedRegion = null;
    const THEME_STORAGE_KEY = "aidde_dashboard_theme";
    const PHC_AUTO_STORAGE_KEY = "aidde_phc_auto_dispatch";
    const PHC_LAST_OUTLOOK_KEY = "aidde_phc_last_outlook_dispatch";
    let phcAutoEnabled = false;

    function setTheme(mode) {
      const root = document.documentElement;
      const toggle = document.getElementById("theme-toggle");
      if (mode === "lumen") {
        root.setAttribute("data-theme", "lumen");
        if (toggle) toggle.textContent = "Nebula Mode";
      } else {
        root.removeAttribute("data-theme");
        if (toggle) toggle.textContent = "Lumen Mode";
      }
    }

    function initThemeToggle() {
      const stored = localStorage.getItem(THEME_STORAGE_KEY) || "nebula";
      setTheme(stored);
      const toggle = document.getElementById("theme-toggle");
      if (!toggle) return;
      toggle.addEventListener("click", () => {
        const isLumen = document.documentElement.getAttribute("data-theme") === "lumen";
        const next = isLumen ? "nebula" : "lumen";
        localStorage.setItem(THEME_STORAGE_KEY, next);
        setTheme(next);
      });
    }

    function fmt(v, d = 3) {
      if (typeof v !== "number" || Number.isNaN(v)) return v;
      return v.toFixed(d);
    }

    async function getJson(path) {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(`Cannot load ${path} (${response.status})`);
      return response.json();
    }

    async function getText(path) {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) throw new Error(`Cannot load ${path} (${response.status})`);
      return response.text();
    }

    async function getApiJson(path) {
      const response = await fetch(path, { cache: "no-store" });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Cannot load ${path} (${response.status})`);
      }
      return response.json();
    }

    function parseCsv(text) {
      const lines = text.trim().split(/\r?\n/);
      if (!lines.length) return [];
      const headers = lines[0].split(",");
      return lines.slice(1).map((line) => {
        const cols = line.split(",");
        const row = {};
        headers.forEach((h, i) => {
          row[h] = cols[i];
        });
        return row;
      });
    }

    function setPhcStatus(message, isError = false) {
      const el = document.getElementById("phc-alert-status");
      if (!el) return;
      el.textContent = message;
      el.style.color = isError ? "#ffd8d2" : "";
    }

    async function dispatchPhcAlerts(mode = "manual") {
      try {
        const response = await fetch("/api/phc-alert-dispatch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }),
          cache: "no-store",
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `Cannot dispatch PHC alerts (${response.status})`);
        }
        const payload = await response.json();
        const now = new Date().toLocaleTimeString();
        setPhcStatus(
          `${payload.alerts_dispatched || 0} PHC alert(s) dispatched at ${now} (${mode}).`,
          false
        );
        if (payload.outlook_generated_at_utc) {
          localStorage.setItem(PHC_LAST_OUTLOOK_KEY, payload.outlook_generated_at_utc);
        }
      } catch (err) {
        setPhcStatus(`PHC dispatch failed: ${String(err)}`, true);
      }
    }

    function initPhcAutomation() {
      const toggle = document.getElementById("phc-auto-toggle");
      const sendBtn = document.getElementById("phc-send-btn");
      phcAutoEnabled = localStorage.getItem(PHC_AUTO_STORAGE_KEY) === "true";
      if (toggle) {
        toggle.checked = phcAutoEnabled;
        toggle.addEventListener("change", () => {
          phcAutoEnabled = !!toggle.checked;
          localStorage.setItem(PHC_AUTO_STORAGE_KEY, String(phcAutoEnabled));
          setPhcStatus(
            phcAutoEnabled
              ? "Auto PHC alert dispatch is enabled. Alerts will be sent on new outlook cycles."
              : "Auto PHC alert dispatch is disabled.",
            false
          );
        });
      }
      if (sendBtn) {
        sendBtn.addEventListener("click", () => dispatchPhcAlerts("manual"));
      }
    }

    function sevClass(value) {
      return String(value || "low").toLowerCase();
    }

    function trendClass(value) {
      return `trend-${String(value || "stable").toLowerCase()}`;
    }

    function renderKpis(summary, outlook) {
      const regions = outlook.regions || [];
      const alerts = regions.filter((r) => r.alert).length;
      const rising = regions.filter((r) => String(r.trend).toLowerCase() === "rising").length;
      const maxProb = regions.length ? Math.max(...regions.map((r) => Number(r.outbreak_probability || 0))) : 0;
      const critical = regions.filter((r) => String(r.severity).toLowerCase() === "critical").length;

      document.getElementById("kpis").innerHTML = [
        ["Data Source", summary.data_source || "unknown"],
        ["Tracked Regions", regions.length],
        ["Regions on Alert", alerts],
        ["Rising Trend Regions", rising],
        ["Critical Severity Regions", critical],
        ["Peak Probability", fmt(maxProb, 3)],
      ].map(([label, value]) => `
        <article class="card">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
        </article>
      `).join("");
    }

    function renderAnalytics(outlook) {
      const regions = outlook.regions || [];
      const probs = regions.map((r) => Number(r.outbreak_probability || 0));
      const avg = probs.length ? probs.reduce((a, b) => a + b, 0) / probs.length : 0;

      document.getElementById("intensity-value").textContent = fmt(avg, 3);
      document.getElementById("intensity-bar").style.width = `${Math.max(0, Math.min(100, avg * 100)).toFixed(1)}%`;

      let caption = "Low pressure. Routine monitoring suggested.";
      if (avg >= 0.75) caption = "Very high pressure. Immediate administrative review advised.";
      else if (avg >= 0.5) caption = "Elevated pressure. Active surveillance recommended.";
      else if (avg >= 0.3) caption = "Moderate pressure. Maintain precautionary watch.";
      document.getElementById("intensity-caption").textContent = caption;

      const families = {};
      regions.forEach((r) => {
        const family = String(r.disease_family || "mixed/uncertain");
        families[family] = (families[family] || 0) + 1;
      });
      const ranked = Object.entries(families).sort((a, b) => b[1] - a[1]);
      const dominant = ranked[0] ? `${ranked[0][0]} (${ranked[0][1]} region)` : "unknown";
      const dist = ranked.map(([name, count]) => `${name}: ${count}`).join(" | ") || "No type signal";
      document.getElementById("type-analytics").innerHTML =
        `<strong>Dominant family:</strong> ${dominant}<br/><span class="type-breakdown">${dist}</span>`;
    }

    function renderRows(outlook) {
      const rows = (outlook.regions || []).map((r) => `
        <tr class="row-click ${selectedRegion === r.region ? "active" : ""}" data-region="${r.region}">
          <td>${r.region}</td>
          <td>${fmt(Number(r.outbreak_probability || 0), 3)}</td>
          <td><span class="chip ${sevClass(r.severity)}">${r.severity || "low"}</span></td>
          <td><span class="chip ${trendClass(r.trend)}">${r.trend || "stable"}</span></td>
          <td>${r.likely_disease || "n/a"}</td>
          <td>${r.disease_family || "n/a"}</td>
          <td>${r.outbreak_type || "n/a"}</td>
          <td>${Array.isArray(r.key_symptoms) ? r.key_symptoms.join(", ") : (r.key_symptoms || "n/a")}</td>
          <td>${r.alert ? "Yes" : "No"}</td>
          <td>${r.forecast_horizon_days} days</td>
          <td>${r.report_date}</td>
        </tr>
      `).join("");
      document.getElementById("region-rows").innerHTML = rows;
    }

    function computeSpreadStatus(regionData, regionHistory) {
      const alertNow = !!regionData.alert;
      const trend = String(regionData.trend || "stable").toLowerCase();
      const recentAlertCount = regionHistory.filter((r) => String(r.is_alert) === "1").length;
      const recentAvgProb = regionHistory.length
        ? regionHistory.reduce((sum, r) => sum + Number(r.predicted_probability || 0), 0) / regionHistory.length
        : 0;

      if (alertNow && trend === "rising") {
        return {
          label: "Disease spread likely increasing",
          note: "Current alert is active and probability trend is rising.",
        };
      }
      if (alertNow || recentAlertCount >= 3 || recentAvgProb >= 0.55) {
        return {
          label: "Disease spread watch: active",
          note: "Signals indicate persistent spread pressure in recent cycles.",
        };
      }
      return {
        label: "No strong spread signal currently",
        note: "Current and recent indicators are below spread escalation threshold.",
      };
    }

    function renderCityDetails(regionName) {
      const panel = document.getElementById("city-detail-panel");
      const region = (currentOutlook?.regions || []).find((r) => r.region === regionName);
      if (!region) {
        panel.innerHTML = '<div class="source-line">Select a city/region from the table above to view detailed spread intelligence.</div>';
        return;
      }

      const regionHistory = recentAlerts
        .filter((r) => String(r.region) === regionName)
        .slice(-10)
        .reverse();

      const spread = computeSpreadStatus(region, regionHistory);
      const topSymptoms = Array.isArray(region.key_symptoms) ? region.key_symptoms.join(", ") : (region.key_symptoms || "n/a");
      const recentHistoryLines = regionHistory.length
        ? regionHistory.slice(0, 5).map((r) =>
            `<li>${r.report_date}: probability ${fmt(Number(r.predicted_probability || 0), 3)}, alert ${String(r.is_alert) === "1" ? "yes" : "no"}, severity ${r.severity || "n/a"}</li>`
          ).join("")
        : "<li>No recent city/region alert history available.</li>";

      panel.innerHTML = `
        <h3 class="detail-title">${regionName}</h3>
        <div class="source-line detail-intro"><strong>${spread.label}</strong><br/>${spread.note}</div>
        <div class="detail-grid">
          <div class="detail-box"><strong>Current Outbreak Probability</strong>${fmt(Number(region.outbreak_probability || 0), 3)}</div>
          <div class="detail-box"><strong>Current Severity</strong>${region.severity || "n/a"}</div>
          <div class="detail-box"><strong>Trend</strong>${region.trend || "stable"}</div>
          <div class="detail-box"><strong>Alert Status</strong>${region.alert ? "Spread risk alert active" : "No active spread alert"}</div>
          <div class="detail-box"><strong>Likely Disease</strong>${region.likely_disease || "n/a"}</div>
          <div class="detail-box"><strong>Disease Family</strong>${region.disease_family || "n/a"}</div>
          <div class="detail-box"><strong>Outbreak Type</strong>${region.outbreak_type || "n/a"}</div>
          <div class="detail-box"><strong>Key Symptoms</strong>${topSymptoms}</div>
          <div class="detail-box"><strong>Forecast Window</strong>${region.forecast_horizon_days} days</div>
          <div class="detail-box"><strong>Last Report Date</strong>${region.report_date}</div>
        </div>
        <div class="history-title"><strong>Recent Detection History (latest 5):</strong></div>
        <ul class="history-list">${recentHistoryLines}</ul>
      `;
    }

    function bindRowClicks() {
      const tbody = document.getElementById("region-rows");
      tbody.onclick = (event) => {
        const row = event.target.closest("tr[data-region]");
        if (!row) return;
        selectedRegion = row.getAttribute("data-region");
        renderRows(currentOutlook);
        renderCityDetails(selectedRegion);
      };
    }

    function renderSourceStatus(obj) {
      const status = obj || {};
      const dataGov = status.data_gov_in || {};
      const weatherConfigured = !!status.weather_api_configured;
      const dataGovConfigured = !!dataGov.configured;
      const dataGovRegions = Array.isArray(dataGov.regions_covered) ? dataGov.regions_covered : [];

      const rows = [
        `<div><strong>status:</strong> ${String(status.status || "unknown")}</div>`,
        `<div><strong>source:</strong> ${String(status.source || "unknown")}</div>`,
        `<div><strong>rows:</strong> ${String(status.rows ?? "n/a")}</div>`,
        `<div><strong>weather_api_configured:</strong> ${weatherConfigured ? "yes" : "no"}</div>`,
        `<div><strong>data_gov_in_configured:</strong> ${dataGovConfigured ? "yes" : "no"}</div>`,
        `<div><strong>data_gov_in_resource_id:</strong> ${String(dataGov.resource_id || "not set")}</div>`,
        `<div><strong>data_gov_in_regions_covered:</strong> ${dataGovRegions.length ? dataGovRegions.join(", ") : "none"}</div>`,
      ];

      if (dataGov.error) {
        rows.push(`<div><strong>data_gov_in_error:</strong> ${String(dataGov.error)}</div>`);
      }

      document.getElementById("source-status").innerHTML = rows.join("") || "No source status available.";
    }

    function setSyncTime() {
      document.getElementById("last-sync").textContent = new Date().toLocaleTimeString();
      countdown = REFRESH_SECONDS;
    }

    function upsertRegion(region) {
      if (!region) return;
      if (!currentOutlook) currentOutlook = { regions: [] };
      const existing = Array.isArray(currentOutlook.regions) ? [...currentOutlook.regions] : [];
      const idx = existing.findIndex((item) => String(item.region).toLowerCase() === String(region.region).toLowerCase());
      if (idx >= 0) existing[idx] = region;
      else existing.unshift(region);
      currentOutlook.regions = existing;
    }

    async function runCitySearch() {
      const input = document.getElementById("city-search");
      const button = document.getElementById("city-search-btn");
      const errorBox = document.getElementById("error-box");
      const city = String(input.value || "").trim();

      if (!city) {
        errorBox.innerHTML = '<div class="error">Please enter a city name.</div>';
        return;
      }

      button.disabled = true;
      button.textContent = "Generating...";
      errorBox.innerHTML = "";
      try {
        const payload = await getApiJson(`/api/city-report?city=${encodeURIComponent(city)}`);
        upsertRegion(payload.region);
        if (payload.headline) currentOutlook.headline = payload.headline;
        if (payload.generated_at_utc) currentOutlook.generated_at_utc = payload.generated_at_utc;

        renderRows(currentOutlook);
        renderAnalytics(currentOutlook);
        bindRowClicks();

        selectedRegion = payload.region?.region || city;
        renderRows(currentOutlook);
        renderCityDetails(selectedRegion);

        document.getElementById("headline").textContent = currentOutlook.headline || "Regional outbreak watch loaded.";
        document.getElementById("generated").textContent = `Generated at: ${currentOutlook.generated_at_utc || "unknown"}`;

        if (payload.source_status) renderSourceStatus(payload.source_status);
        setSyncTime();
      } catch (err) {
        errorBox.innerHTML = `<div class="error">City report generation failed. ${String(err)}. Start the Flask dashboard server to enable city search.</div>`;
      } finally {
        button.disabled = false;
        button.textContent = "Generate Report";
      }
    }

    async function bootstrap() {
      const errorBox = document.getElementById("error-box");
      try {
        const dashboard = await getApiJson("/api/dashboard");
        const summary = dashboard.summary || {};
        const outlook = dashboard.outlook || { regions: [] };
        currentOutlook = outlook;

        try {
          const alertsCsv = await getText("/outputs/alerts.csv");
          recentAlerts = parseCsv(alertsCsv);
        } catch (_ignored) {
          recentAlerts = [];
        }

        document.getElementById("headline").textContent = outlook.headline || "Regional outbreak watch loaded.";
        document.getElementById("generated").textContent = `Generated at: ${outlook.generated_at_utc || "unknown"}`;

        renderKpis(summary, outlook);
        renderAnalytics(outlook);
        renderRows(outlook);
        bindRowClicks();

        if (!selectedRegion && (outlook.regions || []).length) {
          selectedRegion = outlook.regions[0].region;
          renderRows(outlook);
        }
        renderCityDetails(selectedRegion);

        renderSourceStatus(dashboard.source_status || { status: "unknown" });

        if (phcAutoEnabled) {
          const marker = outlook.generated_at_utc || "";
          const lastMarker = localStorage.getItem(PHC_LAST_OUTLOOK_KEY) || "";
          if (marker && marker !== lastMarker) {
            dispatchPhcAlerts("automatic");
          }
        }

        errorBox.innerHTML = "";
        setSyncTime();
      } catch (err) {
        errorBox.innerHTML = `<div class="error">${String(err)}</div>`;
      }
    }

    setInterval(() => {
      countdown -= 1;
      if (countdown <= 0) bootstrap();
      document.getElementById("refresh-countdown").textContent = `${Math.max(0, countdown)}s`;
    }, 1000);

    document.getElementById("city-search-btn").addEventListener("click", runCitySearch);
    document.getElementById("city-search").addEventListener("keydown", (event) => {
      if (event.key === "Enter") runCitySearch();
    });

    initThemeToggle();
    initPhcAutomation();
    bootstrap();
