(function () {
    const configElement = document.getElementById("checkin-console-config");
    if (!configElement) return;

    const config = JSON.parse(configElement.textContent || "{}");
    const statusPollIntervalMs = Number(config.statusPollIntervalMs) || 2000;
    const state = {
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
    };

    const root = document.querySelector("[data-checkin-console]");
    if (!root) return;

    const elements = {
        form: root.querySelector("[data-scan-form]"),
        input: root.querySelector("[data-scan-input]"),
        scanButton: root.querySelector("[data-scan-button]"),
        result: root.querySelector("[data-scan-result]"),
        total: root.querySelector("[data-stat-total]"),
        scanned: root.querySelector("[data-stat-scanned]"),
        stationScanned: root.querySelector("[data-stat-station]"),
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
    };

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(";").shift();
        return "";
    }

    function csrfToken() {
        return getCookie("csrftoken") || config.csrfToken || "";
    }

    function node(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = String(text);
        return element;
    }

    function clear(element) {
        element.replaceChildren();
    }

    function formatTime(value) {
        if (!value) return "";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "";
        return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
    }

    function formatClock(date) {
        return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
    }

    async function requestJson(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                ...(options && options.headers ? options.headers : {}),
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok && !data.detail) {
            data.detail = `HTTP ${response.status}`;
        }
        data._ok = response.ok;
        data._statusCode = response.status;
        return data;
    }

    function setResult(kind, title, lines) {
        elements.result.className = `i2g-checkin-result is-visible is-${kind}`;
        clear(elements.result);
        elements.result.appendChild(node("strong", "", title));
        (lines || []).filter(Boolean).forEach((line) => {
            elements.result.appendChild(node("span", "", line));
        });
    }

    function attendeeLine(attendee) {
        if (!attendee) return "";
        return [attendee.email, attendee.ticket_type].filter(Boolean).join(" - ");
    }

    function setSyncStatus(kind, label) {
        elements.syncStatus.className = `i2g-checkin-sync is-${kind}`;
        elements.syncLabel.textContent = label;
    }

    async function submitScan(value, source) {
        const barcode = String(value || "").trim();
        if (!barcode) return;

        elements.scanButton.disabled = true;
        try {
            const data = await requestJson(config.scanUrl, {
                method: "POST",
                body: JSON.stringify({ barcode }),
            });

            if (data.status === "success") {
                setResult("success", "Checked in", [
                    data.attendee && data.attendee.name,
                    attendeeLine(data.attendee),
                    data.attendee ? `Code: ${data.attendee.ticket_code}` : "",
                ]);
                elements.input.value = "";
                await loadStatus({ force: true });
            } else if (data.status === "duplicate") {
                const station = data.existing_check_in && data.existing_check_in.name;
                setResult("duplicate", "Already checked in", [
                    data.attendee && data.attendee.name,
                    station ? `Station: ${station}` : "",
                    data.scanned_at ? `Time: ${formatTime(data.scanned_at)}` : data.detail,
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

    function updateStats(data) {
        elements.total.textContent = data.total ?? "-";
        elements.scanned.textContent = data.scanned ?? "-";
        elements.stationScanned.textContent = data.station_scanned ?? "-";
        const remaining = Array.isArray(data.not_checked_in) ? data.not_checked_in.length : "-";
        elements.remaining.textContent = remaining;
    }

    function renderRoster() {
        const term = state.filter.trim().toLowerCase();
        const rows = term
            ? state.roster.filter((attendee) =>
                  [attendee.name, attendee.email, attendee.ticket_type, attendee.ticket_code]
                      .filter(Boolean)
                      .join(" ")
                      .toLowerCase()
                      .includes(term)
              )
            : state.roster;

        clear(elements.rosterList);
        if (!rows.length) {
            elements.rosterList.appendChild(node("div", "i2g-checkin-empty", "No matching attendees."));
            return;
        }

        rows.forEach((attendee) => {
            const row = node("div", "i2g-checkin-row");
            const text = document.createElement("div");
            text.append(
                node("strong", "", attendee.name || "Unnamed attendee"),
                node("span", "", attendeeLine(attendee)),
                node("code", "", attendee.ticket_code || "")
            );
            const button = node("button", "", "Check In");
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

        state.recent.forEach((record) => {
            const row = node("div", "i2g-checkin-row");
            const text = document.createElement("div");
            text.append(
                node("strong", "", record.attendee && record.attendee.name ? record.attendee.name : "Unnamed attendee"),
                node("span", "", `${formatTime(record.scanned_at)} - ${record.attendee.ticket_type || ""}`),
                node("code", "", record.attendee.ticket_code || "")
            );
            const button = node("button", "", "Undo");
            button.type = "button";
            button.dataset.undoRecord = record.id || "";
            row.append(text, button);
            elements.recentList.appendChild(row);
        });
    }

    async function loadStatus(options) {
        const force = Boolean(options && options.force);
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
        state.statusPromise = (async () => {
            try {
                const data = await requestJson(config.statusUrl, { method: "GET" });
                if (data._ok === false) {
                    throw new Error(data.detail || `HTTP ${data._statusCode}`);
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
                    setSyncStatus("live", `Live sync \u00b7 updated ${formatClock(new Date())}`);
                }
                return data;
            } catch (error) {
                setSyncStatus(
                    document.hidden ? "paused" : "issue",
                    document.hidden ? "Paused" : "Sync issue \u00b7 retrying"
                );
                if (!state.hasLoadedStatus) {
                    elements.rosterList.replaceChildren(
                        node("div", "i2g-checkin-empty", `Failed to load attendees: ${error.message}`)
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
        const url = config.undoUrlTemplate.replace("__record_id__", recordId);
        try {
            const data = await requestJson(url, { method: "POST", body: JSON.stringify({}) });
            if (data.status === "removed") {
                setResult("success", "Check-in undone", [`Record: ${recordId}`]);
                await loadStatus({ force: true });
            } else {
                setResult("error", "Unable to undo", [data.detail || "Unknown error"]);
            }
        } catch (error) {
            setResult("error", "Network error", [error.message]);
        }
    }

    function setCameraStatus(text) {
        elements.cameraStatus.textContent = text;
    }

    function setCameraMessage(kind, text) {
        elements.cameraMessage.textContent = text || "";
        elements.cameraMessage.className = text
            ? `i2g-checkin-camera-message is-visible is-${kind}`
            : "i2g-checkin-camera-message";
    }

    function cameraErrorMessage(error) {
        const message = error && error.message ? error.message : String(error || "");
        if (/permission|notallowed|denied/i.test(message)) return "Permission denied";
        if (/notfound|device not found|no camera/i.test(message)) return "No camera found";
        return message || "Camera unavailable";
    }

    async function startCamera() {
        if (state.cameraRunning) return;
        if (typeof Html5Qrcode !== "function" || typeof Html5QrcodeSupportedFormats === "undefined") {
            setCameraStatus("Unavailable");
            setCameraMessage("error", "Camera scanner unavailable");
            elements.cameraStart.disabled = true;
            return;
        }
        if (!state.camera) {
            state.camera = new Html5Qrcode(elements.cameraReader.id || "checkin-camera-reader");
        }

        elements.cameraStart.disabled = true;
        setCameraStatus("Starting");
        setCameraMessage("", "");
        try {
            await state.camera.start(
                { facingMode: "environment" },
                {
                    fps: 10,
                    qrbox: { width: 320, height: 180 },
                    formatsToSupport: [
                        Html5QrcodeSupportedFormats.PDF_417,
                        Html5QrcodeSupportedFormats.QR_CODE,
                        Html5QrcodeSupportedFormats.CODE_128,
                        Html5QrcodeSupportedFormats.CODE_39,
                    ],
                },
                (decodedText) => {
                    if (state.cameraCooling) return;
                    state.cameraCooling = true;
                    submitScan(decodedText, "camera").finally(() => {
                        setTimeout(() => {
                            state.cameraCooling = false;
                        }, 1800);
                    });
                },
                () => {}
            );
            state.cameraRunning = true;
            elements.cameraReader.classList.add("is-running");
            elements.cameraStop.disabled = false;
            setCameraStatus("Running");
        } catch (error) {
            elements.cameraStart.disabled = false;
            elements.cameraStop.disabled = true;
            elements.cameraReader.classList.remove("is-running");
            setCameraStatus("Blocked");
            setCameraMessage("error", cameraErrorMessage(error));
            elements.input.focus();
        }
    }

    async function stopCamera() {
        if (!state.camera || !state.cameraRunning) return;
        elements.cameraStop.disabled = true;
        let stopError = null;
        try {
            await state.camera.stop();
        } catch (error) {
            stopError = error;
        } finally {
            state.cameraRunning = false;
            elements.cameraReader.classList.remove("is-running");
            elements.cameraStart.disabled = false;
            setCameraStatus("Idle");
            if (stopError) {
                setCameraMessage("error", stopError.message || "Camera stop failed");
            } else {
                setCameraMessage("", "");
            }
        }
    }

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
        state.statusTimer = window.setInterval(() => {
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

    function bindEvents() {
        elements.form.addEventListener("submit", (event) => {
            event.preventDefault();
            submitScan(elements.input.value, "manual");
        });
        elements.rosterSearch.addEventListener("input", () => {
            state.filter = elements.rosterSearch.value || "";
            renderRoster();
        });
        elements.rosterList.addEventListener("click", (event) => {
            const button = event.target.closest("[data-ticket-code]");
            if (!button) return;
            submitScan(button.dataset.ticketCode || "", "manual");
        });
        elements.recentList.addEventListener("click", (event) => {
            const button = event.target.closest("[data-undo-record]");
            if (!button) return;
            undoRecord(button.dataset.undoRecord || "");
        });
        elements.refreshButton.addEventListener("click", () => loadStatus({ force: true }));
        elements.cameraStart.addEventListener("click", startCamera);
        elements.cameraStop.addEventListener("click", stopCamera);
        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("pagehide", stopStatusPolling);
    }

    document.addEventListener("DOMContentLoaded", () => {
        if (!elements.cameraReader.id) {
            elements.cameraReader.id = "checkin-camera-reader";
        }
        bindEvents();
        loadStatus({ force: true });
        startStatusPolling();
        elements.input.focus();
    });
})();
