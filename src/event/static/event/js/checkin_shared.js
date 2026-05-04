/**
 * Shared utilities for the check-in console.
 * Loaded first — sets up window.__checkinConsole namespace.
 */
(function () {
    "use strict";

    function getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(";").shift();
        return "";
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

    function csrfToken(configToken) {
        return getCookie("csrftoken") || configToken || "";
    }

    function requestJson(url, options, configToken) {
        return fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(configToken),
                ...(options && options.headers ? options.headers : {}),
            },
        })
            .then(function (response) {
                return response
                    .json()
                    .catch(function () {
                        return {};
                    })
                    .then(function (data) {
                        if (!response.ok && !data.detail) {
                            data.detail = "HTTP " + response.status;
                        }
                        data._ok = response.ok;
                        data._statusCode = response.status;
                        return data;
                    });
            });
    }

    window.__checkinConsole = {
        utils: {
            getCookie: getCookie,
            csrfToken: csrfToken,
            requestJson: requestJson,
            node: node,
            clear: clear,
            formatTime: formatTime,
            formatClock: formatClock,
        },
    };
})();
