(function () {
  "use strict";

  var VERIFY_PHONE_HINT_ID = "event-verify-phone-dependency-hint";

  function appendAriaDescription(input, descriptionId) {
    var describedBy = (input.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter(Boolean);
    if (describedBy.indexOf(descriptionId) === -1) describedBy.push(descriptionId);
    input.setAttribute("aria-describedby", describedBy.join(" "));
  }

  function initializePhoneOptionDependency() {
    var promptInput = document.getElementById("id_collect_phone");
    var verifyInput = document.getElementById("id_verify_phone");
    if (!promptInput || !verifyInput) return;

    var verifyContainer =
      verifyInput.closest("[class*='field-verify_phone']") ||
      verifyInput.closest(".field-line") ||
      verifyInput.closest(".form-row") ||
      verifyInput.parentElement;
    var dependencyHint = document.getElementById(VERIFY_PHONE_HINT_ID);

    appendAriaDescription(verifyInput, VERIFY_PHONE_HINT_ID);

    function syncVerifyState() {
      var disabled = !promptInput.checked;
      if (disabled) verifyInput.checked = false;
      verifyInput.disabled = disabled;
      verifyInput.setAttribute("aria-disabled", disabled ? "true" : "false");
      if (verifyContainer) {
        verifyContainer.classList.toggle("event-admin-dependent-disabled", disabled);
      }
      if (dependencyHint) {
        dependencyHint.textContent = disabled
          ? "Enable Prompt for Phone Number to make Verify phone available."
          : "Verify phone is available because Prompt for Phone Number is enabled.";
      }
    }

    promptInput.addEventListener("change", syncVerifyState);
    syncVerifyState();
  }

  function parseDateOnly(value) {
    var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
    if (!match) return null;

    var year = Number(match[1]);
    var month = Number(match[2]);
    var day = Number(match[3]);
    var timestamp = Date.UTC(year, month - 1, day);
    var date = new Date(timestamp);
    if (
      date.getUTCFullYear() !== year ||
      date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day
    ) {
      return null;
    }
    return timestamp;
  }

  function formatDateOnly(timestamp) {
    var date = new Date(timestamp);
    var year = String(date.getUTCFullYear()).padStart(4, "0");
    var month = String(date.getUTCMonth() + 1).padStart(2, "0");
    var day = String(date.getUTCDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function initializeDateRangeDependency() {
    var startInput = document.getElementById("id_date");
    var endInput = document.getElementById("id_end_date");
    if (!startInput || !endInput) return;

    var millisecondsPerDay = 24 * 60 * 60 * 1000;
    var initialStart = parseDateOnly(startInput.value);
    var initialEnd = parseDateOnly(endInput.value);
    var durationDays = 0;
    if (initialStart !== null && initialEnd !== null && initialEnd >= initialStart) {
      durationDays = Math.round((initialEnd - initialStart) / millisecondsPerDay);
    }
    var endDateManuallyEdited = false;

    function markEndDateManuallyEdited() {
      endDateManuallyEdited = true;
    }

    function syncEndDate() {
      if (endDateManuallyEdited) return;
      var start = parseDateOnly(startInput.value);
      endInput.value = start === null ? "" : formatDateOnly(start + durationDays * millisecondsPerDay);
    }

    endInput.addEventListener("input", markEndDateManuallyEdited);
    startInput.addEventListener("input", syncEndDate);
    startInput.addEventListener("change", syncEndDate);
    if (initialStart !== null && initialEnd === null) syncEndDate();
  }

  function initializeCopyFormDirtyGuard() {
    var eventForm = document.getElementById("event_form");
    var copyForm = document.getElementById("event-copy-form");
    if (!eventForm || !copyForm) return;

    var dirty = false;
    function markDirty() {
      dirty = true;
    }

    eventForm.addEventListener("input", markDirty, true);
    eventForm.addEventListener("change", markDirty, true);
    copyForm.addEventListener("submit", function (event) {
      if (
        dirty &&
        !window.confirm(
          "Loading Event data will discard your unsaved Event, Ticket, and Question changes. Continue?",
        )
      ) {
        event.preventDefault();
      }
    });
  }

  function initializeEventAdmin() {
    initializePhoneOptionDependency();
    initializeDateRangeDependency();
    initializeCopyFormDirtyGuard();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeEventAdmin);
  } else {
    initializeEventAdmin();
  }
})();
