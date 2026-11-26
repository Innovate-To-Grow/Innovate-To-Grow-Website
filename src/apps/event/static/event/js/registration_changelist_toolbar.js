(function () {
  "use strict";

  // Registrations changelist toolbar (search + semester + event, see _changelist_toolbar.html).
  function init() {
    var form = document.querySelector(".i2g-reg-toolbar__form");
    if (!form) return;

    // Leave "All semesters" / "All events" / an empty search out of the URL: Django answers an empty
    // event__id__exact with its invalid-lookup page (?e=1), since "" is not a UUID.
    form.addEventListener("formdata", function (event) {
      form.querySelectorAll("select[data-i2g-autosubmit], #searchbar").forEach(function (field) {
        if (field.name && !field.value) event.formData.delete(field.name);
      });
    });

    // Picking a semester or an event applies it straight away.
    form.querySelectorAll("select[data-i2g-autosubmit]").forEach(function (select) {
      select.addEventListener("change", function () {
        form.requestSubmit();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
