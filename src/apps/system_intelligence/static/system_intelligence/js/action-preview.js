(function () {
    'use strict';

    /**
     * System Intelligence CMS action preview: posts each proposed block to its
     * /_block-preview frame, which renders it with the public site's own
     * components and CSS. Same protocol as cms-block-editor-parts/block-preview.js:
     *   frame -> parent: { type: 'cms-block-preview-ready' | 'cms-block-preview-resize', nonce, height? }
     *   parent -> frame: { type: 'cms-block-preview', nonce, block, pageCssClass }
     */

    var MAX_HEIGHT = 4000;
    var PREVIEW_PATH = '/_block-preview';
    var dataElement = document.getElementById('si-action-preview-data');
    if (!dataElement) return;

    var payload;
    try {
        payload = JSON.parse(dataElement.textContent || '{}');
    } catch (e) {
        return;
    }
    var blocks = {};
    (payload.blocks || []).forEach(function (entry) {
        if (entry && entry.nonce) blocks[entry.nonce] = entry.block;
    });

    // The frame URL is rebuilt from a fixed scheme, the validated host, the fixed preview path and
    // the encoded nonce rather than copying the data-src text into src, so a frame can only ever
    // load an http(s) /_block-preview page, never e.g. a javascript: or data: URL.
    function previewUrl(frame, nonce) {
        var parsed;
        try {
            parsed = new URL(frame.getAttribute('data-src') || '', window.location.href);
        } catch (e) {
            return '';
        }
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return '';
        if (parsed.username || parsed.password || parsed.pathname !== PREVIEW_PATH) return '';
        var scheme = parsed.protocol === 'https:' ? 'https://' : 'http://';
        return scheme + parsed.host + PREVIEW_PATH + '?nonce=' + encodeURIComponent(nonce);
    }

    function sendBlock(frame, nonce, origin) {
        if (!frame.contentWindow) return;
        frame.contentWindow.postMessage({
            type: 'cms-block-preview',
            nonce: nonce,
            block: blocks[nonce],
            pageCssClass: payload.pageCssClass || '',
        }, origin);
    }

    function setHeight(frame, rawHeight) {
        var height = Number(rawHeight);
        if (!isFinite(height) || height <= 20) return;
        frame.style.height = Math.min(Math.ceil(height), MAX_HEIGHT) + 'px';
    }

    document.querySelectorAll('.si-action-preview-frame').forEach(function (frame) {
        var nonce = frame.getAttribute('data-preview-nonce') || '';
        if (!nonce || !blocks[nonce]) return;
        var src = previewUrl(frame, nonce);
        if (!src) return;
        var origin = new URL(src).origin;
        var sent = false;

        window.addEventListener('message', function (event) {
            if (event.source !== frame.contentWindow || event.origin !== origin) return;
            var message = event.data || {};
            if (message.nonce !== nonce) return;
            if (message.type === 'cms-block-preview-ready') {
                sent = true;
                sendBlock(frame, nonce, origin);
            } else if (message.type === 'cms-block-preview-resize') {
                setHeight(frame, message.height);
            }
        });

        // Fallback for a ready message that never arrives.
        frame.addEventListener('load', function () {
            window.setTimeout(function () {
                if (sent) return;
                sent = true;
                sendBlock(frame, nonce, origin);
            }, 300);
        });

        // The frame starts loading only now, so neither its ready message nor its load event can
        // arrive before the listeners above exist.
        frame.setAttribute('src', src);
    });
})();
