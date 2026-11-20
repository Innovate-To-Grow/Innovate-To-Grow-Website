/* The ticket page (Helpdesk → Queue → a ticket). Progressive: without this script every form still works.
 *
 * - Reply form: a response template is inserted where the cursor is (no page reload, so nothing typed is lost);
 *   Enter in Cc does not send the reply; Send works once (no duplicate reply on a double click).
 * - The page has three forms (the ticket's fields, the reply, the internal note). Submitting one while another has
 *   unsaved input asks first, because the page reloads and that input would be lost.
 * - Ticket form: the priority follows impact and urgency at once (saved on Save), Assigned to offers the assignment
 *   group's members (all helpdesk staff for a group without members), and "Assign to me" picks the signed-in member.
 */
(function () {
  "use strict";

  function data(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }

  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback);
    } else {
      callback();
    }
  }

  // --- the three forms: warn before one throws away what was typed in another --------------------------------------

  function watchForms() {
    var forms = [
      { form: document.getElementById("ticket_form"), name: "the ticket's fields", once: false },
      { form: document.querySelector("#helpdesk-reply form[method='post']"), name: "the reply", once: true },
      { form: document.getElementById("helpdesk-note"), name: "the internal note", once: true },
    ].filter(function (item) {
      return item.form;
    });
    forms.forEach(function (item) {
      item.dirty = false;
      item.form.addEventListener("input", function () {
        item.dirty = true;
      });
      item.form.addEventListener("change", function () {
        item.dirty = true;
      });
      item.form.addEventListener("submit", function (event) {
        var others = forms.filter(function (other) {
          return other !== item && other.dirty;
        });
        if (others.length) {
          var names = others.map(function (other) {
            return other.name;
          });
          var question = "You have unsaved changes in " + names.join(" and ") + ". They are lost if you continue. Continue?";
          if (!window.confirm(question)) {
            event.preventDefault();
            return;
          }
        }
        item.dirty = false;
        if (item.once) {
          // The reply and the note are sent once (the ticket form's buttons carry Save / Save and continue).
          window.setTimeout(function () {
            item.form.querySelectorAll("button[type='submit']").forEach(function (button) {
              button.disabled = true;
            });
          }, 0);
        }
      });
    });
  }

  // --- the reply form --------------------------------------------------------------------------------------------------

  function insertAtCursor(textarea, text) {
    var start = textarea.selectionStart || 0;
    var end = textarea.selectionEnd || 0;
    var before = textarea.value.slice(0, start);
    var after = textarea.value.slice(end);
    var gap = before && !/\n\n$/.test(before) ? (/\n$/.test(before) ? "\n" : "\n\n") : "";
    textarea.value = before + gap + text + after;
    var cursor = (before + gap + text).length;
    textarea.setSelectionRange(cursor, cursor);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.focus();
  }

  function replyForm() {
    var picker = document.querySelector("#helpdesk-reply .i2g-helpdesk-template-picker");
    var body = document.getElementById("helpdesk-reply-body");
    var templates = data("helpdesk-reply-templates") || [];
    if (picker && body) {
      picker.addEventListener("submit", function (event) {
        event.preventDefault();
        var chosen = picker.querySelector("select").value;
        var template = templates.find(function (item) {
          return item.id === chosen;
        });
        if (template) {
          insertAtCursor(body, template.body);
        }
      });
    }
    var cc = document.getElementById("helpdesk-reply-cc");
    if (cc) {
      cc.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault(); // Enter accepts the address; only "Send reply" sends.
          if (cc.value && !/,\s*$/.test(cc.value)) {
            cc.value = cc.value + ", ";
          }
        }
      });
    }
  }

  // --- the ticket form -------------------------------------------------------------------------------------------------

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

  function ticketForm(helpers) {
    var impact = document.getElementById("id_impact");
    var urgency = document.getElementById("id_urgency");
    var priority = document.querySelector(".field-priority .readonly") || readonlyValue("Priority");
    if (impact && urgency && priority) {
      var saved = priority.textContent.trim();
      var preview = function () {
        var label = helpers.priorities[impact.value + "-" + urgency.value];
        priority.textContent = label && label !== saved ? label + " (when saved)" : saved;
      };
      impact.addEventListener("change", preview);
      urgency.addEventListener("change", preview);
    }
    var group = document.getElementById("id_assignment_group");
    var assignee = document.getElementById("id_assignee");
    if (!assignee) {
      return;
    }
    var narrow = function () {
      var members = (group && helpers.groups[group.value]) || [];
      Array.prototype.forEach.call(assignee.options, function (option) {
        var outside = option.value !== "" && members.length > 0 && members.indexOf(option.value) === -1;
        option.hidden = outside;
        option.disabled = outside;
      });
      var selected = assignee.options[assignee.selectedIndex];
      if (selected && selected.disabled) {
        assignee.value = "";
      }
    };
    if (group) {
      group.addEventListener("change", narrow);
      narrow();
    }
    var mine = Array.prototype.find.call(assignee.options, function (option) {
      return option.value === helpers.me;
    });
    if (mine) {
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
      assignee.insertAdjacentElement("afterend", button);
    }
  }

  onReady(function () {
    watchForms();
    replyForm();
    var helpers = data("helpdesk-form-data");
    if (helpers) {
      ticketForm(helpers);
    }
  });
})();
