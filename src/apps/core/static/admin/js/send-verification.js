(function () {
  "use strict";

  var configuration = document.currentScript.dataset;
  var CHALLENGE_URL = configuration.challengeUrl;
  var SCRIPT_SRC = configuration.altchaUrl;
  var loaded = null;
  var statusRegion = null;
  var pendingStorageKey = "i2g_admin_verified_send:" + configuration.sessionKey;
  var pendingRequestId = configuration.unresolvedRequestId || null;
  var checkingStatus = null;
  try { pendingRequestId = pendingRequestId || sessionStorage.getItem(pendingStorageKey); } catch (_error) { /* Memory fallback. */ }

  function rememberRequest(requestId) {
    pendingRequestId = requestId;
    try {
      if (requestId) sessionStorage.setItem(pendingStorageKey, requestId);
      else sessionStorage.removeItem(pendingStorageKey);
    } catch (_error) { /* Keep the in-memory reference when storage is unavailable. */ }
  }

  function checkPreviousRequest() {
    if (!pendingRequestId) return Promise.resolve();
    if (checkingStatus) return checkingStatus;
    setStatus("Checking the previous request…");
    var controller = new AbortController();
    var timeout = window.setTimeout(function () { controller.abort(); }, 10000);
    checkingStatus = Promise.resolve().then(function () {
      var url = configuration.statusUrl.replace("00000000-0000-0000-0000-000000000000", pendingRequestId);
      return fetch(url, {credentials: "same-origin", signal: controller.signal, headers: {Accept: "application/json"}});
    }).then(function (response) {
      if (!response.ok) throw new Error("Unable to check the previous request.");
      return response.json();
    }).then(function (record) {
      if (record.status === "provider_accepted" || record.status === "definitely_failed") {
        rememberRequest(null);
        setStatus(record.status === "provider_accepted" ? "Your previous code request was accepted. Check your messages." : "The previous request failed. You can request another code.");
        return;
      }
      throw new Error("The send request is unresolved.");
    }).catch(function () {
      setStatus("The previous send request is still unresolved. Check your messages, then reload this page to check its status.");
    }).finally(function () {
      window.clearTimeout(timeout);
      checkingStatus = null;
    });
    return checkingStatus;
  }

  function ensureStatus() {
    if (statusRegion) return statusRegion;
    statusRegion = document.createElement("div");
    statusRegion.className = "send-verification-status";
    statusRegion.setAttribute("role", "status");
    statusRegion.setAttribute("aria-live", "polite");
    var box = document.querySelector(".login-box");
    if (box) box.appendChild(statusRegion);
    else document.body.appendChild(statusRegion);
    return statusRegion;
  }

  function setStatus(message) {
    ensureStatus().textContent = message || "";
  }

  function loadAltcha() {
    if (window.customElements && window.customElements.get("altcha-widget")) {
      return Promise.resolve();
    }
    if (loaded) return loaded;
    loaded = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      var settled = false;
      script.src = SCRIPT_SRC;
      script.async = true;
      if (window.I2G_CSP_NONCE) script.nonce = window.I2G_CSP_NONCE;
      var timeout = window.setTimeout(failed, 15000);
      function failed() {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        loaded = null;
        script.remove();
        reject(new Error("Unable to load verification assets. Please reload and try again."));
      }
      script.onload = function () {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        resolve();
      };
      script.onerror = failed;
      document.head.appendChild(script);
    });
    return loaded;
  }

  function randomRequestId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    if (!window.crypto || !window.crypto.getRandomValues) throw new Error("Secure verification is unavailable in this browser.");
    var bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    var hex = Array.from(bytes, function (value) { return value.toString(16).padStart(2, "0"); }).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
  }

  function operationFor(form) {
    var action = (form.querySelector("input[name=action]") || {}).value || "";
    if (action === "remembered_code") return "admin.login.remembered_code";
    if (action === "resend") return "admin.login.resend";
    return "admin.login.request_code";
  }

  function destinationFor(form) {
    var email = form.querySelector("input[name=email]");
    if (email && email.value) return email.value;
    return "";
  }

  function shouldProtect(form) {
    if (form.querySelector("input[name=mode][value=password]")) return false;
    if (form.querySelector("input[name=code]")) return false;
    var action = (form.querySelector("input[name=action]") || {}).value || "";
    if (action === "remembered_code" || action === "resend") return true;
    return Boolean(form.querySelector("input[name=email]") && form.querySelector("button[type=submit], input[type=submit]"));
  }

  function addHidden(form, name, value) {
    var existing = form.querySelector("input[name='" + name + "']");
    if (!existing) {
      existing = document.createElement("input");
      existing.type = "hidden";
      existing.name = name;
      form.appendChild(existing);
    }
    existing.value = value;
  }

  function solveChallenge(challenge) {
    return loadAltcha().then(function () {
      return new Promise(function (resolve, reject) {
        var host = document.createElement("div");
        host.style.position = "absolute";
        host.style.left = "-9999px";
        var widget = document.createElement("altcha-widget");
        widget.setAttribute("auto", "off");
        var settled = false;
        var started = false;
        var timeout = window.setTimeout(function () { finish(new Error("Verification timed out.")); }, 90000);
        function finish(error, payload) {
          if (settled) return;
          settled = true;
          window.clearTimeout(timeout);
          widget.removeEventListener("load", start);
          widget.removeEventListener("verified", verified);
          widget.removeEventListener("statechange", stateChanged);
          host.remove();
          if (error) reject(error);
          else if (typeof payload === "string" && payload) resolve(payload);
          else reject(new Error("Verification did not produce a payload."));
        }
        function verified(event) { finish(null, event.detail && event.detail.payload); }
        function stateChanged(event) {
          if (event.detail && event.detail.state === "error") finish(new Error("Verification failed. Please try again."));
        }
        function start() {
          if (started || settled || typeof widget.configure !== "function" || typeof widget.verify !== "function") return;
          started = true;
          Promise.resolve()
            .then(function () { return widget.configure({challenge: challenge, auto: "off", hideFooter: true, hideLogo: true}); })
            .then(function () { return settled ? null : widget.verify(); })
            .then(function (result) {
              if (!settled) finish(result ? null : new Error("Verification failed. Please try again."), result && result.payload);
            })
            .catch(function (error) { finish(error); });
        }
        widget.addEventListener("load", start);
        widget.addEventListener("verified", verified);
        widget.addEventListener("statechange", stateChanged);
        host.appendChild(widget);
        document.body.appendChild(host);
        start();
      });
    });
  }

  function intercept(event) {
    var form = event.target;
    if (!form || !shouldProtect(form) || form.getAttribute("data-send-verified") === "1") return;
    event.preventDefault();
    if (pendingRequestId) {
      void checkPreviousRequest();
      return;
    }
    if (form.getAttribute("data-send-pending") === "1") return;
    form.setAttribute("data-send-pending", "1");
    var submitter = event.submitter;
    if (submitter) submitter.disabled = true;
    setStatus("Verifying…");
    var operation = operationFor(form);
    var destination = destinationFor(form);
    var body = { operation: operation };
    if (destination) body.destination = destination;
    var csrfToken = (form.querySelector("input[name=csrfmiddlewaretoken]") || {}).value || "";
    var controller = new AbortController();
    var challengeTimeout = window.setTimeout(function () { controller.abort(); }, 15000);
    fetch(CHALLENGE_URL, {
      signal: controller.signal,
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(body),
    })
      .then(function (response) {
        window.clearTimeout(challengeTimeout);
        if (!response.ok) throw new Error("Unable to start verification.");
        return response.json();
      })
      .then(function (data) {
        return solveChallenge(data.challenge).then(function (payload) {
          addHidden(form, "verification_challenge_id", data.challenge_id);
          addHidden(form, "verification_payload", payload);
          var requestId = randomRequestId();
          addHidden(form, "send_request_id", requestId);
          rememberRequest(requestId);
          form.setAttribute("data-send-verified", "1");
          setStatus("");
          HTMLFormElement.prototype.submit.call(form);
        });
      })
      .catch(function (error) {
        window.clearTimeout(challengeTimeout);
        form.removeAttribute("data-send-pending");
        setStatus(error.message || "Verification failed. Please try again.");
        if (submitter) submitter.disabled = false;
      });
  }

  document.addEventListener("submit", intercept, true);
  document.addEventListener("DOMContentLoaded", function () {
    if (pendingRequestId) {
      rememberRequest(pendingRequestId);
      void checkPreviousRequest();
    }
  }, {once: true});
})();
