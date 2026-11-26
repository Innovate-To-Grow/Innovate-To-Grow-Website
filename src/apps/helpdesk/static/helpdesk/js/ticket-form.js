/* The ticket page's ticket form (Helpdesk → Queue → a ticket). Progressive: without this script the form still works.
 *
 * - A page the server rendered for a GET shows the saved values: a value the browser put back into a control on Back
 *   (it differs from the page's hidden initial value) is reset, so it can never be saved as this person's edit. Not
 *   after a refused save, where the controls rightly hold what this person typed.
 * - The priority follows impact and urgency at once (saved on Save).
 * - Assigned to offers the assignment group's members (all helpdesk staff for a group without members); an assignee
 *   who is no member is kept, marked, until the group is changed. "Assign to me" picks the signed-in member.
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

  function assignedTo(helpers) {
    var group = document.getElementById("id_assignment_group");
    var assignee = document.getElementById("id_assignee");
    if (!assignee) {
      return;
    }
    var narrow = function (keepCurrent) {
      var members = (group && helpers.groups[group.value]) || [];
      Array.prototype.forEach.call(assignee.options, function (option) {
        var outside = option.value !== "" && members.length > 0 && members.indexOf(option.value) === -1;
        var kept = keepCurrent && outside && option.selected;
        option.hidden = outside && !kept;
        option.disabled = outside && !kept;
        if (kept && option.textContent.indexOf("(not a member") === -1) {
          option.textContent += " (not a member of the group)";
        }
      });
      var selected = assignee.options[assignee.selectedIndex];
      if (selected && selected.disabled) {
        assignee.value = "";
      }
    };
    if (group) {
      group.addEventListener("change", function () {
        narrow(false);
      });
      narrow(true);
    }
    var mine = Array.prototype.find.call(assignee.options, function (option) {
      return option.value === helpers.me;
    });
    if (!mine) {
      return;
    }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "i2g-helpdesk-button is-secondary i2g-helpdesk-assign-me";
    button.textContent = "Assign to me";
    button.addEventListener("click", function () {
      if (mine.disabled) {
        window.alert("You are not a member of the chosen assignment group.");
        return;
      }
      assignee.value = helpers.me;
      assignee.dispatchEvent(new Event("change", { bubbles: true }));
    });
    // After Unfold's wrapper (it holds the select's chevron), not inside it.
    (assignee.closest(".relative") || assignee).insertAdjacentElement("afterend", button);
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
    assignedTo(helpers);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
