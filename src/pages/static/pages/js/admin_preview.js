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

        // Sync CKEditor Body
        if (typeof CKEDITOR !== 'undefined') {
            CKEDITOR.on('instanceReady', function(evt) {
                if (evt.editor.name === 'id_body') {
                    const updateBody = () => {
                        const previewBody = doc.getElementById('preview-body');
                        if (previewBody) previewBody.innerHTML = evt.editor.getData();
                    };
                    evt.editor.on('change', updateBody);
                    // Initial update
                    setTimeout(updateBody, 500);
                }
            });
        }
    }

    // Wait for DOM to be ready
    if (document.readyState === 'complete') {
        initPreview();
    } else {
        window.addEventListener('load', initPreview);
    }
})();
