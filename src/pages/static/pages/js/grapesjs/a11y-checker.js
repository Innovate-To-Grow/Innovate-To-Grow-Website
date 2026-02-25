/**
 * GrapesJS Accessibility Checker - In-editor WCAG audit.
 * Phase 9: Scans canvas HTML for common accessibility issues.
 */
var gjsA11yChecker = (function() {
    'use strict';

    function apply(editor) {
        // Add Accessibility button to the options panel
        editor.Panels.addButton('options', {
            id: 'a11y-checker-btn',
            className: 'fa fa-universal-access',
            command: 'run-a11y-check',
            attributes: { title: 'Accessibility Check' },
        });

        // A11y check command
        editor.Commands.add('run-a11y-check', {
            run: function(ed) {
                var issues = runChecks(ed);
                showResultsPanel(ed, issues);
            },
        });
    }

    function runChecks(editor) {
        var html = editor.getHtml() || '';
        var issues = [];

        // Parse HTML into a temporary DOM
        var parser = new DOMParser();
        var doc = parser.parseFromString(
            '<html><body>' + html + '</body></html>',
            'text/html'
        );
        var body = doc.body;

        // 1. Images missing alt attribute
        var images = body.querySelectorAll('img');
        images.forEach(function(img) {
            if (!img.hasAttribute('alt')) {
                issues.push({
                    severity: 'error',
                    rule: 'img-alt',
                    message: 'Image missing alt attribute',
                    element: describeElement(img),
                    selector: buildSelector(img),
                });
            } else if (img.getAttribute('alt').trim() === '') {
                issues.push({
                    severity: 'warning',
                    rule: 'img-alt-empty',
                    message: 'Image has empty alt text (only acceptable for decorative images)',
                    element: describeElement(img),
                    selector: buildSelector(img),
                });
            }
        });

        // 2. Links with no accessible text
        var links = body.querySelectorAll('a');
        links.forEach(function(a) {
            var text = (a.textContent || '').trim();
            var ariaLabel = a.getAttribute('aria-label');
            var title = a.getAttribute('title');
            var imgAlt = a.querySelector('img[alt]');
            if (!text && !ariaLabel && !title && !imgAlt) {
                issues.push({
                    severity: 'error',
                    rule: 'link-text',
                    message: 'Link has no accessible text content',
                    element: describeElement(a),
                    selector: buildSelector(a),
                });
            }
        });

        // 3. Missing H1 or skipped heading levels
        var headings = body.querySelectorAll('h1, h2, h3, h4, h5, h6');
        var headingLevels = [];
        headings.forEach(function(h) {
            headingLevels.push(parseInt(h.tagName.charAt(1)));
        });

        if (headingLevels.length > 0 && headingLevels.indexOf(1) === -1) {
            issues.push({
                severity: 'warning',
                rule: 'heading-h1',
                message: 'Page has headings but no H1 element',
                element: 'Document',
                selector: '',
            });
        }

        // Check for skipped heading levels
        for (var i = 1; i < headingLevels.length; i++) {
            if (headingLevels[i] > headingLevels[i - 1] + 1) {
                issues.push({
                    severity: 'warning',
                    rule: 'heading-order',
                    message: 'Heading level skipped: H' + headingLevels[i - 1] + ' followed by H' + headingLevels[i],
                    element: 'Document structure',
                    selector: 'h' + headingLevels[i],
                });
            }
        }

        // 4. Form inputs missing labels
        var inputs = body.querySelectorAll('input, textarea, select');
        inputs.forEach(function(input) {
            if (input.type === 'hidden' || input.type === 'submit' || input.type === 'button') return;
            var id = input.getAttribute('id');
            var ariaLabel = input.getAttribute('aria-label');
            var ariaLabelledby = input.getAttribute('aria-labelledby');
            var hasLabel = false;

            if (id) {
                hasLabel = body.querySelector('label[for="' + id + '"]') !== null;
            }
            if (!hasLabel) {
                // Check if wrapped in a label
                hasLabel = input.closest('label') !== null;
            }

            if (!hasLabel && !ariaLabel && !ariaLabelledby) {
                issues.push({
                    severity: 'error',
                    rule: 'form-label',
                    message: 'Form input missing associated label',
                    element: describeElement(input),
                    selector: buildSelector(input),
                });
            }
        });

        // 5. Empty buttons
        var buttons = body.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]');
        buttons.forEach(function(btn) {
            var text = (btn.textContent || '').trim();
            var ariaLabel = btn.getAttribute('aria-label');
            var title = btn.getAttribute('title');
            var value = btn.getAttribute('value');
            if (!text && !ariaLabel && !title && !value) {
                issues.push({
                    severity: 'error',
                    rule: 'button-text',
                    message: 'Button has no accessible text',
                    element: describeElement(btn),
                    selector: buildSelector(btn),
                });
            }
        });

        // 6. Tables missing headers
        var tables = body.querySelectorAll('table');
        tables.forEach(function(table) {
            var th = table.querySelectorAll('th');
            if (th.length === 0) {
                issues.push({
                    severity: 'warning',
                    rule: 'table-headers',
                    message: 'Table missing header cells (th elements)',
                    element: describeElement(table),
                    selector: buildSelector(table),
                });
            }
        });

        // 7. Missing lang attribute — typically set on <html> which we can't
        // check from canvas HTML, so we skip this for in-editor checks.

        // 8. Auto-playing media
        var autoplayMedia = body.querySelectorAll('video[autoplay], audio[autoplay]');
        autoplayMedia.forEach(function(media) {
            issues.push({
                severity: 'warning',
                rule: 'no-autoplay',
                message: 'Media element has autoplay — may cause issues for users with cognitive disabilities',
                element: describeElement(media),
                selector: buildSelector(media),
            });
        });

        // 9. Check for tabindex > 0
        var tabindexEls = body.querySelectorAll('[tabindex]');
        tabindexEls.forEach(function(el) {
            var val = parseInt(el.getAttribute('tabindex'));
            if (val > 0) {
                issues.push({
                    severity: 'warning',
                    rule: 'tabindex-positive',
                    message: 'Positive tabindex (' + val + ') disrupts natural tab order',
                    element: describeElement(el),
                    selector: buildSelector(el),
                });
            }
        });

        return issues;
    }

    function describeElement(el) {
        var tag = el.tagName.toLowerCase();
        var id = el.getAttribute('id');
        var cls = el.getAttribute('class');
        var desc = '<' + tag;
        if (id) desc += '#' + id;
        if (cls) desc += '.' + cls.split(' ')[0];
        desc += '>';
        // Truncate
        if (desc.length > 60) desc = desc.substring(0, 57) + '...';
        return desc;
    }

    function buildSelector(el) {
        var tag = el.tagName.toLowerCase();
        var id = el.getAttribute('id');
        if (id) return tag + '#' + id;
        var cls = el.getAttribute('class');
        if (cls) return tag + '.' + cls.trim().split(/\s+/).join('.');
        return tag;
    }

    function showResultsPanel(editor, issues) {
        // Remove existing panel
        var existing = document.getElementById('gjs-a11y-panel');
        if (existing) existing.remove();

        var panel = document.createElement('div');
        panel.id = 'gjs-a11y-panel';
        panel.className = 'gjs-a11y-panel';

        var errors = issues.filter(function(i) { return i.severity === 'error'; });
        var warnings = issues.filter(function(i) { return i.severity === 'warning'; });

        var headerHtml = '<div class="gjs-a11y-header">' +
            '<span class="gjs-a11y-title">Accessibility Report</span>' +
            '<button class="gjs-a11y-close" id="a11y-close-btn">&times;</button>' +
            '</div>' +
            '<div class="gjs-a11y-summary">';

        if (issues.length === 0) {
            headerHtml += '<span class="gjs-a11y-badge good">No issues found</span>';
        } else {
            if (errors.length > 0) {
                headerHtml += '<span class="gjs-a11y-badge error">' + errors.length + ' error' + (errors.length > 1 ? 's' : '') + '</span> ';
            }
            if (warnings.length > 0) {
                headerHtml += '<span class="gjs-a11y-badge warning">' + warnings.length + ' warning' + (warnings.length > 1 ? 's' : '') + '</span>';
            }
        }
        headerHtml += '</div>';

        var bodyHtml = '<div class="gjs-a11y-body">';
        issues.forEach(function(issue, idx) {
            bodyHtml += '<div class="gjs-a11y-issue ' + issue.severity + '" data-selector="' + (issue.selector || '') + '" data-idx="' + idx + '">' +
                '<div class="gjs-a11y-issue-icon">' + (issue.severity === 'error' ? '&#10007;' : '&#9888;') + '</div>' +
                '<div class="gjs-a11y-issue-content">' +
                    '<div class="gjs-a11y-issue-msg">' + issue.message + '</div>' +
                    '<div class="gjs-a11y-issue-el">' + escapeHtml(issue.element) + '</div>' +
                '</div>' +
            '</div>';
        });
        bodyHtml += '</div>';

        var footerHtml = '<div class="gjs-a11y-footer">' +
            '<button class="gjs-a11y-recheck" id="a11y-recheck-btn">Re-check</button>' +
            '</div>';

        panel.innerHTML = headerHtml + bodyHtml + footerHtml;

        // Append to views container or editor wrapper
        var viewsContainer = document.querySelector('.gjs-pn-views-container');
        if (viewsContainer) {
            viewsContainer.appendChild(panel);
        } else {
            document.getElementById('grapesjs-editor-wrapper').appendChild(panel);
        }

        // Bind events
        document.getElementById('a11y-close-btn').addEventListener('click', function() {
            panel.remove();
        });

        document.getElementById('a11y-recheck-btn').addEventListener('click', function() {
            var newIssues = runChecks(editor);
            panel.remove();
            showResultsPanel(editor, newIssues);
        });

        // Click on issue to select component
        panel.querySelectorAll('.gjs-a11y-issue').forEach(function(issueEl) {
            issueEl.addEventListener('click', function() {
                var selector = this.getAttribute('data-selector');
                if (!selector) return;
                try {
                    var wrapper = editor.getWrapper();
                    var found = wrapper.find(selector);
                    if (found && found.length > 0) {
                        editor.select(found[0]);
                        // Scroll into view
                        var el = found[0].getEl();
                        if (el && el.scrollIntoView) {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    }
                } catch (e) {
                    console.warn('Could not select element:', selector, e);
                }
            });
        });

        // Update the button badge
        updateBadge(issues.length);
    }

    function updateBadge(count) {
        var btn = document.querySelector('.fa-universal-access');
        if (!btn) return;
        // Remove existing badge
        var existingBadge = btn.querySelector('.gjs-a11y-count');
        if (existingBadge) existingBadge.remove();

        if (count > 0) {
            var badge = document.createElement('span');
            badge.className = 'gjs-a11y-count';
            badge.textContent = count;
            btn.style.position = 'relative';
            btn.appendChild(badge);
        }
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    return { apply: apply };
})();
