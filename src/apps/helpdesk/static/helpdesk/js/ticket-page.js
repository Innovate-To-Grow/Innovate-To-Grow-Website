/* The ticket page (Helpdesk → Queue → a ticket): its three forms. Progressive: without this script they still work.
 *
 * - The page has three forms (the ticket's fields, the reply, the internal note). Submitting one while another has
 *   unsaved input asks first (the page reloads and that input would be lost), and so does leaving the page. A reply
 *   the server put back after a refusal counts as unsaved input.
 * - Reply form: a response template is inserted where the cursor is (no page reload, so nothing typed is lost);
 *   Enter in Cc does not send the reply; Send works once (no duplicate reply on a double click); a counter shows the
 *   characters left (the browser cuts a longer paste without saying so).
 * The ticket form's own helpers are in ticket-form.js.
 */
(function () {
  "use strict";

  function data(id) {
    var node = document.getElementById(id);
    return node ? JSON.parse(node.textContent) : null;
  }

  function filled(form, selector) {
    return Array.prototype.some.call(form.querySelectorAll(selector), function (field) {
      return field.value.trim() !== "";
    });
  }

  // --- the three forms: warn before one throws away what was typed in another --------------------------------------

  function watchForms() {
    var reply = document.querySelector("#helpdesk-reply form[method='post']");
    var note = document.getElementById("helpdesk-note");
    var forms = [
      { form: document.getElementById("ticket_form"), name: "the ticket's fields", once: false, dirty: false },
      { form: reply, name: "the reply", once: true, dirty: Boolean(reply) && filled(reply, "textarea, #helpdesk-reply-cc") },
      { form: note, name: "the internal note", once: true, dirty: Boolean(note) && filled(note, "textarea") },
    ].filter(function (item) {
      return item.form;
    });
    var submitting = false;
    forms.forEach(function (item) {
      var mark = function () {
        item.dirty = true;
      };
      item.form.addEventListener("input", mark);
      item.form.addEventListener("change", mark);
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
        submitting = true;
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
    window.addEventListener("beforeunload", function (event) {
      var unsaved = forms.some(function (item) {
        return item.dirty;
      });
      if (unsaved && !submitting) {
        event.preventDefault();
        event.returnValue = "";
      }
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

  function counter(body) {
    var max = body.maxLength > 0 ? body.maxLength : 0;
    if (!max) {
      return;
    }
    var line = document.createElement("p");
    line.className = "i2g-helpdesk-muted";
    line.setAttribute("aria-live", "polite");
    var update = function () {
      var left = max - body.value.length;
      line.textContent =
        left > 0 ? left.toLocaleString() + " characters left" : "The reply is at its limit: anything longer was cut off.";
    };
    body.addEventListener("input", update);
    body.insertAdjacentElement("afterend", line);
    update();
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
    if (body) {
      counter(body);
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

  function start() {
    watchForms();
    replyForm();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
