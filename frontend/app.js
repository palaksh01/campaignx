let currentCampaignId = null;

const statusEl = document.getElementById("statusText");
const phaseTagEl = document.getElementById("phaseTag");
const btnPlan = document.getElementById("btnPlan");
const btnReset = document.getElementById("btnReset");
const btnApproveInitial = document.getElementById("btnApproveInitial");
const btnOptimize = document.getElementById("btnOptimize");
const btnApproveOptimized = document.getElementById("btnApproveOptimized");

const strategyPreviewEl = document.getElementById("strategyPreview");
const contentPreviewEl = document.getElementById("contentPreview");
const optimizationPreviewEl = document.getElementById("optimizationPreview");
const openRateEl = document.getElementById("openRate");
const clickRateEl = document.getElementById("clickRate");

function setStatus(text) {
  statusEl.textContent = text;
}

function setPhase(phase) {
  if (!phase) {
    phaseTagEl.textContent = "No campaign";
    return;
  }
  phaseTagEl.textContent = phase;
}

function resetUI() {
  currentCampaignId = null;
  setPhase(null);
  setStatus("Idle.");
  strategyPreviewEl.textContent = "// Strategy JSON will appear here after planning.";
  contentPreviewEl.textContent = "// Email variant JSON will appear here after planning.";
  optimizationPreviewEl.textContent = "// Metrics and optimization JSON will appear here after optimization.";
  openRateEl.textContent = "–";
  clickRateEl.textContent = "–";
  btnApproveInitial.disabled = true;
  btnOptimize.disabled = true;
  btnApproveOptimized.disabled = true;
}

resetUI();

async function planCampaign() {
  const brief = document.getElementById("brief").value.trim();
  const cohortIdRaw = document.getElementById("cohortId").value.trim();
  const cohort_id = cohortIdRaw || "demo";

  if (!brief) {
    alert("Please enter a campaign brief.");
    return;
  }

  setStatus("Planning campaign (strategy + content)...");
  btnPlan.disabled = true;

  try {
    const res = await fetch("/campaigns/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brief, cohort_id }),
    });
    if (!res.ok) {
      throw new Error(`Backend error: ${res.status}`);
    }
    const data = await res.json();
    currentCampaignId = data.campaign_id;

    strategyPreviewEl.textContent = JSON.stringify(
      { cohort: data.cohort, strategy: data.strategy },
      null,
      2
    );
    contentPreviewEl.textContent = JSON.stringify(data.content, null, 2);

    setPhase("draft");
    setStatus("Plan ready. Review and approve to schedule the initial campaign.");
    btnApproveInitial.disabled = false;
  } catch (err) {
    console.error(err);
    alert("Failed to plan campaign. Check console for details.");
    setStatus("Error planning campaign.");
  } finally {
    btnPlan.disabled = false;
  }
}

async function approveInitial() {
  if (!currentCampaignId) return;
  setStatus("Scheduling initial campaign...");
  btnApproveInitial.disabled = true;

  try {
    const res = await fetch(`/campaigns/${currentCampaignId}/approve-initial`, {
      method: "POST",
    });
    if (!res.ok) {
      throw new Error(`Backend error: ${res.status}`);
    }
    const data = await res.json();
    setPhase(data.phase);
    setStatus("Initial campaign scheduled. Once it runs, fetch metrics to optimize.");
    btnOptimize.disabled = false;
  } catch (err) {
    console.error(err);
    alert("Failed to schedule initial campaign.");
    setStatus("Error scheduling initial campaign.");
    btnApproveInitial.disabled = false;
  }
}

async function fetchMetricsAndOptimize() {
  if (!currentCampaignId) return;
  setStatus("Fetching metrics and generating optimized version...");
  btnOptimize.disabled = true;

  try {
    const res = await fetch(`/campaigns/${currentCampaignId}/metrics`);
    if (!res.ok) {
      throw new Error(`Backend error: ${res.status}`);
    }
    const data = await res.json();

    openRateEl.textContent = (data.metrics.open_rate * 100).toFixed(1) + "%";
    clickRateEl.textContent = (data.metrics.click_rate * 100).toFixed(1) + "%";
    optimizationPreviewEl.textContent = JSON.stringify(data, null, 2);

    setPhase("optimized_draft");
    setStatus("Optimized strategy + content ready. Approve to relaunch.");
    btnApproveOptimized.disabled = false;
  } catch (err) {
    console.error(err);
    alert("Failed to fetch metrics / optimize.");
    setStatus("Error during optimization.");
    btnOptimize.disabled = false;
  }
}

async function approveOptimized() {
  if (!currentCampaignId) return;
  setStatus("Scheduling optimized campaign...");
  btnApproveOptimized.disabled = true;

  try {
    const res = await fetch(`/campaigns/${currentCampaignId}/approve-optimized`, {
      method: "POST",
    });
    if (!res.ok) {
      throw new Error(`Backend error: ${res.status}`);
    }
    const data = await res.json();
    setPhase(data.phase);
    setStatus("Optimized campaign scheduled. Full optimization loop complete.");
  } catch (err) {
    console.error(err);
    alert("Failed to schedule optimized campaign.");
    setStatus("Error scheduling optimized campaign.");
    btnApproveOptimized.disabled = false;
  }
}

btnPlan.addEventListener("click", planCampaign);
btnReset.addEventListener("click", resetUI);
btnApproveInitial.addEventListener("click", approveInitial);
btnOptimize.addEventListener("click", fetchMetricsAndOptimize);
btnApproveOptimized.addEventListener("click", approveOptimized);

