(function() {
    'use strict';

    // Component Editor Module
    var ComponentEditor = {
        modal: null,
        editors: {},
        currentRow: null,
        
        init: function() {
            this.injectModal();
            this.bindEvents();
        },

        injectModal: function() {
            var html = `
                <div id="component-editor-modal" class="component-editor-modal">
                    <div class="component-editor-content">
                        <div class="component-editor-header">
                            <h2 id="component-editor-title">Edit Component</h2>
                            <button type="button" class="component-editor-btn btn-cancel" id="component-editor-close-x">×</button>
                        </div>
                        <div class="component-editor-tabs">
                            <div class="component-editor-tab active" data-tab="html">HTML Content</div>
                            <div class="component-editor-tab" data-tab="css">CSS Code</div>
                            <div class="component-editor-tab" data-tab="js">JS Code</div>
                            <div class="component-editor-tab" data-tab="config">Config (JSON)</div>
                        </div>
                        <div class="component-editor-body">
                            <div class="editor-panel active" id="panel-html"><textarea id="editor-html"></textarea></div>
                            <div class="editor-panel" id="panel-css"><textarea id="editor-css"></textarea></div>
                            <div class="editor-panel" id="panel-js"><textarea id="editor-js"></textarea></div>
                            <div class="editor-panel" id="panel-config"><textarea id="editor-config"></textarea></div>
                        </div>
                        <div class="component-editor-footer">
                            <button type="button" class="component-editor-btn btn-cancel" id="component-editor-cancel">Cancel</button>
                            <button type="button" class="component-editor-btn btn-save" id="component-editor-save">Apply Changes</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', html);
            this.modal = document.getElementById('component-editor-modal');
        },

        bindEvents: function() {
            var self = this;

            // Delegate click for edit buttons (since rows can be added dynamically)
            document.addEventListener('click', function(e) {
                if (e.target && e.target.classList.contains('edit-component-btn')) {
                    e.preventDefault();
                    var row = e.target.closest('tr');
                    if (row) {
                        self.open(row);
                    }
                }
            });

            // Modal controls
            document.getElementById('component-editor-close-x').addEventListener('click', function() { self.close(); });
            document.getElementById('component-editor-cancel').addEventListener('click', function() { self.close(); });
            document.getElementById('component-editor-save').addEventListener('click', function() { self.save(); });

            // Tabs
            var tabs = document.querySelectorAll('.component-editor-tab');
            tabs.forEach(function(tab) {
                tab.addEventListener('click', function() {
                    self.switchTab(this.dataset.tab);
                });
            });
        },

        initEditors: function() {
            if (this.editors.html) return; // Already inited

            var config = {
                lineNumbers: true,
                lineWrapping: true,
                indentUnit: 2,
                tabSize: 2,
                theme: 'default'
            };

            this.editors.html = CodeMirror.fromTextArea(document.getElementById('editor-html'), {
                ...config, mode: 'htmlmixed'
            });
            this.editors.css = CodeMirror.fromTextArea(document.getElementById('editor-css'), {
                ...config, mode: 'css'
            });
            this.editors.js = CodeMirror.fromTextArea(document.getElementById('editor-js'), {
                ...config, mode: 'javascript'
            });
            this.editors.config = CodeMirror.fromTextArea(document.getElementById('editor-config'), {
                ...config, mode: 'application/json'
            });

            // Refresh editors when they become visible
            var self = this;
            setTimeout(function() {
                Object.values(self.editors).forEach(function(ed) { ed.refresh(); });
            }, 100);
        },

        open: function(row) {
            this.currentRow = row;
            this.modal.classList.add('active');
            
            // Initialize editors if first time
            this.initEditors();

            // Get values from row inputs
            // Note: inputs might be input[type=hidden] or textarea depending on widget, 
            // but we are using Textarea widget hidden via CSS now.
            var htmlVal = this.getRowValue(row, 'html_content');
            var cssVal = this.getRowValue(row, 'css_code');
            var jsVal = this.getRowValue(row, 'js_code');
            var configVal = this.getRowValue(row, 'config');

            // Set values
            this.editors.html.setValue(htmlVal || '');
            this.editors.css.setValue(cssVal || '');
            this.editors.js.setValue(jsVal || '');
            this.editors.config.setValue(configVal || '{}');

            // Set title
            var nameInput = row.querySelector('input[name$="-name"]');
            var title = nameInput ? nameInput.value : 'Component';
            document.getElementById('component-editor-title').textContent = 'Edit: ' + title;

            // Refresh layout
            var self = this;
            setTimeout(function() {
                Object.values(self.editors).forEach(function(ed) { ed.refresh(); });
            }, 50);
        },

        close: function() {
            this.modal.classList.remove('active');
            this.currentRow = null;
        },

        save: function() {
            if (!this.currentRow) return;

            // Get values from editors
            var htmlVal = this.editors.html.getValue();
            var cssVal = this.editors.css.getValue();
            var jsVal = this.editors.js.getValue();
            var configVal = this.editors.config.getValue();

            // Write back to row inputs
            this.setRowValue(this.currentRow, 'html_content', htmlVal);
            this.setRowValue(this.currentRow, 'css_code', cssVal);
            this.setRowValue(this.currentRow, 'js_code', jsVal);
            this.setRowValue(this.currentRow, 'config', configVal);

            this.close();
        },

        switchTab: function(tabName) {
            // Update tabs UI
            document.querySelectorAll('.component-editor-tab').forEach(function(t) {
                t.classList.remove('active');
                if (t.dataset.tab === tabName) t.classList.add('active');
            });

            // Update panels UI
            document.querySelectorAll('.editor-panel').forEach(function(p) {
                p.classList.remove('active');
            });
            document.getElementById('panel-' + tabName).classList.add('active');

            // Refresh editor
            if (this.editors[tabName]) {
                this.editors[tabName].refresh();
            }
        },

        getRowValue: function(row, fieldName) {
            var input = row.querySelector('textarea[name$="-' + fieldName + '"], input[name$="-' + fieldName + '"]');
            return input ? input.value : '';
        },

        setRowValue: function(row, fieldName, value) {
            var input = row.querySelector('textarea[name$="-' + fieldName + '"], input[name$="-' + fieldName + '"]');
            if (input) {
                input.value = value;
                // Trigger change event for page-live-preview.js
                var event = new Event('input', { bubbles: true });
                input.dispatchEvent(event);
                var changeEvent = new Event('change', { bubbles: true });
                input.dispatchEvent(changeEvent);
            }
        }
    };

    // Initialize on load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() { ComponentEditor.init(); });
    } else {
        ComponentEditor.init();
    }

})();
