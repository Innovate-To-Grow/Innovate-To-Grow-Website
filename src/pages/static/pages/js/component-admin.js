/**
 * Component Admin Integration
 * Initializes Quill editor for PageComponent and handles popup window preview functionality
 */

(function() {
    'use strict';

    let quill = null;
    let popupWindows = [];

    // Quill toolbar configuration with image alignment
    const toolbarOptions = {
        container: [
            [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ 'color': [] }, { 'background': [] }],
            [{ 'align': [] }],
            [{ 'list': 'ordered'}, { 'list': 'bullet' }],
            [{ 'indent': '-1'}, { 'indent': '+1' }],
            ['blockquote', 'code-block'],
            ['link', 'image', 'video'],
            // Image alignment buttons
            ['image-left', 'image-center', 'image-right'],
            ['clean']
        ],
        handlers: {
            'image-left': function() { alignSelectedImage('left'); },
            'image-center': function() { alignSelectedImage('center'); },
            'image-right': function() { alignSelectedImage('right'); }
        }
    };

    // Track currently selected image
    let selectedImage = null;

    /**
     * Align the selected image
     */
    function alignSelectedImage(alignment) {
        if (!selectedImage) {
            alert('Please click to select an image first');
            return;
        }

        // Remove all alignment classes
        selectedImage.classList.remove('align-left', 'align-center', 'align-right');
        selectedImage.style.float = '';
        selectedImage.style.display = '';
        selectedImage.style.marginLeft = '';
        selectedImage.style.marginRight = '';

        // Apply new alignment
        switch(alignment) {
            case 'left':
                selectedImage.classList.add('align-left');
                selectedImage.style.float = 'left';
                selectedImage.style.marginRight = '15px';
                selectedImage.style.marginBottom = '10px';
                break;
            case 'right':
                selectedImage.classList.add('align-right');
                selectedImage.style.float = 'right';
                selectedImage.style.marginLeft = '15px';
                selectedImage.style.marginBottom = '10px';
                break;
            case 'center':
            default:
                selectedImage.classList.add('align-center');
                selectedImage.style.display = 'block';
                selectedImage.style.marginLeft = 'auto';
                selectedImage.style.marginRight = 'auto';
                break;
        }

        // Trigger content update
        syncToTextarea();
        updatePopupPreviews();
    }

    /**
     * Setup image selection handling
     */
    function setupImageSelection() {
        if (!quill) return;

        quill.root.addEventListener('click', function(e) {
            // Deselect previous image
            if (selectedImage) {
                selectedImage.classList.remove('selected');
            }

            // Check if clicked on an image
            if (e.target.tagName === 'IMG') {
                selectedImage = e.target;
                selectedImage.classList.add('selected');
            } else {
                selectedImage = null;
            }
        });
    }

    /**
     * Add custom toolbar button icons
     */
    function setupToolbarIcons() {
        // Wait for toolbar to be created
        setTimeout(function() {
            const toolbar = document.querySelector('.ql-toolbar');
            if (!toolbar) return;

            // Style the image alignment buttons
            const leftBtn = toolbar.querySelector('.ql-image-left');
            const centerBtn = toolbar.querySelector('.ql-image-center');
            const rightBtn = toolbar.querySelector('.ql-image-right');

            if (leftBtn) {
                leftBtn.innerHTML = '<svg viewBox="0 0 18 18"><rect x="1" y="3" width="6" height="6" fill="currentColor"/><line x1="9" y1="4" x2="17" y2="4"/><line x1="9" y1="6" x2="17" y2="6"/><line x1="9" y1="8" x2="17" y2="8"/><line x1="1" y1="11" x2="17" y2="11"/><line x1="1" y1="13" x2="17" y2="13"/><line x1="1" y1="15" x2="10" y2="15"/></svg>';
                leftBtn.title = 'Align image left (text wraps right)';
            }
            if (centerBtn) {
                centerBtn.innerHTML = '<svg viewBox="0 0 18 18"><rect x="4" y="3" width="10" height="7" fill="currentColor"/><line x1="1" y1="12" x2="17" y2="12"/><line x1="3" y1="14" x2="15" y2="14"/><line x1="5" y1="16" x2="13" y2="16"/></svg>';
                centerBtn.title = 'Center image';
            }
            if (rightBtn) {
                rightBtn.innerHTML = '<svg viewBox="0 0 18 18"><rect x="11" y="3" width="6" height="6" fill="currentColor"/><line x1="1" y1="4" x2="9" y2="4"/><line x1="1" y1="6" x2="9" y2="6"/><line x1="1" y1="8" x2="9" y2="8"/><line x1="1" y1="11" x2="17" y2="11"/><line x1="1" y1="13" x2="17" y2="13"/><line x1="8" y1="15" x2="17" y2="15"/></svg>';
                rightBtn.title = 'Align image right (text wraps left)';
            }
        }, 100);
    }

    /**
     * Initialize the Quill editor for html_content field
     */
    function initQuillEditor() {
        const editorContainer = document.getElementById('quill-editor');
        const textarea = document.getElementById('id_html_content');
        
        if (!editorContainer || !textarea) {
            console.log('Quill editor container or textarea not found');
            return;
        }

        // Check if ImageResize module is available
        const modules = {
            toolbar: toolbarOptions
        };

        // Add ImageResize module if available
        if (window.ImageResize) {
            Quill.register('modules/imageResize', window.ImageResize.default || window.ImageResize);
            modules.imageResize = {
                displayStyles: {
                    backgroundColor: 'black',
                    border: 'none',
                    color: 'white'
                },
                modules: ['Resize', 'DisplaySize']
            };
        }

        // Initialize Quill
        quill = new Quill('#quill-editor', {
            theme: 'snow',
            modules: modules,
            placeholder: 'Start writing your HTML content here...'
        });

        // Load initial content from textarea
        if (textarea.value) {
            quill.root.innerHTML = textarea.value;
        }

        // Sync content to textarea on change
        quill.on('text-change', function() {
            syncToTextarea();
            updatePopupPreviews();
        });

        // Handle image paste/drop
        quill.root.addEventListener('paste', handleImagePaste);
        quill.root.addEventListener('drop', handleImageDrop);

        // Setup image selection and toolbar icons
        setupImageSelection();
        setupToolbarIcons();

        console.log('Component Quill editor initialized');
    }

    /**
     * Sync Quill content to hidden textarea
     */
    function syncToTextarea() {
        const textarea = document.getElementById('id_html_content');
        if (textarea && quill) {
            textarea.value = quill.root.innerHTML;
            // Trigger change event for form validation
            const event = new Event('change', { bubbles: true });
            textarea.dispatchEvent(event);
        }
    }

    /**
     * Get current component data for preview
     */
    function getComponentData() {
        const htmlContent = quill ? quill.root.innerHTML : (document.getElementById('id_html_content')?.value || '');
        const cssCode = document.getElementById('id_css_code')?.value || '';
        const jsCode = document.getElementById('id_js_code')?.value || '';
        
        return {
            html: htmlContent,
            css: cssCode,
            js: jsCode
        };
    }

    /**
     * Update all popup preview windows
     */
    function updatePopupPreviews() {
        const data = getComponentData();

        // Update popup windows via postMessage
        popupWindows = popupWindows.filter(win => !win.closed);
        popupWindows.forEach(win => {
            try {
                win.postMessage({
                    type: 'component-preview-update',
                    content: data.html,
                    css: data.css,
                    js: data.js
                }, '*');
            } catch (e) {
                console.error('Failed to send message to popup:', e);
            }
        });
    }

    /**
     * Open popup preview window
     */
    function openPopupPreview() {
        const width = 1000;
        const height = 700;
        const left = (screen.width - width) / 2;
        const top = (screen.height - height) / 2;
        
        const popup = window.open(
            '/admin/component-preview/',
            'componentPreview_' + Date.now(),
            `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
        );

        if (popup) {
            popupWindows.push(popup);
            
            // Send initial content after popup loads
            popup.addEventListener('load', function() {
                setTimeout(updatePopupPreviews, 300);
            });

            // Clean up reference when closed
            const checkClosed = setInterval(() => {
                if (popup.closed) {
                    clearInterval(checkClosed);
                    popupWindows = popupWindows.filter(w => w !== popup);
                }
            }, 1000);
        } else {
            alert('Popup was blocked. Please allow popups for this site.');
        }
    }

    /**
     * Handle image paste
     */
    function handleImagePaste(e) {
        const items = e.clipboardData?.items;
        if (!items) return;

        for (const item of items) {
            if (item.type.startsWith('image/')) {
                e.preventDefault();
                const file = item.getAsFile();
                if (file) {
                    insertImageAsBase64(file);
                }
                break;
            }
        }
    }

    /**
     * Handle image drop
     */
    function handleImageDrop(e) {
        const files = e.dataTransfer?.files;
        if (!files || files.length === 0) return;

        for (const file of files) {
            if (file.type.startsWith('image/')) {
                e.preventDefault();
                insertImageAsBase64(file);
            }
        }
    }

    /**
     * Insert image as base64
     */
    function insertImageAsBase64(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const range = quill.getSelection(true);
            quill.insertEmbed(range.index, 'image', e.target.result);
            quill.setSelection(range.index + 1);
        };
        reader.readAsDataURL(file);
    }

    /**
     * Setup popup preview button
     */
    function setupPopupButton() {
        const btn = document.getElementById('component-preview-btn');
        if (btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                openPopupPreview();
            });
        }
    }

    /**
     * Setup JS code field change listener
     */
    function setupJsCodeListener() {
        const jsCodeField = document.getElementById('id_js_code');
        if (jsCodeField) {
            jsCodeField.addEventListener('input', function() {
                updatePopupPreviews();
            });
        }
    }

    /**
     * Setup CSS code field change listener
     */
    function setupCssCodeListener() {
        const cssCodeField = document.getElementById('id_css_code');
        if (cssCodeField) {
            cssCodeField.addEventListener('input', function() {
                updatePopupPreviews();
            });
        }
    }

    /**
     * Initialize everything when DOM is ready
     */
    function init() {
        initQuillEditor();
        setupPopupButton();
        setupJsCodeListener();
        setupCssCodeListener();
    }

    // Wait for DOM to be ready
    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }

    // Expose for debugging
    window.componentAdmin = {
        getQuill: () => quill,
        updatePopupPreviews,
        openPopupPreview,
        getComponentData
    };
})();

