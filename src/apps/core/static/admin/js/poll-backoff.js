/**
 * Back-off for admin pages that poll the server (check-in console and summary, campaign / SMS send status, the
 * delivery-rates status, the CMS live-preview keepalive). When the server answers 429 Too Many Requests, a poller
 * stops asking until the wait the server named in Retry-After (or the body's `retry_after`) has passed, and waits
 * longer each time it is refused again in a row: base x 2^strikes, capped at maxMs, never shorter than the server's
 * wait. The first answer that is not a 429 clears the back-off.
 *
 *   var gate = window.I2GPollBackoff.createGate({ baseMs: 2000 });
 *   if (gate.blocked()) return;                      // skip this tick
 *   ... if (response.status === 429) gate.refused(I2GPollBackoff.retryAfterMs(response, data));
 *   ... else gate.succeeded();
 */
(function () {
    "use strict";

    var DEFAULT_BASE_MS = 2000;
    var DEFAULT_MAX_MS = 60000;

    function headerValue(source) {
        var headers = source && source.headers;
        if (!headers) return null;
        if (typeof headers.get === "function") return headers.get("Retry-After");
        return headers["retry-after"] || headers["Retry-After"] || null;
    }

    /** A Retry-After value (delta-seconds or an HTTP date) in milliseconds, or null when absent or unusable. */
    function parseRetryAfter(value, now) {
        var text = value === null || value === undefined ? "" : String(value).trim();
        if (!text) return null;
        if (/^\d+(\.\d+)?$/.test(text)) return Number(text) * 1000;
        var delay = Date.parse(text) - (now === undefined ? Date.now() : now);
        return isFinite(delay) && delay >= 0 ? delay : null;
    }

    /** The wait a refused response asks for, in ms: its Retry-After header, else the JSON body's retry_after. */
    function retryAfterMs(response, data) {
        var fromHeader = parseRetryAfter(headerValue(response));
        if (fromHeader !== null) return fromHeader;
        var seconds = data && typeof data === "object" ? data.retry_after : undefined;
        return typeof seconds === "number" && isFinite(seconds) && seconds >= 0 ? seconds * 1000 : null;
    }

    /** "in N seconds" for a wait in ms, or "in a moment" when none is known. */
    function waitText(ms) {
        if (ms === null || ms === undefined) return "in a moment";
        var seconds = Math.max(1, Math.ceil(ms / 1000));
        return "in " + seconds + (seconds === 1 ? " second" : " seconds");
    }

    function createGate(options) {
        var baseMs = Number(options && options.baseMs) || DEFAULT_BASE_MS;
        var maxMs = Number(options && options.maxMs) || DEFAULT_MAX_MS;
        var now = (options && options.now) || Date.now;
        var strikes = 0;
        var until = 0;

        return {
            /** True while a poll should be skipped. */
            blocked: function () {
                return now() < until;
            },
            /** Milliseconds left in the current back-off (0 when none). */
            remainingMs: function () {
                return Math.max(0, until - now());
            },
            /** Record a 429; returns how long polling now waits. */
            refused: function (serverWaitMs) {
                strikes += 1;
                var grown = Math.min(maxMs, baseMs * Math.pow(2, strikes));
                var wait = Math.max(grown, serverWaitMs || 0);
                until = now() + wait;
                return wait;
            },
            /** Record an answer that was not a 429: the back-off ends. */
            succeeded: function () {
                strikes = 0;
                until = 0;
            },
            strikes: function () {
                return strikes;
            },
        };
    }

    window.I2GPollBackoff = {
        createGate: createGate,
        parseRetryAfter: parseRetryAfter,
        retryAfterMs: retryAfterMs,
        waitText: waitText,
    };
})();
