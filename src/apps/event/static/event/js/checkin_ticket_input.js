/**
 * Ticket code input: normalization, barcode-to-attendee lookup, and autocomplete suggestions.
 * Depends on checkin_shared.js (window.__checkinConsole.utils).
 */
(function () {
    "use strict";

    var ns = window.__checkinConsole;
    if (!ns) return;
    var node = ns.utils.node;
    var clear = ns.utils.clear;

    /** Matches server-side ticket codes: I2G- + 12 hex (see generate_registration_ticket_code). */
    function normalizeManualTicketInput(value) {
        var raw = String(value || "");
        if (!raw.trim()) return "";
        if (raw.includes("|")) return raw;
        var compact = raw.replace(/\s/g, "");
        if (!compact) return "";

        var embedded = /\bI2G-[0-9A-Fa-f]{12}\b/i.exec(compact);
        if (embedded) return embedded[0].toUpperCase();

        var withPrefix = compact.match(/^(I2G)(-?)([0-9A-Fa-f]*)$/i);
        if (withPrefix) {
            var hex = withPrefix[3].replace(/[^0-9A-Fa-f]/g, "").toUpperCase().slice(0, 12);
            return "I2G-" + hex;
        }

        if (/^i$/i.test(compact)) return "I";
        if (/^i2$/i.test(compact)) return "I2";
        if (/^i2g$/i.test(compact)) return "I2G-";

        var hexOnly = compact.replace(/[^0-9A-Fa-f]/g, "").toUpperCase().slice(0, 12);
        if (hexOnly) return "I2G-" + hexOnly;

        return compact.toUpperCase();
    }

    /**
     * Match a scanned barcode payload (e.g. "I2G|EVENT|slug|I2G-XXXXXXXXXXXX")
     * against the attendee roster to find the corresponding attendee.
     */
    function findAttendeeByBarcode(barcode, roster) {
        if (!barcode) return null;
        var lower = barcode.toLowerCase();

        var found = roster.find(function (a) {
            return a.ticket_code && a.ticket_code.toLowerCase() === lower;
        });
        if (found) return found;

        if (barcode.includes("|")) {
            var parts = barcode.split("|");
            if (parts.length >= 4 && parts[0].toUpperCase() === "I2G" && parts[1].toUpperCase() === "EVENT") {
                var pipeCode = parts[3].trim().toUpperCase();
                found = roster.find(function (a) {
                    return a.ticket_code && a.ticket_code.toUpperCase() === pipeCode;
                });
                if (found) return found;
            }
            for (var pi = 0; pi < parts.length; pi++) {
                var part = parts[pi].trim().toUpperCase();
                found = roster.find(function (a) {
                    return a.ticket_code && a.ticket_code.toUpperCase() === part;
                });
                if (found) return found;
            }
        }

        var match = /I2G-[0-9A-Fa-f]{12}/i.exec(barcode);
        if (match) {
            var extracted = match[0].toUpperCase();
            found = roster.find(function (a) {
                return a.ticket_code && a.ticket_code.toUpperCase() === extracted;
            });
            if (found) return found;
        }

        found = roster.find(function (a) {
            return a.ticket_code && lower.includes(a.ticket_code.toLowerCase());
        });
        return found || null;
    }

    function getSuggestionMatches(inputValue, roster) {
        var query = String(inputValue || "").trim();
        if (query.includes("|")) return [];
        var normalized = normalizeManualTicketInput(query);
        var prefix = normalized.replace(/\s/g, "").toLowerCase();
        if (!prefix) return [];
        var seen = new Set();
        var matches = [];
        var maxOptions = 30;
        for (var i = 0; i < roster.length && matches.length < maxOptions; i += 1) {
            var attendee = roster[i];
            var code = attendee && attendee.ticket_code;
            if (!code || seen.has(code)) continue;
            if (!code.toLowerCase().startsWith(prefix)) continue;
            seen.add(code);
            matches.push(attendee);
        }
        return matches;
    }

    function hideSuggestions(panel, input, state) {
        if (panel) panel.hidden = true;
        if (input) {
            input.setAttribute("aria-expanded", "false");
            input.removeAttribute("aria-activedescendant");
        }
        state.suggestionActiveIndex = -1;
    }

    function highlightSuggestion(index, panel, input) {
        if (!panel) return;
        var options = panel.querySelectorAll(".i2g-checkin-suggestion");
        options.forEach(function (opt, i) {
            var active = i === index;
            opt.classList.toggle("is-highlighted", active);
            opt.setAttribute("aria-selected", active ? "true" : "false");
        });
        if (input) {
            if (index >= 0 && options[index]) {
                input.setAttribute("aria-activedescendant", options[index].id);
            } else {
                input.removeAttribute("aria-activedescendant");
            }
        }
        if (options[index]) {
            options[index].scrollIntoView({ block: "nearest" });
        }
    }

    function applySuggestion(ticketCode, input, panel, state) {
        if (!input) return;
        input.value = ticketCode;
        hideSuggestions(panel, input, state);
        input.focus();
    }

    function renderSuggestions(panel, input, roster, state) {
        if (!panel || !input) return;
        clear(panel);
        var matches = getSuggestionMatches(input.value, roster);
        if (!matches.length) {
            hideSuggestions(panel, input, state);
            return;
        }

        matches.forEach(function (attendee, index) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "i2g-checkin-suggestion";
            button.setAttribute("role", "option");
            button.setAttribute("id", "checkin-suggestion-" + index);
            button.dataset.ticketCode = attendee.ticket_code || "";
            button.dataset.index = String(index);
            button.appendChild(node("span", "i2g-checkin-suggestion__name", attendee.name || "Unnamed attendee"));
            var org = String(attendee.organization || "").trim();
            var typeLabel = attendee.ticket_type || "";
            var metaParts = [org, typeLabel].filter(Boolean);
            if (metaParts.length) {
                button.appendChild(node("span", "i2g-checkin-suggestion__meta", metaParts.join(" \u00b7 ")));
            }
            button.appendChild(node("code", "i2g-checkin-suggestion__code", attendee.ticket_code || ""));
            panel.appendChild(button);
        });

        panel.hidden = false;
        input.setAttribute("aria-expanded", "true");
        state.suggestionActiveIndex = matches.length > 0 ? 0 : -1;
        if (state.suggestionActiveIndex >= 0) {
            highlightSuggestion(state.suggestionActiveIndex, panel, input);
        }
    }

    ns.ticketInput = {
        normalizeManualTicketInput: normalizeManualTicketInput,
        findAttendeeByBarcode: findAttendeeByBarcode,
        getSuggestionMatches: getSuggestionMatches,
        hideSuggestions: hideSuggestions,
        highlightSuggestion: highlightSuggestion,
        applySuggestion: applySuggestion,
        renderSuggestions: renderSuggestions,
    };
})();
