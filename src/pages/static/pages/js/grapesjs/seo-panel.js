/**
 * GrapesJS SEO Panel - In-editor SEO fields and score indicator.
 * Phase 8: Meta fields, character counters, SEO score.
 */
var gjsSeoPanel = (function() {
    'use strict';

    // Global SEO data store that the storage manager picks up
    window._gjsSeoData = {};

    window._gjsLoadSeoData = function(result) {
        var fields = ['meta_title', 'meta_description', 'meta_keywords', 'og_image', 'canonical_url', 'meta_robots'];
        fields.forEach(function(f) {
            if (result[f] !== undefined) {
                window._gjsSeoData[f] = result[f] || '';
            }
        });
        // Update form fields if they exist
        setTimeout(function() {
            fields.forEach(function(f) {
                var el = document.getElementById('seo-' + f);
                if (el && window._gjsSeoData[f]) {
                    el.value = window._gjsSeoData[f];
                    updateCounter(el);
                }
            });
            updateSeoScore();
        }, 500);
    };

    function apply(editor, apiBase, objectId, csrfToken) {
        // Add SEO panel button
        editor.Panels.addButton('views', {
            id: 'seo-panel-btn',
            className: 'fa fa-search',
            command: 'show-seo-panel',
            attributes: { title: 'SEO Settings' },
        });

        // SEO panel command
        editor.Commands.add('show-seo-panel', {
            run: function(ed) {
                var container = document.getElementById('gjs-seo-panel');
                if (!container) {
                    container = buildSeoPanel(ed);
                }
                container.style.display = 'block';
            },
            stop: function() {
                var container = document.getElementById('gjs-seo-panel');
                if (container) container.style.display = 'none';
            },
        });
    }

    function buildSeoPanel(editor) {
        var panel = document.createElement('div');
        panel.id = 'gjs-seo-panel';
        panel.className = 'gjs-seo-panel';
        panel.innerHTML =
            '<div class="gjs-seo-header">' +
                '<span class="gjs-seo-score" id="seo-score-badge">--</span>' +
                '<span>SEO Settings</span>' +
            '</div>' +
            '<div class="gjs-seo-body">' +
                buildField('meta_title', 'Meta Title', 'text', 60) +
                buildField('meta_description', 'Meta Description', 'textarea', 160) +
                buildField('meta_keywords', 'Keywords', 'text', 0) +
                buildField('canonical_url', 'Canonical URL', 'text', 0) +
                buildField('og_image', 'OG Image URL', 'text', 0) +
                '<div class="gjs-seo-field">' +
                    '<label>Meta Robots</label>' +
                    '<select id="seo-meta_robots" class="gjs-seo-input">' +
                        '<option value="">Default</option>' +
                        '<option value="index,follow">index, follow</option>' +
                        '<option value="noindex,nofollow">noindex, nofollow</option>' +
                        '<option value="noindex,follow">noindex, follow</option>' +
                        '<option value="index,nofollow">index, nofollow</option>' +
                    '</select>' +
                '</div>' +
            '</div>';

        // Append to the right panels area
        var viewsContainer = document.querySelector('.gjs-pn-views-container');
        if (viewsContainer) {
            viewsContainer.appendChild(panel);
        } else {
            document.getElementById('grapesjs-editor-wrapper').appendChild(panel);
        }

        // Bind events
        panel.querySelectorAll('.gjs-seo-input').forEach(function(input) {
            input.addEventListener('input', function() {
                window._gjsSeoData[input.id.replace('seo-', '')] = input.value;
                updateCounter(input);
                updateSeoScore(editor);
            });
            input.addEventListener('change', function() {
                window._gjsSeoData[input.id.replace('seo-', '')] = input.value;
                updateSeoScore(editor);
            });
        });

        return panel;
    }

    function buildField(name, label, type, maxLen) {
        var tag = type === 'textarea' ? 'textarea' : 'input';
        var maxAttr = maxLen > 0 ? ' data-maxlen="' + maxLen + '"' : '';
        var counter = maxLen > 0 ? '<span class="gjs-seo-counter" id="seo-counter-' + name + '">0/' + maxLen + '</span>' : '';

        return '<div class="gjs-seo-field">' +
            '<label>' + label + counter + '</label>' +
            '<' + tag + ' id="seo-' + name + '" class="gjs-seo-input"' + maxAttr +
            (type === 'textarea' ? ' rows="3"' : ' type="text"') +
            '></' + tag + '>' +
        '</div>';
    }

    function updateCounter(input) {
        var maxLen = parseInt(input.getAttribute('data-maxlen'));
        if (!maxLen) return;
        var name = input.id.replace('seo-', '');
        var counter = document.getElementById('seo-counter-' + name);
        if (counter) {
            var len = (input.value || '').length;
            counter.textContent = len + '/' + maxLen;
            counter.className = 'gjs-seo-counter' + (len > maxLen ? ' over' : len > 0 ? ' ok' : '');
        }
    }

    function updateSeoScore(editor) {
        var score = 0;
        var total = 5;
        var d = window._gjsSeoData;

        // Check meta title
        if (d.meta_title && d.meta_title.length > 0 && d.meta_title.length <= 60) score++;
        // Check meta description
        if (d.meta_description && d.meta_description.length > 0 && d.meta_description.length <= 160) score++;
        // Check keywords
        if (d.meta_keywords && d.meta_keywords.length > 0) score++;
        // Check H1 in editor
        if (editor) {
            var html = editor.getHtml();
            if (html && html.match(/<h1[\s>]/i)) score++;
        } else {
            score++; // Give benefit of doubt if editor not available
        }
        // Check OG image
        if (d.og_image && d.og_image.length > 0) score++;

        var badge = document.getElementById('seo-score-badge');
        if (badge) {
            var pct = Math.round((score / total) * 100);
            badge.textContent = pct + '%';
            badge.className = 'gjs-seo-score' +
                (pct >= 80 ? ' good' : pct >= 50 ? ' ok' : ' poor');
        }
    }

    return { apply: apply };
})();
