/*
 * Description: Client-side logic for Snap & Cook. Manages a five-state flow:
 *   1. upload    — file picker + preferences form
 *   2. loading   — polling until AWAITING_CONFIRMATION
 *   3. verify    — user edits detected ingredients, reviews preferences
 *   4. generating — polling until COMPLETE after POST /confirm
 *   5. results   — recipe cards displayed
 * Also handles the ?id= query-string so shareable links auto-load a prior
 * result. All API calls use window.API_BASE_URL from config.js — never
 * hardcode a URL in this file.
 * Last Modified By: bvela
 * Created: 2026-07-01
 * Last Modified:
 *     2026-07-01 - File created.
 *     2026-07-01 - Added preferences form, ingredient verification step,
 *                  POST /confirm flow.
 *     2026-07-01 - Added settings panel (gear icon): API URL + key persisted
 *                  to localStorage, override config.js at runtime.
 *     2026-07-01 - Added requireApiConfigured() guard (blocks upload/share-link
 *                  load when no URL is set, opens settings panel with error).
 *                  Fixed share button clipboard fallback for HTTP contexts.
 *                  Added _fallbackCopy() with textarea + window.prompt last resort.
 *     2026-07-01 - requireApiConfigured() now checks localStorage only (ignores
 *                  config.js defaults): API URL must be explicitly saved in
 *                  settings panel before the app can run. API key removed.
 */

/* ============================================================
   Constants
   ============================================================ */

const POLL_INTERVAL_MS   = 2000;
const POLL_TIMEOUT_MS    = 60000;

const LS_KEY_API_URL = "snapcook_api_url";

/* ============================================================
   Settings helpers — localStorage overrides config.js
   ============================================================ */

/**
 * Returns the active API base URL. localStorage value takes priority over
 * window.API_BASE_URL (injected from config.js by Terraform).
 *
 * @returns {string}
 */
function getApiUrl() {
  return localStorage.getItem(LS_KEY_API_URL) || window.API_BASE_URL || "";
}

/**
 * Checks that the API URL has been explicitly saved in localStorage via the
 * settings panel. config.js defaults are intentionally ignored — the URL must
 * be entered manually before the app can be used.
 *
 * @returns {boolean} true if a valid URL is saved, false otherwise.
 */
function requireApiConfigured() {
  const savedUrl = localStorage.getItem(LS_KEY_API_URL) || "";

  if (!savedUrl || !savedUrl.startsWith("http")) {
    openSettings();
    _showSettingsStatus(
      "Enter your API Gateway URL above to continue.",
      "error"
    );
    return false;
  }

  return true;
}

/**
 * Thin wrapper around fetch() that prepends the API base URL to every request.
 *
 * @param {string} path - Path relative to the API base URL (e.g. "/analyze").
 * @param {RequestInit} [options] - Standard fetch options.
 * @returns {Promise<Response>}
 */
function apiFetch(path, options = {}) {
  return fetch(`${getApiUrl()}${path}`, options);
}

/* ============================================================
   State
   ============================================================ */

/** @type {string|null} */
let currentRequestId = null;

/** @type {number|null} */
let pollingTimer = null;

/** @type {number|null} */
let pollingStart = null;

/** @type {string} */
let pollingTarget = "AWAITING_CONFIRMATION"; // changes to "COMPLETE" after confirm

/** Current list of ingredient strings shown in the verify step. @type {string[]} */
let verifyIngredients = [];

/** Preferences captured from the upload form. @type {object} */
let capturedPreferences = {};

/* ============================================================
   DOM references
   ============================================================ */

let dom = {};

/* ============================================================
   Entry point
   ============================================================ */

document.addEventListener("DOMContentLoaded", init);

/**
 * Initialises the app: wires events, checks URL for a pre-existing ?id= param.
 */
function init() {
  dom = {
    uploadSection:     document.getElementById("upload-section"),
    uploadForm:        document.getElementById("upload-form"),
    dropZone:          document.getElementById("drop-zone"),
    fileInput:         document.getElementById("file-input"),
    filePreview:       document.getElementById("file-preview"),
    previewImg:        document.getElementById("preview-img"),
    previewName:       document.getElementById("preview-name"),
    submitBtn:         document.getElementById("submit-btn"),
    recipeCountInput:  document.getElementById("recipe-count"),
    recipeCountOutput: document.getElementById("recipe-count-value"),
    maxPrepTime:       document.getElementById("max-prep-time"),
    loadingSection:    document.getElementById("loading-section"),
    loadingText:       document.getElementById("loading-text"),
    verifySection:     document.getElementById("verify-section"),
    verifyTags:        document.getElementById("verify-tags"),
    addIngredientInput: document.getElementById("add-ingredient-input"),
    addIngredientBtn:  document.getElementById("add-ingredient-btn"),
    prefsSummary:      document.getElementById("prefs-summary"),
    generateBtn:       document.getElementById("generate-btn"),
    generatingSection: document.getElementById("generating-section"),
    resultsSection:    document.getElementById("results-section"),
    copyLinkBtn:       document.getElementById("copy-link-btn"),
    newRecipeBtn:      document.getElementById("new-recipe-btn"),
    ingredientTags:    document.getElementById("ingredient-tags"),
    recipeGrid:        document.getElementById("recipe-grid"),
    errorSection:      document.getElementById("error-section"),
    errorMessage:      document.getElementById("error-message"),
    retryBtn:          document.getElementById("retry-btn"),
    toast:             document.getElementById("toast"),
    // Settings panel
    settingsBtn:     document.getElementById("settings-btn"),
    settingsOverlay: document.getElementById("settings-overlay"),
    settingsClose:   document.getElementById("settings-close"),
    settingsApiUrl:  document.getElementById("settings-api-url"),
    settingsSave:    document.getElementById("settings-save"),
    settingsClear:   document.getElementById("settings-clear"),
    settingsStatus:  document.getElementById("settings-status"),
  };

  initSettings();

  // Range slider live update
  dom.recipeCountInput.addEventListener("input", () => {
    dom.recipeCountOutput.value = dom.recipeCountInput.value;
    dom.recipeCountInput.setAttribute("aria-valuenow", dom.recipeCountInput.value);
  });

  dom.uploadForm.addEventListener("submit", handleUpload);
  dom.fileInput.addEventListener("change", handleFileSelect);
  dom.addIngredientBtn.addEventListener("click", handleAddIngredient);
  dom.addIngredientInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); handleAddIngredient(); }
  });
  dom.generateBtn.addEventListener("click", handleConfirm);
  dom.copyLinkBtn.addEventListener("click", handleCopyLink);
  dom.newRecipeBtn.addEventListener("click", resetToUpload);
  dom.retryBtn.addEventListener("click", resetToUpload);
  setupDropZone();

  // Auto-load from ?id= (shareable link)
  const params = new URLSearchParams(window.location.search);
  const preloadId = params.get("id");
  if (preloadId) {
    if (!requireApiConfigured()) return;
    currentRequestId = preloadId;
    showSection("generating");
    pollingTarget = "COMPLETE";
    setLoadingText("Fetching your recipes…");
    startPolling(preloadId);
  }
}

/* ============================================================
   Section visibility
   ============================================================ */

/**
 * Shows exactly one app section; hides all others.
 *
 * @param {"upload"|"loading"|"verify"|"generating"|"results"|"error"} name
 */
function showSection(name) {
  dom.uploadSection.classList.toggle("hidden",     name !== "upload");
  dom.loadingSection.classList.toggle("hidden",    name !== "loading");
  dom.verifySection.classList.toggle("hidden",     name !== "verify");
  dom.generatingSection.classList.toggle("hidden", name !== "generating");
  dom.resultsSection.classList.toggle("hidden",    name !== "results");
  dom.errorSection.classList.toggle("hidden",      name !== "error");
}

/**
 * @param {string} message
 */
function setLoadingText(message) {
  dom.loadingText.textContent = message;
}

/* ============================================================
   Upload form
   ============================================================ */

/**
 * Handles file selection via the file input.
 *
 * @param {Event} event
 */
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (file) showFilePreview(file);
}

/**
 * Renders a thumbnail preview and enables the submit button.
 *
 * @param {File} file
 */
function showFilePreview(file) {
  dom.dropZone.classList.add("has-file");
  dom.filePreview.classList.remove("hidden");
  dom.previewName.textContent = file.name;
  dom.submitBtn.disabled = false;

  const reader = new FileReader();
  reader.onload = (e) => { dom.previewImg.src = e.target.result; };
  reader.readAsDataURL(file);
}

/**
 * Reads the current preference values from the upload form.
 *
 * @returns {{ recipe_count: number, max_prep_time: string, dietary: string[] }}
 */
function readPreferences() {
  const dietary = Array.from(
    dom.uploadForm.querySelectorAll('input[name="dietary"]:checked')
  ).map((el) => el.value);

  return {
    recipe_count: parseInt(dom.recipeCountInput.value, 10),
    max_prep_time: dom.maxPrepTime.value,
    dietary,
  };
}

/**
 * Handles form submission: POSTs the image to /analyze and starts polling.
 *
 * @param {Event} event
 */
async function handleUpload(event) {
  event.preventDefault();

  const file = dom.fileInput.files[0];
  if (!file) {
    showError("Please select an image file before submitting.");
    return;
  }

  if (!requireApiConfigured()) return;

  capturedPreferences = readPreferences();
  showSection("loading");
  setLoadingText("Uploading image…");

  const formData = new FormData();
  formData.append("image", file);

  try {
    const response = await apiFetch("/analyze", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}: ${await response.text()}`);
    }

    const data = await response.json();
    if (!data.requestId) throw new Error("No requestId in server response.");

    currentRequestId = data.requestId;
    setLoadingText("Analysing ingredients…");
    pollingTarget = "AWAITING_CONFIRMATION";
    startPolling(data.requestId);
  } catch (err) {
    showError(`Upload failed: ${err.message}`);
  }
}

/* ============================================================
   Polling
   ============================================================ */

/**
 * Starts polling GET /recipes/{requestId} at POLL_INTERVAL_MS.
 *
 * @param {string} requestId
 */
function startPolling(requestId) {
  pollingStart = Date.now();
  pollingTimer = setInterval(() => poll(requestId), POLL_INTERVAL_MS);
  poll(requestId); // immediate first check
}

/** Stops the active polling interval. */
function stopPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

/**
 * Fetches /recipes/{requestId} and reacts to the returned status.
 *
 * @param {string} requestId
 */
async function poll(requestId) {
  if (Date.now() - pollingStart > POLL_TIMEOUT_MS) {
    stopPolling();
    showError("Processing timed out after 60 seconds. Please try again.");
    return;
  }

  try {
    const response = await apiFetch(`/recipes/${requestId}`);

    if (response.status === 404) return; // not yet written — keep waiting

    if (!response.ok) throw new Error(`Server returned ${response.status}`);

    const data = await response.json();

    if (data.status === "AWAITING_CONFIRMATION" && pollingTarget === "AWAITING_CONFIRMATION") {
      stopPolling();
      showVerifyStep(data.ingredients || []);
    } else if (data.status === "COMPLETE" && pollingTarget === "COMPLETE") {
      stopPolling();
      renderResults(data);
    } else if (data.status === "FAILED") {
      stopPolling();
      showError("Recipe generation failed. Please try again with a clearer photo.");
    }
    // PROCESSING / GENERATING → keep polling
  } catch (err) {
    stopPolling();
    showError(`Failed to fetch status: ${err.message}`);
  }
}

/* ============================================================
   Ingredient verification step
   ============================================================ */

/**
 * Populates and shows the ingredient verification UI.
 *
 * @param {string[]} detectedIngredients
 */
function showVerifyStep(detectedIngredients) {
  verifyIngredients = [...detectedIngredients];
  renderVerifyTags();
  renderPrefsSummary();
  showSection("verify");
}

/** Re-renders the removable ingredient tag list. */
function renderVerifyTags() {
  dom.verifyTags.innerHTML = "";

  if (verifyIngredients.length === 0) {
    const empty = document.createElement("span");
    empty.className = "verify-tags-empty";
    empty.textContent = "No ingredients detected — add some below.";
    dom.verifyTags.appendChild(empty);
    return;
  }

  verifyIngredients.forEach((ingredient, index) => {
    const tag = document.createElement("span");
    tag.className = "verify-tag";

    const label = document.createElement("span");
    label.textContent = ingredient;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "verify-tag-remove";
    removeBtn.setAttribute("aria-label", `Remove ${ingredient}`);
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      verifyIngredients.splice(index, 1);
      renderVerifyTags();
    });

    tag.appendChild(label);
    tag.appendChild(removeBtn);
    dom.verifyTags.appendChild(tag);
  });
}

/**
 * Renders a read-only summary of the captured preferences inside the verify step.
 */
function renderPrefsSummary() {
  const p = capturedPreferences;
  dom.prefsSummary.innerHTML = "";

  const badges = [
    `${p.recipe_count} recipe${p.recipe_count !== 1 ? "s" : ""}`,
    p.max_prep_time ? `≤${p.max_prep_time} min` : "No time limit",
    ...(p.dietary || []),
  ];

  badges.forEach((text) => {
    const badge = document.createElement("span");
    badge.className = "pref-badge";
    badge.textContent = text;
    dom.prefsSummary.appendChild(badge);
  });
}

/**
 * Adds a manually-typed ingredient to the verify list.
 */
function handleAddIngredient() {
  const value = dom.addIngredientInput.value.trim();
  if (!value) return;

  const normalised = value.charAt(0).toUpperCase() + value.slice(1);
  if (!verifyIngredients.includes(normalised)) {
    verifyIngredients.push(normalised);
    renderVerifyTags();
  }
  dom.addIngredientInput.value = "";
  dom.addIngredientInput.focus();
}

/* ============================================================
   Confirm step — POST /recipes/{id}/confirm
   ============================================================ */

/**
 * Sends confirmed ingredients + preferences to the API and starts generation polling.
 */
async function handleConfirm() {
  if (verifyIngredients.length === 0) {
    showToast("Add at least one ingredient before generating.");
    return;
  }

  showSection("generating");
  pollingTarget = "COMPLETE";

  try {
    const response = await apiFetch(
      `/recipes/${currentRequestId}/confirm`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ingredients: verifyIngredients,
          preferences: capturedPreferences,
        }),
      }
    );

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || `Server returned ${response.status}`);
    }

    startPolling(currentRequestId);
  } catch (err) {
    showError(`Could not start recipe generation: ${err.message}`);
  }
}

/* ============================================================
   Results rendering
   ============================================================ */

/**
 * Renders ingredient tags and recipe cards in the results section.
 *
 * @param {{ ingredients: string[], recipes: RecipeObject[] }} data
 * @typedef {{ name: string, ingredients: string[], instructions: string[],
 *             prep_time?: string, cook_time?: string }} RecipeObject
 */
function renderResults(data) {
  // Ingredient tags
  dom.ingredientTags.innerHTML = "";
  if (Array.isArray(data.ingredients) && data.ingredients.length > 0) {
    data.ingredients.forEach((ingredient) => {
      const tag = document.createElement("span");
      tag.className = "ingredient-tag";
      tag.textContent = ingredient;
      dom.ingredientTags.appendChild(tag);
    });
    document.getElementById("ingredients-section").classList.remove("hidden");
  } else {
    document.getElementById("ingredients-section").classList.add("hidden");
  }

  // Recipe cards
  dom.recipeGrid.innerHTML = "";
  const recipes = Array.isArray(data.recipes) ? data.recipes : [];
  recipes.forEach((recipe, i) => dom.recipeGrid.appendChild(buildRecipeCard(recipe, i + 1)));

  showSection("results");
}

/**
 * Builds and returns a recipe card DOM element.
 *
 * @param {RecipeObject} recipe
 * @param {number} number - 1-based index.
 * @returns {HTMLElement}
 */
function buildRecipeCard(recipe, number) {
  const card = document.createElement("article");
  card.className = "recipe-card";
  card.setAttribute("aria-label", `Recipe ${number}: ${recipe.name}`);

  const header = document.createElement("div");
  header.className = "recipe-card-header";

  const label = document.createElement("span");
  label.className = "recipe-number";
  label.textContent = `Recipe ${number}`;

  const name = document.createElement("h3");
  name.className = "recipe-name";
  name.textContent = recipe.name;

  header.appendChild(label);
  header.appendChild(name);

  const badges = buildTimeBadges(recipe.prep_time, recipe.cook_time);
  if (badges) header.appendChild(badges);

  card.appendChild(header);
  card.appendChild(Object.assign(document.createElement("hr"), { className: "recipe-divider" }));

  if (Array.isArray(recipe.ingredients) && recipe.ingredients.length > 0) {
    const title = Object.assign(document.createElement("p"), {
      className: "recipe-section-title",
      textContent: "Ingredients",
    });
    const list = document.createElement("ul");
    list.className = "recipe-ingredients";
    recipe.ingredients.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    card.appendChild(title);
    card.appendChild(list);
  }

  if (Array.isArray(recipe.instructions) && recipe.instructions.length > 0) {
    const title = Object.assign(document.createElement("p"), {
      className: "recipe-section-title",
      textContent: "Instructions",
    });
    const list = document.createElement("ol");
    list.className = "recipe-instructions";
    recipe.instructions.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      list.appendChild(li);
    });
    card.appendChild(title);
    card.appendChild(list);
  }

  return card;
}

/**
 * Builds a prep/cook time badge row, or returns null if neither value exists.
 *
 * @param {string|undefined} prepTime
 * @param {string|undefined} cookTime
 * @returns {HTMLElement|null}
 */
function buildTimeBadges(prepTime, cookTime) {
  if (!prepTime && !cookTime) return null;
  const row = document.createElement("div");
  row.className = "recipe-time-badges";
  if (prepTime) {
    const b = Object.assign(document.createElement("span"), {
      className: "time-badge",
      textContent: `⏱ Prep: ${prepTime}`,
    });
    row.appendChild(b);
  }
  if (cookTime) {
    const b = Object.assign(document.createElement("span"), {
      className: "time-badge",
      textContent: `🍳 Cook: ${cookTime}`,
    });
    row.appendChild(b);
  }
  return row;
}

/* ============================================================
   Error handling
   ============================================================ */

/**
 * Shows the error section with a human-readable message.
 *
 * @param {string} message
 */
function showError(message) {
  stopPolling();
  dom.errorMessage.textContent = message;
  showSection("error");
}

/**
 * Resets the entire UI back to the upload state.
 */
function resetToUpload() {
  stopPolling();
  currentRequestId = null;
  verifyIngredients = [];
  capturedPreferences = {};
  pollingTarget = "AWAITING_CONFIRMATION";

  dom.fileInput.value = "";
  dom.filePreview.classList.add("hidden");
  dom.dropZone.classList.remove("has-file");
  dom.submitBtn.disabled = true;
  dom.previewImg.src = "";
  dom.verifyTags.innerHTML = "";
  dom.prefsSummary.innerHTML = "";

  showSection("upload");

  const url = new URL(window.location.href);
  url.searchParams.delete("id");
  window.history.replaceState({}, "", url.toString());
}

/* ============================================================
   Shareable link
   ============================================================ */

/**
 * Copies a URL with ?id= to the clipboard and shows a toast.
 * Falls back to a textarea-select approach for HTTP (non-secure) contexts,
 * and as a last resort prompts the user with the URL to copy manually.
 */
function handleCopyLink() {
  if (!currentRequestId) return;
  const base = window.location.origin + window.location.pathname.replace(/\/$/, "");
  const url = `${base}?id=${currentRequestId}`;

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(url)
      .then(() => showToast("Link copied to clipboard!"))
      .catch(() => _fallbackCopy(url));
  } else {
    _fallbackCopy(url);
  }
}

/**
 * Copies text using a hidden textarea + execCommand. Falls back to window.prompt
 * so the user can copy manually if execCommand is blocked.
 *
 * @param {string} text - The text to copy.
 */
function _fallbackCopy(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;top:-9999px;left:-9999px;opacity:0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try {
    const ok = document.execCommand("copy");
    if (ok) {
      showToast("Link copied to clipboard!");
    } else {
      window.prompt("Copy this shareable link:", text);
    }
  } catch (_e) {
    window.prompt("Copy this shareable link:", text);
  } finally {
    document.body.removeChild(ta);
  }
}

/**
 * Shows a brief toast notification.
 *
 * @param {string} message
 */
function showToast(message) {
  dom.toast.textContent = message;
  dom.toast.classList.add("visible");
  setTimeout(() => dom.toast.classList.remove("visible"), 2500);
}

/* ============================================================
   Settings panel
   ============================================================ */

/**
 * Wires the settings panel open/close logic, pre-fills saved values, and
 * handles save/clear actions.
 */
function initSettings() {
  // Pre-fill with whatever is already saved in localStorage
  _refreshSettingsFields();
  _updateSettingsIndicator();

  dom.settingsBtn.addEventListener("click", openSettings);
  dom.settingsClose.addEventListener("click", closeSettings);

  // Close on overlay backdrop click (outside the panel)
  dom.settingsOverlay.addEventListener("click", (e) => {
    if (e.target === dom.settingsOverlay) closeSettings();
  });

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !dom.settingsOverlay.classList.contains("hidden")) {
      closeSettings();
    }
  });

  dom.settingsSave.addEventListener("click", saveSettings);
  dom.settingsClear.addEventListener("click", clearSettings);
}

/** Opens the settings overlay and sets aria-expanded on the trigger. */
function openSettings() {
  _refreshSettingsFields();
  dom.settingsOverlay.classList.remove("hidden");
  dom.settingsBtn.setAttribute("aria-expanded", "true");
  dom.settingsApiUrl.focus();
}

/** Closes the settings overlay. */
function closeSettings() {
  dom.settingsOverlay.classList.add("hidden");
  dom.settingsBtn.setAttribute("aria-expanded", "false");
  dom.settingsStatus.classList.add("hidden");
  dom.settingsStatus.className = "settings-status hidden";
}

/**
 * Validates and persists the API URL to localStorage, then shows a status message.
 */
function saveSettings() {
  const rawUrl = dom.settingsApiUrl.value.trim().replace(/\/$/, "");

  if (!rawUrl) {
    _showSettingsStatus("API URL is required.", "error");
    return;
  }

  if (!rawUrl.startsWith("https://") && !rawUrl.startsWith("http://")) {
    _showSettingsStatus("URL must start with https:// or http://", "error");
    return;
  }

  localStorage.setItem(LS_KEY_API_URL, rawUrl);
  _updateSettingsIndicator();
  _showSettingsStatus("Settings saved.", "success");
  setTimeout(closeSettings, 900);
}

/**
 * Clears the saved API URL and resets the field.
 */
function clearSettings() {
  localStorage.removeItem(LS_KEY_API_URL);
  _refreshSettingsFields();
  _updateSettingsIndicator();
  _showSettingsStatus("Reset to defaults.", "success");
}

/** Fills the URL input from localStorage (or shows empty if not set). */
function _refreshSettingsFields() {
  dom.settingsApiUrl.value = localStorage.getItem(LS_KEY_API_URL) || "";
}

/**
 * Adds/removes the orange indicator dot on the gear button when a URL is saved.
 */
function _updateSettingsIndicator() {
  dom.settingsBtn.classList.toggle("has-custom", !!localStorage.getItem(LS_KEY_API_URL));
}

/**
 * Shows a status message inside the settings panel.
 *
 * @param {string} message
 * @param {"success"|"error"} type
 */
function _showSettingsStatus(message, type) {
  dom.settingsStatus.textContent = message;
  dom.settingsStatus.className = `settings-status ${type}`;
}

/* ============================================================
   Drag-and-drop
   ============================================================ */

/** Attaches drag-and-drop listeners to the drop zone. */
function setupDropZone() {
  const zone = dom.dropZone;

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      const dt = new DataTransfer();
      dt.items.add(file);
      dom.fileInput.files = dt.files;
      showFilePreview(file);
    }
  });
}