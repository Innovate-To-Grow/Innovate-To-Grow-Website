(function () {
  "use strict";

  function appendAriaDescription(input, descriptionId) {
    var describedBy = (input.getAttribute("aria-describedby") || "")
      .split(/\s+/)
      .filter(Boolean);
    if (describedBy.indexOf(descriptionId) === -1) describedBy.push(descriptionId);
    input.setAttribute("aria-describedby", describedBy.join(" "));
  }

  function initializeContactOptionDependency(collectField, dependentFields, hintId, label) {
    var collectInput = document.getElementById("id_" + collectField);
    var dependentInputs = dependentFields.map(function (field) {
      return document.getElementById("id_" + field);
    });
    if (!collectInput || dependentInputs.some(function (input) { return !input; })) return;

    var dependencyHint = document.getElementById(hintId);
    dependentInputs.forEach(function (input) { appendAriaDescription(input, hintId); });

    function syncDependentState() {
      var disabled = !collectInput.checked;
      dependentInputs.forEach(function (input) {
        if (disabled) input.checked = false;
        input.disabled = disabled;
        input.setAttribute("aria-disabled", disabled ? "true" : "false");
        var container = input.closest(".field-" + input.name) || input.closest(".field-line") || input.parentElement;
        if (container) container.classList.toggle("event-admin-dependent-disabled", disabled);
      });
      if (dependencyHint) {
        dependencyHint.textContent = disabled
          ? "Enable Collect for " + label + " to make Verify if provided and Required available."
          : "Verify if provided and Required are available because Collect for " + label + " is enabled.";
      }
    }

    collectInput.addEventListener("change", syncDependentState);
    syncDependentState();
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
    initializeContactOptionDependency(
      "collect_phone", ["verify_phone", "require_phone"], "event-phone-dependency-hint", "Phone Number",
    );
    initializeContactOptionDependency(
      "allow_secondary_email", ["verify_secondary_email", "require_secondary_email"],
      "event-secondary-email-dependency-hint", "Secondary Email",
    );
    initializeDateRangeDependency();
    initializeCopyFormDirtyGuard();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeEventAdmin);
  } else {
    initializeEventAdmin();
  }
})();
