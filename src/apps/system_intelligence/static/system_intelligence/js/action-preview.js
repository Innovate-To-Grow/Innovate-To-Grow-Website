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

    function frameOrigin(frame) {
        try {
            return new URL(frame.getAttribute('src') || '', window.location.href).origin;
        } catch (e) {
            return '';
        }
    }

    function sendBlock(frame, nonce) {
        var origin = frameOrigin(frame);
        if (!origin || !frame.contentWindow) return;
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
        var sent = false;

        window.addEventListener('message', function (event) {
            if (event.source !== frame.contentWindow || event.origin !== frameOrigin(frame)) return;
            var message = event.data || {};
            if (message.nonce !== nonce) return;
            if (message.type === 'cms-block-preview-ready') {
                sent = true;
                sendBlock(frame, nonce);
            } else if (message.type === 'cms-block-preview-resize') {
                setHeight(frame, message.height);
            }
        });

        // The ready message can arrive before this listener on a cached frame.
        frame.addEventListener('load', function () {
            window.setTimeout(function () {
                if (sent) return;
                sent = true;
                sendBlock(frame, nonce);
            }, 300);
        });
    });
})();
