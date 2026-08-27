"use strict";

const telegram = window.Telegram?.WebApp;
const form = document.getElementById("calculator-form");
const bulkText = document.getElementById("bulk-text");
const error = document.getElementById("input-error");
const resultPanel = document.getElementById("result-panel");
const resultLabel = document.getElementById("result-label");
const resultValue = document.getElementById("result-value");
const vatDetails = document.getElementById("vat-details");
const bulkResult = document.getElementById("bulk-result");
const sendButton = document.getElementById("send-button");
let latestCalculation = null;
const bulkLinePattern = /^(?:(?:https?:\/\/)?t\.me\/|@)([A-Za-z0-9_]{5,32})\/?\s+([0-9]+(?:[.,][0-9]+)?)$/i;

function getNdsMode() {
  return document.querySelector('input[name="nds-mode"]:checked').value;
}

if (telegram) {
  telegram.ready();
  telegram.expand();
}

function parsePositiveNumber(value) {
  const normalized = value.trim().replace(",", ".");
  if (!normalized || !/^\d+(?:\.\d+)?$/.test(normalized)) {
    throw new Error("Введите положительное число без лишних символов.");
  }

  const number = Number(normalized);
  if (!Number.isFinite(number) || number <= 0) {
    throw new Error("Число должно быть больше нуля.");
  }
  if (number > 1e100) {
    throw new Error("Число слишком большое.");
  }
  return number;
}

function calculatePrice(inputNumber, erid, urgent, gazprom) {
  let result = inputNumber / 0.8 * 1.4;
  if (erid) result *= 1.03;
  if (urgent) result *= 1.1;
  result /= gazprom ? 0.94 : 0.87;
  return Math.round((result + Number.EPSILON) * 100) / 100;
}

function calculateVatDetails(finalPrice, ndsMode) {
  if (ndsMode === "none") {
    return { displayedPrice: finalPrice, vat: 0 };
  }
  const vat = Math.round((finalPrice * 0.05 / 1.05 + Number.EPSILON) * 100) / 100;
  const displayedPrice = ndsMode === "inside"
    ? finalPrice
    : Math.round((finalPrice - vat + Number.EPSILON) * 100) / 100;
  return { displayedPrice, vat };
}

function formatMoney(value) {
  return value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function buildBulkPreview(text, options) {
  const lines = [];
  text.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) return;
    const match = bulkLinePattern.exec(line);
    if (!match) {
      lines.push(`⚠️ Не удалось распознать: ${line}`);
      return;
    }

    const inputNumber = parsePositiveNumber(match[2]);
    const finalPrice = calculatePrice(inputNumber, options.erid, options.urgent, options.gazprom);
    const { displayedPrice, vat } = calculateVatDetails(finalPrice, options.nds_mode);
    const details = options.nds_mode === "none"
      ? `${formatMoney(displayedPrice)} руб.`
      : options.nds_mode === "inside"
      ? `${formatMoney(displayedPrice)} руб., в том числе НДС (НДС ${formatMoney(vat)} руб.)`
      : `${formatMoney(displayedPrice)} руб. + НДС ${formatMoney(vat)} руб. = ${formatMoney(finalPrice)} руб.`;
    lines.push(`@${match[1]} (${details})`);
  });
  return lines;
}

function showError(message) {
  error.textContent = message;
  bulkText.setAttribute("aria-invalid", "true");
}

function sendCalculationToChat() {
  if (!latestCalculation) {
    showError("Сначала выполните расчёт.");
    return;
  }
  if (!telegram || typeof telegram.sendData !== "function") {
    showError("Откройте мини-приложение через Telegram, чтобы отправить результат.");
    return;
  }

  try {
    telegram.sendData(JSON.stringify(latestCalculation));
  } catch (sendError) {
    showError("Не удалось отправить результат. Откройте калькулятор заново.");
    console.error("Ошибка отправки Web App data:", sendError);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  error.textContent = "";
  bulkText.removeAttribute("aria-invalid");

  if (!bulkText.value.trim()) {
    error.textContent = "Введите хотя бы один канал.";
    bulkText.setAttribute("aria-invalid", "true");
    return;
  }

  const payload = {
    mode: "bulk",
    bulk_text: bulkText.value,
    erid: document.getElementById("erid").checked,
    urgent: document.getElementById("urgent").checked,
    gazprom: document.getElementById("gazprom").checked,
    nds_mode: getNdsMode(),
    nds: getNdsMode() !== "none",
  };
  try {
    const previewLines = buildBulkPreview(bulkText.value, payload);
    if (!previewLines.length) {
      throw new Error("В списке нет непустых строк.");
    }
    latestCalculation = payload;
    resultLabel.textContent = "Результаты списка";
    resultValue.textContent = "";
    vatDetails.textContent = "Проверьте список перед отправкой в чат.";
    bulkResult.textContent = previewLines.join("\n");
    bulkResult.hidden = false;
    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (calculationError) {
    latestCalculation = null;
    resultPanel.hidden = true;
    showError(calculationError.message);
  }
});

sendButton.addEventListener("click", () => {
  sendCalculationToChat();
});
