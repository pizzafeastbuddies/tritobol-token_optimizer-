"use strict";

const sourceText = document.querySelector("#source-text");
const textFile = document.querySelector("#text-file");
const characterCount = document.querySelector("#character-count");
const optimizeButton = document.querySelector("#optimize-button");
const appStatus = document.querySelector("#app-status");
const tokenizer = document.querySelector("#tokenizer");
const customTokenizer = document.querySelector("#custom-tokenizer");
const tokenizerFile = document.querySelector("#tokenizer-file");
const tokenizerFileName = document.querySelector("#tokenizer-file-name");
const budget = document.querySelector("#token-budget");
const demoButton = document.querySelector("#demo-button");
const demoState = document.querySelector("#demo-state");
const truncationNote = document.querySelector("#truncation-note");

function updateInputState() {
  const length = sourceText.value.length;
  characterCount.textContent = `${length.toLocaleString()} ${length === 1 ? "character" : "characters"}`;
  optimizeButton.disabled = sourceText.value.trim().length === 0;
}

function showStatus(message, kind = "info") {
  appStatus.textContent = message;
  appStatus.dataset.kind = kind;
  appStatus.hidden = false;
}

function hideStatus() {
  appStatus.textContent = "";
  appStatus.hidden = true;
  delete appStatus.dataset.kind;
}

sourceText.addEventListener("input", () => {
  updateInputState();
  hideStatus();
});

textFile.addEventListener("change", async () => {
  const file = textFile.files && textFile.files[0];
  if (!file) return;

  showStatus(`Loading ${file.name}…`, "loading");
  await new Promise((resolve) => window.requestAnimationFrame(resolve));

  try {
    const bytes = await file.arrayBuffer();
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    sourceText.value = text;
    updateInputState();
    showStatus(`Loaded ${file.name}. The original file has not been changed.`);
  } catch (error) {
    if (error instanceof TypeError) {
      showStatus("This file is not valid UTF-8. Choose a UTF-8 text file; your existing text is unchanged.", "error");
    } else {
      showStatus("The file could not be read. Choose another file or paste text instead.", "error");
    }
  } finally {
    textFile.value = "";
  }
});

tokenizer.addEventListener("change", () => {
  const useCustom = tokenizer.value === "custom";
  customTokenizer.hidden = !useCustom;
  if (!useCustom) {
    tokenizerFile.value = "";
    tokenizerFileName.textContent = "No file selected";
  }
});

tokenizerFile.addEventListener("change", () => {
  const file = tokenizerFile.files && tokenizerFile.files[0];
  tokenizerFileName.textContent = file ? file.name : "No file selected";
  if (file) {
    showStatus("File selected for the prototype only. Tokenizer compatibility is not checked until integration.");
  }
});

optimizeButton.addEventListener("click", () => {
  if (!sourceText.value.trim()) {
    showStatus("Add some text before continuing.", "error");
    sourceText.focus();
    return;
  }

  if (budget.value && (!Number.isInteger(Number(budget.value)) || Number(budget.value) < 1)) {
    showStatus("Enter a whole-number token budget greater than zero, or leave it blank.", "error");
    budget.focus();
    return;
  }

  if (tokenizer.value === "custom" && (!tokenizerFile.files || tokenizerFile.files.length === 0)) {
    showStatus("Choose a local tokenizer.json, or switch back to the bundled tokenizer.", "error");
    tokenizerFile.focus();
    return;
  }

  demoState.hidden = true;
  truncationNote.hidden = true;
  demoButton.setAttribute("aria-expanded", "false");
  demoButton.innerHTML = 'Show sample screen state <span aria-hidden="true">→</span>';
  showStatus("The optimizer is not connected in this prototype. Nothing was processed and no result or token statistics were generated.", "error");
});

demoButton.addEventListener("click", () => {
  const isOpening = demoState.hidden;
  demoState.hidden = !isOpening;
  truncationNote.hidden = !isOpening;
  demoButton.setAttribute("aria-expanded", String(isOpening));
  demoButton.innerHTML = isOpening
    ? 'Hide sample screen state <span aria-hidden="true">↑</span>'
    : 'Show sample screen state <span aria-hidden="true">→</span>';

  if (isOpening) {
    showStatus("Sample screen state only. It is not optimizer output; no counts or savings are available.");
  }
});

updateInputState();
