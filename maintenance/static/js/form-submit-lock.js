(function () {
  "use strict";

  var submittingClass = "is-submitting";
  var busyText = "Processing...";

  function isForm(element) {
    return element && element.tagName === "FORM";
  }

  function formMethod(form) {
    return (form.getAttribute("method") || "get").toLowerCase();
  }

  function isMutatingForm(form) {
    if (form.hasAttribute("data-no-submit-lock")) {
      return false;
    }
    return (
      formMethod(form) !== "get" ||
      form.hasAttribute("hx-post") ||
      form.hasAttribute("hx-put") ||
      form.hasAttribute("hx-patch") ||
      form.hasAttribute("hx-delete")
    );
  }

  function fallbackSubmitter(form) {
    var active = document.activeElement;
    if (!active || !form.contains(active)) {
      return null;
    }
    return active.matches('button, input[type="submit"], input[type="image"]') ? active : null;
  }

  function preserveSubmitterValue(form, submitter) {
    if (!submitter || !submitter.name || submitter.disabled) {
      return;
    }

    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = submitter.name;
    hidden.value = submitter.value || "";
    hidden.setAttribute("data-submit-lock-hidden", "true");
    form.appendChild(hidden);
  }

  function submitControls(scope) {
    return scope.querySelectorAll(
      'button, input[type="submit"], input[type="button"], input[type="image"]'
    );
  }

  function setButtonBusy(control) {
    if (!control || control.hasAttribute("data-submit-lock-busy")) {
      return;
    }

    control.setAttribute("data-submit-lock-busy", "true");

    if (control.tagName === "BUTTON") {
      control.setAttribute("data-submit-lock-original-html", control.innerHTML);
      control.innerHTML =
        '<span class="submit-spinner" aria-hidden="true"></span><span>' +
        busyText +
        "</span>";
    } else if (control.type === "submit" || control.type === "button") {
      control.setAttribute("data-submit-lock-original-value", control.value);
      control.value = busyText;
    }
  }

  function disableControl(control) {
    if (control.disabled) {
      return;
    }
    control.setAttribute("data-submit-lock-enabled", "true");
    control.disabled = true;
    control.setAttribute("aria-disabled", "true");
  }

  function lockForm(form, submitter) {
    form.dataset.submitting = "true";
    form.classList.add(submittingClass);
    form.setAttribute("aria-busy", "true");

    preserveSubmitterValue(form, submitter);
    setButtonBusy(submitter);

    submitControls(form).forEach(disableControl);
  }

  function restoreControl(control) {
    if (control.getAttribute("data-submit-lock-original-html") !== null) {
      control.innerHTML = control.getAttribute("data-submit-lock-original-html");
      control.removeAttribute("data-submit-lock-original-html");
    }
    if (control.getAttribute("data-submit-lock-original-value") !== null) {
      control.value = control.getAttribute("data-submit-lock-original-value");
      control.removeAttribute("data-submit-lock-original-value");
    }
    if (control.getAttribute("data-submit-lock-enabled") === "true") {
      control.disabled = false;
      control.removeAttribute("data-submit-lock-enabled");
      control.removeAttribute("aria-disabled");
    }
    control.removeAttribute("data-submit-lock-busy");
  }

  function unlockForm(form) {
    if (!isForm(form)) {
      return;
    }
    form.dataset.submitting = "";
    form.classList.remove(submittingClass);
    form.removeAttribute("aria-busy");
    form.removeAttribute("data-htmx-request-started");
    form.querySelectorAll("[data-submit-lock-hidden]").forEach(function (hidden) {
      hidden.remove();
    });
    submitControls(form).forEach(restoreControl);
  }

  function mutatingHtmxElement(element) {
    if (!element || element.hasAttribute("data-no-submit-lock")) {
      return null;
    }

    if (
      element.matches &&
      element.matches("[hx-post], [hx-put], [hx-patch], [hx-delete]")
    ) {
      return element;
    }

    if (element.closest) {
      return element.closest("[hx-post], [hx-put], [hx-patch], [hx-delete]");
    }

    return null;
  }

  function lockHtmxElement(element) {
    if (!element || element.hasAttribute("data-htmx-submitting")) {
      return false;
    }

    element.setAttribute("data-htmx-submitting", "true");
    element.setAttribute("aria-busy", "true");

    if (element.matches('button, input[type="submit"], input[type="button"]')) {
      setButtonBusy(element);
      disableControl(element);
    } else if (isForm(element)) {
      lockForm(element, fallbackSubmitter(element));
    }

    return true;
  }

  function unlockHtmxElement(element) {
    if (!element) {
      return;
    }

    element.removeAttribute("data-htmx-submitting");
    element.removeAttribute("aria-busy");

    if (element.matches && element.matches('button, input[type="submit"], input[type="button"]')) {
      restoreControl(element);
    } else if (isForm(element)) {
      unlockForm(element);
    }
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;

    if (!isForm(form) || !isMutatingForm(form) || event.defaultPrevented) {
      return;
    }

    if (form.dataset.submitting === "true") {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    lockForm(form, event.submitter || fallbackSubmitter(form));
  });

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var element = mutatingHtmxElement(event.detail.elt);

    if (!element) {
      return;
    }

    if (isForm(element) && element.dataset.submitting === "true") {
      if (element.getAttribute("data-htmx-request-started") === "true") {
        event.preventDefault();
        return;
      }
      element.setAttribute("data-htmx-request-started", "true");
      return;
    }

    if (!lockHtmxElement(element)) {
      event.preventDefault();
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    unlockHtmxElement(mutatingHtmxElement(event.detail.elt));
  });
})();
