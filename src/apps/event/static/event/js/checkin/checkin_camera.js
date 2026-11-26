/**
 * Camera scanning: html5-qrcode lifecycle, scan preview card, and error handling.
 * Depends on checkin_shared.js and checkin_ticket_input.js.
 */
(function () {
    "use strict";

    var ns = window.__checkinConsole;
    if (!ns) return;
    var node = ns.utils.node;
    var clear = ns.utils.clear;
    var ticketInput = ns.ticketInput;

    function setCameraStatus(elements, text) {
        elements.cameraStatus.textContent = text;
    }

    function setCameraMessage(elements, kind, text) {
        elements.cameraMessage.textContent = text || "";
        elements.cameraMessage.className = text
            ? "i2g-checkin-camera-message is-visible is-" + kind
            : "i2g-checkin-camera-message";
    }

    function cameraErrorMessage(error) {
        var message = error && error.message ? error.message : String(error || "");
        if (/permission|notallowed|denied/i.test(message)) {
            return "Camera permission is required. Allow camera access in your browser, then try again.";
        }
        if (/notfound|device not found|no camera/i.test(message)) return "No camera found";
        return message || "Camera unavailable";
    }

    function pdf417ScanBox(viewfinderWidth, viewfinderHeight) {
        var width = Math.floor(Math.min(viewfinderWidth * 0.98, 800));
        var height = Math.floor(Math.min(viewfinderHeight * 0.85, Math.max(width * 0.4, 200)));
        return {
            width: Math.max(width, Math.min(viewfinderWidth, 300)),
            height: Math.max(height, Math.min(viewfinderHeight, 150)),
        };
    }

    /**
     * Build and display the camera-scan preview card in the result area.
     * Shows attendee info (if matched) plus an inline Check In button.
     */
    function showScanPreview(decodedText, ctx) {
        var raw = String(decodedText || "").trim();
        if (!raw) return;
        console.log("[checkin] camera decoded:", raw);

        var normalized = raw.includes("|") ? raw : ticketInput.normalizeManualTicketInput(raw);

        var attendee = ticketInput.findAttendeeByBarcode(normalized, ctx.state.roster);
        var submitCode = attendee ? attendee.ticket_code : normalized;
        ctx.elements.input.value = submitCode;

        if (attendee && ctx.showAttendeePreview) {
            ctx.showAttendeePreview(attendee, submitCode);
        } else {
            ctx.elements.result.className = "i2g-checkin-result is-visible is-preview";
            clear(ctx.elements.result);

            var card = document.createElement("div");
            card.className = "i2g-checkin-preview-card";

            var info = document.createElement("div");
            info.className = "i2g-checkin-preview-info";
            info.appendChild(node("strong", "", "Code scanned"));
            if (normalized) info.appendChild(node("span", "", normalized));

            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "i2g-checkin-preview-action";
            var icon = document.createElement("span");
            icon.className = "material-symbols-outlined";
            icon.textContent = "login";
            btn.appendChild(icon);
            btn.appendChild(document.createTextNode("Check In"));
            btn.addEventListener("click", function () {
                ctx.submitScan(submitCode, "camera-preview");
            });

            card.appendChild(info);
            card.appendChild(btn);
            ctx.elements.result.appendChild(card);
        }
    }

    /**
     * Start the camera scanner via html5-qrcode.
     * @param {object} ctx - { state, elements, submitScan }
     */
    async function startCamera(ctx) {
        var state = ctx.state;
        var elements = ctx.elements;

        if (state.cameraRunning) return;
        if (typeof Html5Qrcode !== "function" || typeof Html5QrcodeSupportedFormats === "undefined") {
            setCameraStatus(elements, "Unavailable");
            setCameraMessage(elements, "error", "Camera scanner unavailable");
            elements.cameraStart.disabled = true;
            return;
        }

        if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
            setCameraStatus(elements, "Blocked");
            setCameraMessage(elements, "error", "Camera access is not available in this browser.");
            return;
        }

        elements.cameraStart.disabled = true;
        setCameraStatus(elements, "Starting");
        setCameraMessage(elements, "info", "Starting camera\u2026 allow access if prompted.");
        try {
            if (!state.camera) {
                state.camera = new Html5Qrcode(elements.cameraReader.id || "checkin-camera-reader", {
                    formatsToSupport: [
                        Html5QrcodeSupportedFormats.PDF_417,
                        Html5QrcodeSupportedFormats.QR_CODE,
                        Html5QrcodeSupportedFormats.CODE_128,
                        Html5QrcodeSupportedFormats.CODE_39,
                    ],
                });
            }
            await state.camera.start(
                { facingMode: "environment" },
                {
                    fps: 10,
                    qrbox: pdf417ScanBox,
                    aspectRatio: 1.7777778,
                    disableFlip: true,
                },
                function (decodedText) {
                    if (state.cameraCooling) return;
                    state.cameraCooling = true;
                    showScanPreview(decodedText, ctx);
                    setTimeout(function () {
                        state.cameraCooling = false;
                    }, 2500);
                },
                function () {}
            );
            state.cameraRunning = true;
            elements.cameraReader.classList.add("is-running");
            elements.cameraStop.disabled = false;
            setCameraStatus(elements, "Running");
            setCameraMessage(elements, "info", "Point camera at the barcode on the ticket.");
        } catch (error) {
            elements.cameraStart.disabled = false;
            elements.cameraStop.disabled = true;
            elements.cameraReader.classList.remove("is-running");
            setCameraStatus(elements, "Blocked");
            setCameraMessage(elements, "error", cameraErrorMessage(error));
            elements.input.focus();
        }
    }

    async function stopCamera(ctx) {
        var state = ctx.state;
        var elements = ctx.elements;

        if (!state.camera) return;
        elements.cameraStop.disabled = true;
        elements.cameraStart.disabled = true;
        var stopError = null;
        try {
            if (state.cameraRunning) {
                await state.camera.stop();
            }
        } catch (error) {
            stopError = error;
        } finally {
            state.cameraRunning = false;
            state.cameraCooling = false;
            elements.cameraReader.classList.remove("is-running");
            elements.cameraStart.disabled = false;
            setCameraStatus(elements, "Idle");
            if (stopError) {
                setCameraMessage(elements, "error", stopError.message || "Camera stop failed");
            } else {
                setCameraMessage(elements, "", "");
            }
        }
    }

    ns.camera = {
        startCamera: startCamera,
        stopCamera: stopCamera,
        showScanPreview: showScanPreview,
    };
})();
