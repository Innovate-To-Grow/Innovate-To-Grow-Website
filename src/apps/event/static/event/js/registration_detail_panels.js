(function () {
  "use strict";

  function init() {
    var path = window.location.pathname;
    if (path.indexOf("/eventregistration/add") === -1) return;

    var BASE = path.replace(/add\/?$/, "");

    function buildPanel(id) {
      var panel = document.createElement("div");
      panel.id = id;
      panel.style.cssText =
        "margin:6px 12px 2px;padding:10px 14px;border-radius:8px;" +
        "background:var(--color-base-50,#f8fafc);border:1px solid var(--color-base-200,#e2e8f0);" +
        "font-size:0.84rem;line-height:1.5;color:var(--color-base-700,#334155);display:none;";
      return panel;
    }

    function escHtml(str) {
      var d = document.createElement("div");
      d.textContent = str;
      return d.innerHTML;
    }

    function renderRows(pairs) {
      return pairs
        .filter(function (p) { return p[1]; })
        .map(function (p) {
          return '<span style="color:var(--color-base-500,#64748b)">' + p[0] + ":</span> " + escHtml(p[1]);
        })
        .join("<br>");
    }

    function findFieldRow(name) {
      var line = document.querySelector(".field-" + name);
      if (!line) return null;
      return line.closest(".field-row") || line;
    }

    function fetchJson(url, callback) {
      fetch(url, { credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(callback)
        .catch(function () {});
    }

    /* ---------- Member info panel ---------- */

    var memberRow = findFieldRow("member");
    var memberPanel = buildPanel("member-info-panel");
    if (memberRow) memberRow.parentNode.insertBefore(memberPanel, memberRow.nextSibling);

    function showMemberInfo(id) {
      if (!id) { memberPanel.style.display = "none"; return; }
      fetchJson(BASE + "member-info/" + id + "/", function (d) {
        var html = renderRows([
          ["Name", d.name],
          ["Email", (d.emails || []).join(", ")],
          ["Phone", (d.phones || []).join(", ")],
          ["Organization", d.organization],
          ["Title", d.title],
        ]);
        if (html) { memberPanel.innerHTML = html; memberPanel.style.display = "block"; }
        else { memberPanel.style.display = "none"; }
      });
    }

    /* ---------- Event info panel ---------- */

    var eventRow = findFieldRow("event");
    var eventPanel = buildPanel("event-info-panel");
    if (eventRow) eventRow.parentNode.insertBefore(eventPanel, eventRow.nextSibling);

    function showEventInfo(id) {
      if (!id) { eventPanel.style.display = "none"; return; }
      fetchJson(BASE + "event-info/" + id + "/", function (d) {
        var lines = [];
        var L = function (label, val) {
          if (!val) return;
          lines.push('<span style="color:var(--color-base-500,#64748b)">' + label + ":</span> " + escHtml(val));
        };
        var Lraw = function (label, html) {
          if (!html) return;
          lines.push('<span style="color:var(--color-base-500,#64748b)">' + label + ":</span> " + html);
        };

        L("Date", d.date);
        L("Location", d.location);
        if (d.description) L("Description", d.description);
        L("Status", d.is_live ? "Live" : "Not live");

        var flags = [];
        if (d.allow_secondary_email) flags.push("Secondary email");
        if (d.collect_phone) flags.push("Collect phone");
        if (d.verify_phone) flags.push("Verify phone");
        if (flags.length) L("Options", flags.join(", "));

        L("Total registrations", String(d.total_registrations));

        if (d.tickets && d.tickets.length) {
          var tParts = d.tickets.map(function (t) {
            return escHtml(t.name) + "&nbsp;(" + t.registrations + ")";
          });
          Lraw("Tickets", tParts.join(", "));
        }

        if (d.questions && d.questions.length) {
          var qParts = d.questions.map(function (q) {
            return escHtml(q.text) + (q.required ? " *" : "");
          });
          Lraw("Questions", qParts.join("; "));
        }

        var html = lines.join("<br>");
        if (html) { eventPanel.innerHTML = html; eventPanel.style.display = "block"; }
        else { eventPanel.style.display = "none"; }
      });
    }

    /* ---------- Watch select changes ---------- */

    function watchSelect(name, callback) {
      var select = document.querySelector('select[name="' + name + '"]');
      if (!select) return;

      // Native DOM change (plain <select>)
      select.addEventListener("change", function () { callback(select.value); });

      // jQuery change — covers Select2 autocomplete widgets.
      // django.jQuery is available after jquery.init.js runs.
      var $ = window.django && window.django.jQuery;
      if ($) {
        $(select).on("change", function () { callback(select.value); });
      }

      if (select.value) callback(select.value);
    }

    watchSelect("member", showMemberInfo);
    watchSelect("event", showEventInfo);
  }

  // Wait for full page load so Select2 / Unfold widgets are bound.
  if (document.readyState === "complete") {
    init();
  } else {
    window.addEventListener("load", init);
  }
})();
