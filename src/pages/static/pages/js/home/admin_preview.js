(function() {
    function initPreview() {
        const iframe = document.getElementById('home-preview');
        if (!iframe) return;

        // Initialize iframe content
        const doc = iframe.contentDocument || iframe.contentWindow.document;
        doc.open();
        doc.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <link rel="stylesheet" href="/static/css/theme.css">
                <link rel="stylesheet" href="/static/css/custom.css">
                <style>
                    body { padding: 20px; background: white; }
                    .home-container { width: 100% !important; margin: 0 !important; }
                </style>
            </head>
            <body class="html front not-logged-in no-sidebars page-node">
                <div id="main" class="clearfix main" role="main">
                    <div class="container">
                        <div id="main-content" class="row main-content">
                            <div id="content" class="mc-content span12">
                                <div class="home-container">
                                    <div class="home-content">
                                        <h1 class="home-title" id="preview-title"></h1>
                                        <div class="home-body" id="preview-body"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </body>
            </html>
        `);
        doc.close();

        // Sync Title
        const titleInput = document.getElementById('id_name');
        if (titleInput) {
            const updateTitle = () => {
                const previewTitle = doc.getElementById('preview-title');
                if (previewTitle) previewTitle.innerText = titleInput.value;
            };
            titleInput.addEventListener('input', updateTitle);
            updateTitle();
        }

        // Sync CKEditor 5 Body
        const bodyField = document.querySelector('[data-ck-editor-id="id_body"]');
        if (bodyField) {
            // CKEditor 5 uses a different API - watch for changes in the editable area
            const observer = new MutationObserver(() => {
                const previewBody = doc.getElementById('preview-body');
                const editableArea = bodyField.querySelector('.ck-editor__editable');
                if (previewBody && editableArea) {
                    previewBody.innerHTML = editableArea.innerHTML;
                }
            });

            // Wait for CKEditor 5 to initialize, then observe changes
            const initObserver = () => {
                const editableArea = bodyField.querySelector('.ck-editor__editable');
                if (editableArea) {
                    observer.observe(editableArea, { childList: true, subtree: true, characterData: true });
                    // Initial update
                    const previewBody = doc.getElementById('preview-body');
                    if (previewBody) previewBody.innerHTML = editableArea.innerHTML;
                } else {
                    // Retry if CKEditor 5 not ready yet
                    setTimeout(initObserver, 500);
                }
            };
            setTimeout(initObserver, 500);
        }
    }

    // Wait for DOM to be ready
    if (document.readyState === 'complete') {
        initPreview();
    } else {
        window.addEventListener('load', initPreview);
    }
})();
