// MedFlow works without this file; it only adds conveniences on top.

// Forms marked data-busy-label ignore a second submit while the first is being handled:
// a second bill analysis would spend AI quota again, and a second save would add the
// same expenses twice.
(function () {
  "use strict";
  if (!window.addEventListener || !Element.prototype.matches) {
    return;
  }

  function setBusy(form, busy) {
    var button = form.querySelector('button[type="submit"]');
    var status = form.querySelector("[data-busy-status]");
    if (busy) {
      form.setAttribute("aria-busy", "true");
    } else {
      form.removeAttribute("aria-busy");
    }
    if (button) {
      if (busy) {
        button.setAttribute("data-idle-label", button.textContent);
        button.textContent = form.getAttribute("data-busy-label");
      } else if (button.hasAttribute("data-idle-label")) {
        button.textContent = button.getAttribute("data-idle-label");
      }
      button.disabled = busy;
    }
    if (status) {
      status.textContent = busy ? form.getAttribute("data-busy-status-text") || "" : "";
    }
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches("form[data-busy-label]")) {
      return;
    }
    if (form.getAttribute("aria-busy") === "true") {
      event.preventDefault();
      return;
    }
    setBusy(form, true);
  });

  // The Back button can restore a page exactly as it was left, busy button and all.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) {
      return;
    }
    var forms = document.querySelectorAll("form[data-busy-label]");
    for (var i = 0; i < forms.length; i++) {
      setBusy(forms[i], false);
    }
  });
})();
