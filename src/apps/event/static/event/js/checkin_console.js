/**
 * Check-in console orchestrator.
 * Wires together shared utilities, ticket-input logic, and camera scanning.
 * Depends on: checkin_shared.js, checkin_ticket_input.js, checkin_camera.js.
 */
(function () {
    "use strict";

    var ns = window.__checkinConsole;
    if (!ns) return;

    var utils = ns.utils;
    var ticketInput = ns.ticketInput;
    var cam = ns.camera;

    var node = utils.node;
    var clear = utils.clear;
    var formatTime = utils.formatTime;
    var formatClock = utils.formatClock;

    var configElement = document.getElementById("checkin-console-config");
    if (!configElement) return;

    var config = JSON.parse(configElement.textContent || "{}");
    var statusPollIntervalMs = Number(config.statusPollIntervalMs) || 2000;

    var state = {
        camera: null,
        cameraRunning: false,
        cameraCooling: false,
        hasLoadedStatus: false,
        statusLoading: false,
        statusPromise: null,
        statusRefreshQueued: false,
        statusTimer: null,
        roster: [],
        recent: [],
        filter: "",
        suggestionActiveIndex: -1,
    };

    var root = document.querySelector("[data-checkin-console]");
    if (!root) return;

    var elements = {
        form: root.querySelector("[data-scan-form]"),
        input: root.querySelector("[data-scan-input]"),
        scanButton: root.querySelector("[data-scan-button]"),
        result: root.querySelector("[data-scan-result]"),
        total: root.querySelector("[data-stat-total]"),
        scanned: root.querySelector("[data-stat-scanned]"),
        remaining: root.querySelector("[data-stat-remaining]"),
        syncStatus: root.querySelector("[data-sync-status]"),
        syncLabel: root.querySelector("[data-sync-label]"),
        rosterSearch: root.querySelector("[data-roster-search]"),
        rosterList: root.querySelector("[data-roster-list]"),
        recentList: root.querySelector("[data-recent-list]"),
        refreshButton: root.querySelector("[data-refresh-button]"),
        cameraReader: root.querySelector("[data-camera-reader]"),
        cameraStart: root.querySelector("[data-camera-start]"),
        cameraStop: root.querySelector("[data-camera-stop]"),
        cameraStatus: root.querySelector("[data-camera-status]"),
        cameraMessage: root.querySelector("[data-camera-message]"),
        codeField: root.querySelector(".i2g-checkin-code-field"),
    };

    /**
     * Show an inline attendee preview card in the result area.
     * Used by both manual input matching and camera scanning.
     */
    function showAttendeePreview(attendee, code) {
        elements.result.className = "i2g-checkin-result is-visible is-preview";
        clear(elements.result);

        var card = document.createElement("div");
        card.className = "i2g-checkin-preview-card";

        var info = document.createElement("div");
        info.className = "i2g-checkin-preview-info";
        info.appendChild(node("strong", "", attendee.name || "Unnamed attendee"));
        var meta = [attendee.organization, attendee.ticket_type].filter(Boolean).join(" \u00b7 ");
        if (meta) info.appendChild(node("span", "", meta));
        if (attendee.email) info.appendChild(node("span", "", attendee.email));
        var codeEl = document.createElement("code");
        codeEl.textContent = attendee.ticket_code || code;
        info.appendChild(codeEl);

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "i2g-checkin-preview-action";
        var icon = document.createElement("span");
        icon.className = "material-symbols-outlined";
        icon.textContent = "login";
        btn.appendChild(icon);
        btn.appendChild(document.createTextNode("Check In"));
        btn.addEventListener("click", function () {
            submitScan(attendee.ticket_code || code, "manual");
        });

        card.appendChild(info);
        card.appendChild(btn);
        elements.result.appendChild(card);
    }

    function showInputMatchPreview() {
        var value = elements.input.value.trim();
        if (!value || value.length < 2) {
            hidePreview();
            return;
        }
        var matches = ticketInput.getSuggestionMatches(value, state.roster);
        if (!matches.length) {
            hidePreview();
            return;
        }
        showAttendeePreview(matches[0], value);
    }

    var cameraCtx = {
        state: state,
        elements: elements,
        submitScan: submitScan,
        showAttendeePreview: showAttendeePreview,
    };

    function requestJson(url, options) {
        return utils.requestJson(url, options, config.csrfToken);
    }

    function setResult(kind, title, lines) {
        elements.result.className = "i2g-checkin-result is-visible is-" + kind;
        clear(elements.result);
        elements.result.appendChild(node("strong", "", title));
        (lines || []).filter(Boolean).forEach(function (line) {
            elements.result.appendChild(node("span", "", line));
        });
    }

    function hidePreview() {
        if (elements.result.classList.contains("is-preview")) {
            elements.result.className = "i2g-checkin-result";
            clear(elements.result);
        }
    }

    function attendeeLine(attendee) {
        if (!attendee) return "";
        return [attendee.email, attendee.ticket_type].filter(Boolean).join(" - ");
    }

    function setSyncStatus(kind, label) {
        elements.syncStatus.className = "i2g-checkin-sync is-" + kind;
        elements.syncLabel.textContent = label;
    }

    /* ---------- Scan submission ---------- */

    async function submitScan(value, source) {
        var barcode = String(value || "").trim();
        if (!barcode) return;

        elements.scanButton.disabled = true;
        try {
            var data = await requestJson(config.scanUrl, {
                method: "POST",
                body: JSON.stringify({ barcode: barcode }),
            });

            if (data.status === "success") {
                setResult("success", "Checked in", [
                    data.attendee && data.attendee.name,
                    attendeeLine(data.attendee),
                    data.attendee ? "Code: " + data.attendee.ticket_code : "",
                ]);
                elements.input.value = "";
                ticketInput.hideSuggestions(elements.ticketSuggestions, elements.input, state);
                await loadStatus({ force: true });
            } else if (data.status === "duplicate") {
                var station = data.existing_check_in && data.existing_check_in.name;
                setResult("duplicate", "Already checked in", [
                    data.attendee && data.attendee.name,
                    station ? "Station: " + station : "",
                    data.scanned_at ? "Time: " + formatTime(data.scanned_at) : data.detail,
                ]);
                await loadStatus({ force: true });
            } else {
                setResult("error", data.status === "not_found" ? "Not found" : "Unable to check in", [
                    data.detail || "Unknown error",
                ]);
            }
        } catch (error) {
            setResult("error", "Network error", [error.message]);
        } finally {
            elements.scanButton.disabled = false;
            if (source !== "camera") elements.input.focus();
        }
    }

    /* ---------- Status polling and rendering ---------- */

    function updateStats(data) {
        elements.total.textContent = data.total ?? "-";
        elements.scanned.textContent = data.scanned ?? "-";
        var remaining = Array.isArray(data.not_checked_in) ? data.not_checked_in.length : "-";
        elements.remaining.textContent = remaining;
    }

    function renderRoster() {
        var term = state.filter.trim().toLowerCase();
        var rows = term
            ? state.roster.filter(function (attendee) {
                  return [attendee.name, attendee.email, attendee.ticket_type, attendee.ticket_code]
                      .filter(Boolean)
                      .join(" ")
                      .toLowerCase()
                      .includes(term);
              })
            : state.roster;

        clear(elements.rosterList);
        if (!rows.length) {
            elements.rosterList.appendChild(node("div", "i2g-checkin-empty", "No matching attendees."));
            return;
        }

        rows.forEach(function (attendee) {
            var row = node("div", "i2g-checkin-row");
            var text = document.createElement("div");
            text.append(
                node("strong", "", attendee.name || "Unnamed attendee"),
                node("span", "", attendeeLine(attendee)),
                node("code", "", attendee.ticket_code || "")
            );
            var button = node("button", "", "Check In");
            button.type = "button";
            button.dataset.ticketCode = attendee.ticket_code || "";
            row.append(text, button);
            elements.rosterList.appendChild(row);
        });
    }

    function renderRecent() {
        clear(elements.recentList);
        if (!state.recent.length) {
            elements.recentList.appendChild(node("div", "i2g-checkin-empty", "No scans yet."));
            return;
        }

        state.recent.forEach(function (record) {
            var row = node("div", "i2g-checkin-row");
            var text = document.createElement("div");
            text.append(
                node("strong", "", record.attendee && record.attendee.name ? record.attendee.name : "Unnamed attendee"),
                node("span", "", formatTime(record.scanned_at) + " - " + (record.attendee.ticket_type || "")),
                node("code", "", record.attendee.ticket_code || "")
            );
            var button = node("button", "", "Undo");
            button.type = "button";
            button.dataset.undoRecord = record.id || "";
            row.append(text, button);
            elements.recentList.appendChild(row);
        });
    }

    async function loadStatus(options) {
        var force = Boolean(options && options.force);
        if (document.hidden && !force) {
            setSyncStatus("paused", "Paused");
            return null;
        }
        if (state.statusLoading) {
            if (force) state.statusRefreshQueued = true;
            return state.statusPromise;
        }

        state.statusLoading = true;
        setSyncStatus("syncing", "Syncing...");
        state.statusPromise = (async function () {
            try {
                var data = await requestJson(config.statusUrl, { method: "GET" });
                if (data._ok === false) {
                    throw new Error(data.detail || "HTTP " + data._statusCode);
                }
                state.roster = Array.isArray(data.not_checked_in) ? data.not_checked_in : [];
                state.recent = Array.isArray(data.recent_scans) ? data.recent_scans : [];
                updateStats(data);
                renderRoster();
                renderRecent();
                state.hasLoadedStatus = true;
                if (document.hidden) {
                    setSyncStatus("paused", "Paused");
                } else {
                    setSyncStatus("live", "Live sync \u00b7 updated " + formatClock(new Date()));
                }
                return data;
            } catch (error) {
                setSyncStatus(
                    document.hidden ? "paused" : "issue",
                    document.hidden ? "Paused" : "Sync issue \u00b7 retrying"
                );
                if (!state.hasLoadedStatus) {
                    elements.rosterList.replaceChildren(
                        node("div", "i2g-checkin-empty", "Failed to load attendees: " + error.message)
                    );
                }
                return null;
            } finally {
                state.statusLoading = false;
                state.statusPromise = null;
                if (state.statusRefreshQueued) {
                    state.statusRefreshQueued = false;
                    loadStatus({ force: true });
                }
            }
        })();
        return state.statusPromise;
    }

    async function undoRecord(recordId) {
        if (!recordId) return;
        if (!window.confirm("Undo this check-in record?")) return;
        var url = config.undoUrlTemplate.replace("__record_id__", recordId);
        try {
            var data = await requestJson(url, { method: "POST", body: JSON.stringify({}) });
            if (data.status === "removed") {
                setResult("success", "Check-in undone", ["Record: " + recordId]);
                await loadStatus({ force: true });
            } else {
                setResult("error", "Unable to undo", [data.detail || "Unknown error"]);
            }
        } catch (error) {
            setResult("error", "Network error", [error.message]);
        }
    }

    /* ---------- Polling ---------- */

    function stopStatusPolling() {
        if (state.statusTimer) {
            window.clearInterval(state.statusTimer);
            state.statusTimer = null;
        }
    }

    function startStatusPolling() {
        stopStatusPolling();
        if (document.hidden) {
            setSyncStatus("paused", "Paused");
            return;
        }
        state.statusTimer = window.setInterval(function () {
            loadStatus();
        }, statusPollIntervalMs);
    }

    function handleVisibilityChange() {
        if (document.hidden) {
            stopStatusPolling();
            setSyncStatus("paused", "Paused");
            return;
        }
        loadStatus({ force: true });
        startStatusPolling();
    }

    /* ---------- Event binding ---------- */

    function bindEvents() {
        elements.form.addEventListener("submit", function (event) {
            event.preventDefault();
            var raw = elements.input.value;
            var normalized = raw.includes("|") ? raw : ticketInput.normalizeManualTicketInput(raw);
            if (!raw.includes("|") && normalized !== raw) {
                elements.input.value = normalized;
            }
            submitScan(normalized, "manual");
        });
        elements.rosterSearch.addEventListener("input", function () {
            state.filter = elements.rosterSearch.value || "";
            renderRoster();
        });
        elements.rosterList.addEventListener("click", function (event) {
            var button = event.target.closest("[data-ticket-code]");
            if (!button) return;
            submitScan(button.dataset.ticketCode || "", "manual");
        });
        elements.recentList.addEventListener("click", function (event) {
            var button = event.target.closest("[data-undo-record]");
            if (!button) return;
            undoRecord(button.dataset.undoRecord || "");
        });
        elements.refreshButton.addEventListener("click", function () {
            loadStatus({ force: true });
        });
        elements.cameraStart.addEventListener("click", function () {
            cam.startCamera(cameraCtx);
        });
        elements.cameraStop.addEventListener("click", function () {
            cam.stopCamera(cameraCtx);
        });
        elements.input.addEventListener("input", function () {
            var before = elements.input.value;
            if (!before.includes("|")) {
                var after = ticketInput.normalizeManualTicketInput(before);
                if (after !== before) {
                    elements.input.value = after;
                }
            }
            showInputMatchPreview();
        });
        elements.input.addEventListener("focus", function () {
            showInputMatchPreview();
        });
        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("pagehide", stopStatusPolling);
    }

    /* ---------- Init ---------- */

    document.addEventListener("DOMContentLoaded", function () {
        if (!elements.cameraReader.id) {
            elements.cameraReader.id = "checkin-camera-reader";
        }
        bindEvents();
        loadStatus({ force: true });
        startStatusPolling();
        elements.input.focus();
    });
})();
