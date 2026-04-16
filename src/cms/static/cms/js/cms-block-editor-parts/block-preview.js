(function () {
    /**
     * Per-block preview via iframe + postMessage.
     *
     * Each block preview loads the React frontend at /_block-preview inside an
     * iframe, then sends block data via postMessage.  The frontend renders it
     * with the real BlockRenderer — pixel-perfect with the public site.
     */

    var PREVIEW_PATH = '/_block-preview';
    // Map of blockIdx → iframe element for active previews
    var iframeReadyMap = {};

    function getPreviewUrl() {
        var config = window.CMS_ROUTE_EDITOR || {};
        var base = (config.frontendUrl || '').replace(/\/+$/, '') || window.location.origin;
        return base + PREVIEW_PATH;
    }

    /**
     * Build the preview pane HTML with an iframe for a given block.
     * Called by renderers.js during renderAll().
     */
    function renderPreviewPane(block, idx) {
        var iframeId = 'cms-bp-iframe-' + idx;
        return '<div class="cms-block-preview-pane">'
            + '<div class="bp-label">Preview</div>'
            + '<div class="cms-block-preview-pane-inner">'
            + '<iframe id="' + iframeId + '" class="cms-bp-iframe" src="' + getPreviewUrl() + '" data-block-idx="' + idx + '"></iframe>'
            + '</div></div>';
    }

    /**
     * Initialise iframes after renderAll() rebuilds the DOM.
     * Attaches load listeners and sends initial block data once the iframe is ready.
     */
    function initIframes(blocks) {
        iframeReadyMap = {};
        document.querySelectorAll('.cms-bp-iframe').forEach(function (iframe) {
            var idx = parseInt(iframe.getAttribute('data-block-idx'), 10);
            if (isNaN(idx) || idx >= blocks.length) return;

            function sendData() {
                var pageCssClassEl = document.getElementById('id_page_css_class');
                iframe.contentWindow.postMessage({
                    type: 'cms-block-preview',
                    block: {
                        block_type: blocks[idx].block_type,
                        sort_order: idx,
                        data: blocks[idx].data,
                    },
                    pageCssClass: pageCssClassEl ? pageCssClassEl.value : '',
                }, '*');
            }

            // Listen for the "ready" signal from the iframe
            function onMessage(event) {
                if (event.source !== iframe.contentWindow) return;
                if (event.data && event.data.type === 'cms-block-preview-ready') {
                    iframeReadyMap[idx] = iframe;
                    sendData();
                    // Auto-resize once content renders
                    scheduleResize(iframe);
                }
            }
            window.addEventListener('message', onMessage);
            iframe._previewCleanup = function () { window.removeEventListener('message', onMessage); };

            // If iframe is already loaded (cached), the ready message may have already fired
            // Give a fallback timeout to send data
            iframe.addEventListener('load', function () {
                setTimeout(function () {
                    if (!iframeReadyMap[idx]) {
                        iframeReadyMap[idx] = iframe;
                        sendData();
                        scheduleResize(iframe);
                    }
                }, 300);
            });
        });
    }

    /**
     * Send updated block data to a single preview iframe (real-time update).
     */
    function updatePreview(idx, block) {
        var iframe = iframeReadyMap[idx];
        if (!iframe || !iframe.contentWindow) return;
        var pageCssClassEl = document.getElementById('id_page_css_class');
        iframe.contentWindow.postMessage({
            type: 'cms-block-preview',
            block: {
                block_type: block.block_type,
                sort_order: idx,
                data: block.data,
            },
            pageCssClass: pageCssClassEl ? pageCssClassEl.value : '',
        }, '*');
        scheduleResize(iframe);
    }

    /**
     * Update all active preview iframes with current block data.
     */
    function refreshAllPreviews(blocks, previewSet) {
        previewSet.forEach(function (idx) {
            if (idx >= blocks.length) return;
            updatePreview(idx, blocks[idx]);
        });
    }

    /**
     * Auto-resize iframe to fit its content (no scrollbar in the iframe itself).
     */
    function scheduleResize(iframe) {
        setTimeout(function () { resizeIframe(iframe); }, 200);
        setTimeout(function () { resizeIframe(iframe); }, 600);
        setTimeout(function () { resizeIframe(iframe); }, 1500);
    }

    function resizeIframe(iframe) {
        try {
            var body = iframe.contentDocument && iframe.contentDocument.body;
            if (!body) return;
            var height = body.scrollHeight;
            if (height > 20) {
                iframe.style.height = Math.min(height + 16, 600) + 'px';
            }
        } catch (e) {
            // Cross-origin — cannot access; iframe stays at CSS default height
        }
    }

    window.ITGCmsBlockPreview = {
        renderPreviewPane: renderPreviewPane,
        initIframes: initIframes,
        updatePreview: updatePreview,
        refreshAllPreviews: refreshAllPreviews,
    };
})();
