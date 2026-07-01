/*
 * Description: Client-side application logic for Snap & Cook. Handles image
 *              upload to POST /analyze, polls GET /recipes/{requestId} until
 *              the backend completes processing, and renders recipe cards.
 *              Also reads ?id= from the URL query string so shareable links
 *              auto-load a prior result without re-uploading.
 *              All API calls use window.API_BASE_URL from config.js — never
 *              hardcode a URL in this file.
 * Last Modified By: bvela
 * Created: 2026-07-01
 * Last Modified:
 *     2026-07-01 - File created.
 */

/* ============================================================
   Constants
   ============================================================ */

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS  = 60000;

const LOADING_MESSAGES = [
  "Uploading image…",
  "Analyzing ingredients…",
  "Generating recipes…",
  "Almost there…",
];

/* ============================================================
   State
   ============================================================ */

/** @type {string|null} */
let currentRequestId = null;

/** @type {number|null} */
let pollingTimer = null;

/** @type {number|null} */
let pollingStart = null;

/** @type {number} */
let loadingMessageIndex = 0;

/** @type {number|null} */
let loadingMessageTimer = null;

/* ============================================================
   DOM references — resolved once on DOMContentLoaded
   ============================================================ */

let dom = {};

/* ============================================================
   Entry point
   ============================================================ */

document.addEventListener("DOMContentLoaded", init);

/**
 * Initialises the application. Checks the URL for a pre-existing ?id= query
 * parameter (shareable links) and sets up all event listeners.
 */
function init() {
  dom = {
    uploadSection:   document.getElementById("upload-section"),
    uploadForm:      document.getElementById("upload-form"),
    dropZone:        document.getElementById("drop-zone"),
    fileInput:       document.getElementById("file-input"),
    filePreview:     document.getElementById("file-preview"),
    previewImg:      document.getElementById("preview-img"),
    previewName:     document.getElementById("preview-name"),
    submitBtn:       document.getElementById("submit-btn"),
    loadingSection:  document.getElementById("loading-section"),
    loadingText:     document.getElementById("loading-text"),
    resultsSection:  document.getElementById("results-section"),
    copyLinkBtn:     document.getElementById("copy-link-btn"),
    ingredientTags:  document.getElementById("ingredient-tags"),
    recipeGrid:      document.getElementById("recipe-grid"),
    errorSection:    document.getElementById("error-section"),
    errorMessage:    document.getElementById("error-message"),
    retryBtn:        document.getElementById("retry-btn"),
    toast:           document.getElementById("toast"),
  };

  dom.uploadForm.addEventListener("submit", handleUpload);
  dom.fileInput.addEventListener("change", handleFileSelect);
  dom.copyLinkBtn.addEventListener("click", handleCopyLink);
  dom.retryBtn.addEventListener("click", resetToUpload);
  setupDropZone();

  const params = new URLSearchParams(window.location.search);
  const preloadId = params.get("id");
  if (preloadId) {
    currentRequestId = preloadId;
    showSection("loading");
    setLoadingMessage("Fetching your recipes…");
    startPolling(preloadId);
  }
}

/* ============================================================
   Section visibility helpers
   ============================================================ */

/**
 * Shows exactly one of the four app sections; hides the rest.
 *
 * @param {"upload"|"loading"|"results"|"error"} name - Section to show.
 */
function showSection(name) {
  dom.uploadSection.classList.toggle("hidden",  name !== "upload");
  dom.loadingSection.classList.toggle("hidden", name !== "loading");
  dom.resultsSection.classList.toggle("hidden", name !== "results");
  dom.errorSection.classList.toggle("hidden",   name !== "error");
}

/**
 * Updates the loading section status text.
 *
 * @param {string} message - Human-readable status string.
 */
function setLoadingMessage(message) {
  dom.loadingText.textContent = message;
}

/* ============================================================
   Upload form
   ============================================================ */

/**
 * Handles file selection via the hidden file input. Shows a preview thumbnail
 * and enables the submit button.
 *
 * @param {Event} event - Change event from the file input.
 */
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  showFilePreview(file);
}

/**
 * Renders a thumbnail preview of the selected file inside the drop zone.
 *
 * @param {File} file - The selected image file.
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
 * Submits the selected image to POST /analyze and begins polling.
 *
 * @param {Event} event - Submit event from the upload form.
 */
async function handleUpload(event) {
  event.preventDefault();

  const file = dom.fileInput.files[0];
  if (!file) {
    showError("Please select an image file before submitting.");
    return;
  }

  showSection("loading");
  startLoadingMessages();

  const formData = new FormData();
  formData.append("image", file);

  try {
    const response = await fetch(`${window.API_BASE_URL}/analyze`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Server returned ${response.status}: ${body}`);
    }

    const data = await response.json();
    if (!data.requestId) {
      throw new Error("No requestId in server response.");
    }

    currentRequestId = data.requestId;
    startPolling(data.requestId);
  } catch (err) {
    stopLoadingMessages();
    showError(`Upload failed: ${err.message}`);
  }
}

/* ============================================================
   Polling
   ============================================================ */

/**
 * Begins polling GET /recipes/{requestId} at POLL_INTERVAL_MS until the status
 * is COMPLETE or FAILED, or until POLL_TIMEOUT_MS elapses.
 *
 * @param {string} requestId - The UUID returned by POST /analyze.
 */
function startPolling(requestId) {
  pollingStart = Date.now();
  pollingTimer = setInterval(() => poll(requestId), POLL_INTERVAL_MS);
  // Kick off an immediate first check rather than waiting one full interval.
  poll(requestId);
}

/**
 * Stops the active polling interval.
 */
function stopPolling() {
  if (pollingTimer !== null) {
    clearInterval(pollingTimer);
    pollingTimer = null;
  }
}

/**
 * Fetches the current recipe status for a request and handles the result.
 *
 * @param {string} requestId - The UUID to query.
 */
async function poll(requestId) {
  if (Date.now() - pollingStart > POLL_TIMEOUT_MS) {
    stopPolling();
    stopLoadingMessages();
    showError("Processing timed out after 60 seconds. Please try again.");
    return;
  }

  try {
    const response = await fetch(`${window.API_BASE_URL}/recipes/${requestId}`);

    if (response.status === 404) {
      // Not yet written — keep polling.
      return;
    }

    if (!response.ok) {
      throw new Error(`Server returned ${response.status}`);
    }

    const data = await response.json();

    if (data.status === "COMPLETE") {
      stopPolling();
      stopLoadingMessages();
      renderResults(data);
    } else if (data.status === "FAILED") {
      stopPolling();
      stopLoadingMessages();
      showError("Recipe generation failed. Please try again with a clearer photo.");
    }
    // PROCESSING → keep polling
  } catch (err) {
    stopPolling();
    stopLoadingMessages();
    showError(`Failed to fetch results: ${err.message}`);
  }
}

/* ============================================================
   Loading message rotation
   ============================================================ */

/**
 * Cycles through LOADING_MESSAGES every ~4 seconds to indicate progress.
 */
function startLoadingMessages() {
  loadingMessageIndex = 0;
  setLoadingMessage(LOADING_MESSAGES[0]);
  loadingMessageTimer = setInterval(() => {
    loadingMessageIndex = Math.min(
      loadingMessageIndex + 1,
      LOADING_MESSAGES.length - 1
    );
    setLoadingMessage(LOADING_MESSAGES[loadingMessageIndex]);
  }, 4000);
}

/**
 * Stops the loading message rotation timer.
 */
function stopLoadingMessages() {
  if (loadingMessageTimer !== null) {
    clearInterval(loadingMessageTimer);
    loadingMessageTimer = null;
  }
}

/* ============================================================
   Rendering
   ============================================================ */

/**
 * Renders the full results section: detected ingredient tags and recipe cards.
 *
 * @param {{ ingredients: string[], recipes: RecipeObject[] }} data - API response.
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
  recipes.forEach((recipe, index) => {
    dom.recipeGrid.appendChild(buildRecipeCard(recipe, index + 1));
  });

  showSection("results");
}

/**
 * Builds a recipe card DOM node.
 *
 * @param {RecipeObject} recipe - Single recipe object from the API.
 * @param {number} number - 1-based card index (shown as "Recipe 1", "Recipe 2", etc.).
 * @returns {HTMLElement} The assembled card element.
 */
function buildRecipeCard(recipe, number) {
  const card = document.createElement("article");
  card.className = "recipe-card";
  card.setAttribute("aria-label", `Recipe ${number}: ${recipe.name}`);

  // Header
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

  // Time badges
  const badges = buildTimeBadges(recipe.prep_time, recipe.cook_time);
  if (badges) header.appendChild(badges);

  card.appendChild(header);

  // Divider
  card.appendChild(document.createElement("hr")).className = "recipe-divider";

  // Ingredients
  if (Array.isArray(recipe.ingredients) && recipe.ingredients.length > 0) {
    const ingTitle = document.createElement("p");
    ingTitle.className = "recipe-section-title";
    ingTitle.textContent = "Ingredients";
    card.appendChild(ingTitle);

    const ingList = document.createElement("ul");
    ingList.className = "recipe-ingredients";
    recipe.ingredients.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      ingList.appendChild(li);
    });
    card.appendChild(ingList);
  }

  // Instructions
  if (Array.isArray(recipe.instructions) && recipe.instructions.length > 0) {
    const instTitle = document.createElement("p");
    instTitle.className = "recipe-section-title";
    instTitle.textContent = "Instructions";
    card.appendChild(instTitle);

    const instList = document.createElement("ol");
    instList.className = "recipe-instructions";
    recipe.instructions.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      instList.appendChild(li);
    });
    card.appendChild(instList);
  }

  return card;
}

/**
 * Builds the time badge row for prep/cook time if either value is present.
 *
 * @param {string|undefined} prepTime - Prep time string (e.g. "10 min").
 * @param {string|undefined} cookTime - Cook time string (e.g. "20 min").
 * @returns {HTMLElement|null} A div with badges, or null if neither is set.
 */
function buildTimeBadges(prepTime, cookTime) {
  if (!prepTime && !cookTime) return null;

  const row = document.createElement("div");
  row.className = "recipe-time-badges";

  if (prepTime) {
    const badge = document.createElement("span");
    badge.className = "time-badge";
    badge.textContent = `⏱ Prep: ${prepTime}`;
    row.appendChild(badge);
  }

  if (cookTime) {
    const badge = document.createElement("span");
    badge.className = "time-badge";
    badge.textContent = `🍳 Cook: ${cookTime}`;
    row.appendChild(badge);
  }

  return row;
}

/* ============================================================
   Error handling
   ============================================================ */

/**
 * Displays the error section with a human-readable message.
 *
 * @param {string} message - Error description shown to the user.
 */
function showError(message) {
  dom.errorMessage.textContent = message;
  showSection("error");
}

/**
 * Resets the UI back to the upload state and clears any previous selection.
 */
function resetToUpload() {
  stopPolling();
  stopLoadingMessages();
  currentRequestId = null;
  dom.fileInput.value = "";
  dom.filePreview.classList.add("hidden");
  dom.dropZone.classList.remove("has-file");
  dom.submitBtn.disabled = true;
  dom.previewImg.src = "";
  showSection("upload");

  // Remove ?id= from URL so a page refresh starts fresh.
  const url = new URL(window.location.href);
  url.searchParams.delete("id");
  window.history.replaceState({}, "", url.toString());
}

/* ============================================================
   Shareable link
   ============================================================ */

/**
 * Copies a shareable URL containing the current requestId to the clipboard
 * and shows a brief confirmation toast.
 */
function handleCopyLink() {
  if (!currentRequestId) return;

  const url = `${window.location.origin}${window.location.pathname}?id=${currentRequestId}`;

  navigator.clipboard.writeText(url).then(() => {
    showToast("Link copied to clipboard!");
  }).catch(() => {
    // Fallback for browsers without clipboard API.
    const input = document.createElement("input");
    input.value = url;
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    document.body.removeChild(input);
    showToast("Link copied!");
  });
}

/**
 * Shows a brief toast notification at the bottom of the viewport.
 *
 * @param {string} message - Text to display in the toast.
 */
function showToast(message) {
  dom.toast.textContent = message;
  dom.toast.classList.add("visible");
  setTimeout(() => { dom.toast.classList.remove("visible"); }, 2500);
}

/* ============================================================
   Drag-and-drop
   ============================================================ */

/**
 * Attaches drag-and-drop event listeners to the upload drop zone.
 */
function setupDropZone() {
  const zone = dom.dropZone;

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", () => {
    zone.classList.remove("drag-over");
  });

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");

    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      // Sync to the file input so the form picks it up on submit.
      const dt = new DataTransfer();
      dt.items.add(file);
      dom.fileInput.files = dt.files;
      showFilePreview(file);
    }
  });
}