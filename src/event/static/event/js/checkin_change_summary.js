(function () {
    "use strict";

    const configElement = document.getElementById("checkin-summary-config");
    if (!configElement) return;

    const root = document.querySelector("[data-checkin-summary]");
    if (!root) return;

    const config = JSON.parse(configElement.textContent || "{}");
    if (!config.statusUrl) return;

    const pollIntervalMs = Number(config.pollIntervalMs) || 2000;
    const state = {
        loaded: false,
        loading: false,
        promise: null,
        queued: false,
        timer: null,
        refreshEndTimer: null,
    };

    const elements = {
        total: root.querySelector("[data-summary-total]"),
        scanned: root.querySelector("[data-summary-scanned]"),
        remaining: root.querySelector("[data-summary-remaining]"),
        sync: root.querySelector("[data-summary-sync]"),
        syncLabel: root.querySelector("[data-summary-sync-label]"),
        recentList: root.querySelector("[data-summary-recent-list]"),
    };

    function node(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = String(text);
        return element;
    }

    function clear(element) {
        element.replaceChildren();
    }

    function numberText(value) {
        return Number.isFinite(Number(value)) ? String(value) : "-";
    }

    function attendeeLine(attendee) {
        if (!attendee) return "";
        return [attendee.email, attendee.ticket_type].filter(Boolean).join(" - ");
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

    function setSyncStatus(kind, label) {
        elements.sync.className = `i2g-checkin-summary__sync is-${kind}`;
        elements.syncLabel.textContent = label;
    }

    function setRefreshing(isRefreshing) {
        window.clearTimeout(state.refreshEndTimer);
        if (isRefreshing) {
            elements.sync.classList.add("is-refreshing");
            return;
        }
        state.refreshEndTimer = window.setTimeout(() => {
            elements.sync.classList.remove("is-refreshing");
        }, 350);
    }

    function updateStats(data) {
        elements.total.textContent = numberText(data.total);
        elements.scanned.textContent = numberText(data.scanned);

        if (Array.isArray(data.not_checked_in)) {
            elements.remaining.textContent = String(data.not_checked_in.length);
        } else if (Number.isFinite(Number(data.total)) && Number.isFinite(Number(data.scanned))) {
            elements.remaining.textContent = String(Math.max(0, Number(data.total) - Number(data.scanned)));
        } else {
            elements.remaining.textContent = "-";
        }
    }

    function renderRecent(records) {
        const recent = Array.isArray(records) ? records.slice(0, 5) : [];
        clear(elements.recentList);

        if (!recent.length) {
            elements.recentList.appendChild(node("div", "i2g-checkin-summary__empty", "No recent scans yet."));
            return;
        }

        recent.forEach((record) => {
            const attendee = record.attendee || {};
            const row = node("div", "i2g-checkin-summary__recent-row");
            const details = document.createElement("div");
            details.append(
                node("strong", "", attendee.name || "Unnamed attendee"),
                node("span", "", attendeeLine(attendee)),
                node("code", "", attendee.ticket_code || "")
            );
            row.append(details, node("span", "i2g-checkin-summary__recent-time", formatTime(record.scanned_at)));
            elements.recentList.appendChild(row);
        });
    }

    async function requestStatus() {
        const response = await fetch(config.statusUrl, {
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
            },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return data;
    }

    async function loadStatus(options) {
        const force = Boolean(options && options.force);
        if (document.hidden && !force) {
            setSyncStatus("paused", "Paused");
            return null;
        }

        if (state.loading) {
            if (force) state.queued = true;
            return state.promise;
        }

        state.loading = true;
        if (state.loaded) {
            setRefreshing(true);
        } else {
            setSyncStatus("syncing", "Syncing...");
        }
        state.promise = (async () => {
            try {
                const data = await requestStatus();
                updateStats(data);
                renderRecent(data.recent_scans);
                state.loaded = true;
                if (document.hidden) {
                    setSyncStatus("paused", "Paused");
                } else {
                    setSyncStatus("live", `Live - updated ${formatClock(new Date())}`);
                }
                return data;
            } catch (error) {
                setSyncStatus(
                    document.hidden ? "paused" : "issue",
                    document.hidden ? "Paused" : "Sync issue - retrying"
                );
                if (!state.loaded) {
                    clear(elements.recentList);
                    elements.recentList.appendChild(
                        node("div", "i2g-checkin-summary__empty", `Unable to load status: ${error.message}`)
                    );
                }
                return null;
            } finally {
                state.loading = false;
                state.promise = null;
                setRefreshing(false);
                if (state.queued) {
                    state.queued = false;
                    loadStatus({ force: true });
                }
            }
        })();
        return state.promise;
    }

    function stopPolling() {
        if (state.timer) {
            window.clearInterval(state.timer);
            state.timer = null;
        }
    }

    function startPolling() {
        stopPolling();
        if (document.hidden) {
            setSyncStatus("paused", "Paused");
            return;
        }
        state.timer = window.setInterval(() => {
            loadStatus();
        }, pollIntervalMs);
    }

    function handleVisibilityChange() {
        if (document.hidden) {
            stopPolling();
            setSyncStatus("paused", "Paused");
            return;
        }
        loadStatus({ force: true });
        startPolling();
    }

    function init() {
        loadStatus({ force: true });
        startPolling();
        document.addEventListener("visibilitychange", handleVisibilityChange);
        window.addEventListener("pagehide", stopPolling);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
