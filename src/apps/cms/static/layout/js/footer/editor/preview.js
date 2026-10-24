(function () {
    /**
     * Footer editor preview: the SPA's /_footer-preview renders the real Footer with the site's CSS,
     * from the content this page posts. Same protocol shape as cms-block-editor-parts/block-preview.js:
     *   frame -> parent: { type: 'cms-footer-preview-ready' | 'cms-footer-preview-resize', nonce, height? }
     *   parent -> frame: { type: 'cms-footer-preview', nonce, content }
     */
    var PREVIEW_PATH = '/_footer-preview';
    var MAX_HEIGHT = 1600;
    var state = { iframe: null, nonce: '', ready: false, content: null };

    function createNonce() {
        if (!window.crypto || typeof window.crypto.getRandomValues !== 'function') return '';
        var bytes = new Uint8Array(18);
        window.crypto.getRandomValues(bytes);
        return Array.from(bytes, function (value) { return value.toString(16).padStart(2, '0'); }).join('');
    }

    function frameOrigin(iframe) {
        try {
            return new URL(iframe.getAttribute('src') || '', window.location.href).origin;
        } catch (e) {
            return '';
        }
    }

    function post() {
        var iframe = state.iframe;
        if (!iframe || !state.ready || !state.content || !iframe.contentWindow) return;
        iframe.contentWindow.postMessage(
            { type: 'cms-footer-preview', nonce: state.nonce, content: state.content },
            frameOrigin(iframe)
        );
    }

    function onMessage(event) {
        var iframe = state.iframe;
        if (!iframe || event.source !== iframe.contentWindow || event.origin !== frameOrigin(iframe)) return;
        var message = event.data || {};
        if (message.nonce !== state.nonce) return;
        if (message.type === 'cms-footer-preview-ready') {
            state.ready = true;
            post();
        } else if (message.type === 'cms-footer-preview-resize') {
            var height = Number(message.height);
            if (isFinite(height) && height > 20) iframe.style.height = Math.min(Math.ceil(height), MAX_HEIGHT) + 'px';
        }
    }

    function start(iframe, errorBox) {
        state.iframe = iframe;
        state.nonce = createNonce();
        if (!state.nonce) {
            if (errorBox) errorBox.textContent = 'Preview unavailable: this browser has no secure random number generator.';
            return;
        }
        window.addEventListener('message', onMessage);
        // A fallback for a ready message that never arrives (the frame was already loaded).
        iframe.addEventListener('load', function () {
            window.setTimeout(function () {
                if (state.ready) return;
                state.ready = true;
                post();
            }, 300);
        });
        var base = (iframe.getAttribute('data-preview-base') || '').replace(/\/+$/, '');
        iframe.setAttribute('src', base + PREVIEW_PATH + '?nonce=' + encodeURIComponent(state.nonce));
    }

    function updatePreview(iframe, errorBox, footerData) {
        if (!iframe) return;
        if (state.iframe !== iframe) start(iframe, errorBox);
        // A copy, so later edits to the editor's object never race the frame's render.
        state.content = JSON.parse(JSON.stringify(footerData || {}));
        post();
    }

    window.ITGFooterPreview = { updatePreview: updatePreview };
})();
