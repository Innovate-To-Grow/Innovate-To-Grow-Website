/**
 * GrapesJS Editor UX enhancements.
 * Phase 5: Autosave, fullscreen, zoom, keyboard shortcuts, save indicator.
 */
var gjsEditorUX = (function() {
    'use strict';

    function apply(editor, csrfToken, entityLabel) {
        // =============================================
        // Autosave with debounce
        // =============================================
        var saveTimer = null;
        var SAVE_DELAY = 3000; // 3 seconds

        function scheduleSave() {
            clearTimeout(saveTimer);
            updateSaveStatus('unsaved');
            saveTimer = setTimeout(function() {
                updateSaveStatus('saving');
                editor.store();
            }, SAVE_DELAY);
        }

        editor.on('component:update', scheduleSave);
        editor.on('component:add', scheduleSave);
        editor.on('component:remove', scheduleSave);
        editor.on('style:change', scheduleSave);

        editor.on('storage:store', function() {
            updateSaveStatus('saved');
        });
        editor.on('storage:error:store', function() {
            updateSaveStatus('error');
        });

        // =============================================
        // Save status indicator
        // =============================================
        var statusBar = document.createElement('div');
        statusBar.id = 'gjs-save-status';
        statusBar.className = 'gjs-save-status';
        statusBar.innerHTML = '<span class="gjs-save-dot"></span> <span class="gjs-save-text">Ready</span>';

        var wrapper = document.getElementById('grapesjs-editor-wrapper');
        if (wrapper) {
            wrapper.insertBefore(statusBar, wrapper.firstChild);
        }

        function updateSaveStatus(state) {
            var dot = statusBar.querySelector('.gjs-save-dot');
            var text = statusBar.querySelector('.gjs-save-text');
            statusBar.className = 'gjs-save-status gjs-save-' + state;

            switch (state) {
                case 'saving':
                    text.textContent = 'Saving...';
                    break;
                case 'saved':
                    var now = new Date();
                    text.textContent = 'Saved at ' + now.toLocaleTimeString();
                    break;
                case 'unsaved':
                    text.textContent = 'Unsaved changes';
                    break;
                case 'error':
                    text.textContent = 'Save failed';
                    break;
                default:
                    text.textContent = 'Ready';
            }
        }

        // =============================================
        // Keyboard shortcuts
        // =============================================
        document.addEventListener('keydown', function(e) {
            // Ctrl+S / Cmd+S: Manual save
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                clearTimeout(saveTimer);
                updateSaveStatus('saving');
                editor.store();
            }

            // Ctrl+D / Cmd+D: Duplicate selected component
            if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
                e.preventDefault();
                var selected = editor.getSelected();
                if (selected) {
                    var parent = selected.parent();
                    if (parent) {
                        var index = parent.components().indexOf(selected);
                        var clone = selected.clone();
                        parent.components().add(clone, { at: index + 1 });
                        editor.select(clone);
                    }
                }
            }

            // Escape: Deselect all
            if (e.key === 'Escape') {
                editor.select(null);
            }
        });

        // =============================================
        // Fullscreen toggle
        // =============================================
        var pnManager = editor.Panels;

        pnManager.addButton('options', {
            id: 'fullscreen',
            className: 'fa fa-expand',
            command: {
                run: function(ed) {
                    var el = document.getElementById('grapesjs-editor-wrapper');
                    if (el) {
                        el.classList.add('gjs-fullscreen');
                        document.body.style.overflow = 'hidden';
                    }
                },
                stop: function(ed) {
                    var el = document.getElementById('grapesjs-editor-wrapper');
                    if (el) {
                        el.classList.remove('gjs-fullscreen');
                        document.body.style.overflow = '';
                    }
                },
            },
            attributes: { title: 'Fullscreen' },
            active: false,
        });

        // =============================================
        // Zoom controls
        // =============================================
        var currentZoom = 100;

        pnManager.addButton('options', {
            id: 'zoom-in',
            className: 'fa fa-search-plus',
            command: function(ed) {
                currentZoom = Math.min(currentZoom + 10, 200);
                ed.Canvas.setZoom(currentZoom);
            },
            attributes: { title: 'Zoom In' },
        });

        pnManager.addButton('options', {
            id: 'zoom-out',
            className: 'fa fa-search-minus',
            command: function(ed) {
                currentZoom = Math.max(currentZoom - 10, 50);
                ed.Canvas.setZoom(currentZoom);
            },
            attributes: { title: 'Zoom Out' },
        });

        pnManager.addButton('options', {
            id: 'zoom-reset',
            className: 'fa fa-crosshairs',
            command: function(ed) {
                currentZoom = 100;
                ed.Canvas.setZoom(100);
            },
            attributes: { title: 'Reset Zoom' },
        });

        // =============================================
        // Grid / outline toggle
        // =============================================
        pnManager.addButton('options', {
            id: 'sw-visibility',
            className: 'fa fa-square-o',
            command: 'sw-visibility',
            attributes: { title: 'Toggle Borders' },
            active: true,
        });
    }

    return { apply: apply };
})();
