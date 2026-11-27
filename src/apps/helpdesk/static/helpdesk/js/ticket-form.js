/* The ticket page's ticket form (Helpdesk → Queue → a ticket). Progressive: without this script the form still works.
 *
 * - A page the server rendered for a GET shows the saved values: a value the browser put back into a control on Back
 *   (it differs from the page's hidden initial value) is reset, so it can never be saved as this person's edit. Not
 *   after a refused save, where the controls rightly hold what this person typed.
 * - The priority follows impact and urgency at once (saved on Save).
 *
 * Tickets have no owner (I2G-HELPDESK-01): there is no assignee or assignment group on the form.
 */
(function () {
  "use strict";

  function data(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }

  function showSaved(form) {
    form.querySelectorAll("input[type='hidden'][name^='initial-']").forEach(function (initial) {
      var field = form.querySelector("[name='" + initial.name.slice("initial-".length) + "']");
      var saved = initial.value.replace(/\r\n/g, "\n");
      if (field && field.tagName !== "INPUT" && field.value.replace(/\r\n/g, "\n") !== saved) {
        field.value = saved;
      }
    });
  }

  function readonlyValue(labelText) {
    // A read-only field's value box, found by its label (Unfold's rows carry no field-name class).
    var labels = document.querySelectorAll("#ticket_form label");
    for (var index = 0; index < labels.length; index += 1) {
      if (labels[index].textContent.trim() === labelText) {
        var line = labels[index].closest(".field-line") || labels[index].parentElement.parentElement;
        return line ? line.querySelector(".readonly") : null;
      }
    }
    return null;
  }

  function priorityPreview(helpers) {
    var impact = document.getElementById("id_impact");
    var urgency = document.getElementById("id_urgency");
    var priority = readonlyValue("Priority");
    if (!impact || !urgency || !priority) {
      return;
    }
    var saved = priority.textContent.trim();
    var preview = function () {
      var label = helpers.priorities[impact.value + "-" + urgency.value];
      priority.textContent = label && label !== saved ? label + " (when saved)" : saved;
    };
    impact.addEventListener("change", preview);
    urgency.addEventListener("change", preview);
  }

  function start() {
    var form = document.getElementById("ticket_form");
    var helpers = data("helpdesk-form-data");
    if (!form || !helpers) {
      return;
    }
    if (helpers.fresh) {
      showSaved(form);
    }
    priorityPreview(helpers);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
