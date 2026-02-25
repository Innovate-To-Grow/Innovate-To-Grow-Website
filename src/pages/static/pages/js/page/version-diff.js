/**
 * Version Comparison (Visual Diff) for Page/HomePage admin.
 * Phase 10: Compare two versions side by side in a split-pane modal.
 */
(function() {
    'use strict';

    function init() {
        // Add "Compare" buttons to version table rows
        var versionRows = document.querySelectorAll('.version-table tbody tr');
        if (!versionRows.length) return;

        versionRows.forEach(function(row) {
            var actionCell = row.querySelector('td:last-child');
            if (!actionCell) return;

            var rollbackBtn = actionCell.querySelector('.btn-rollback');
            if (!rollbackBtn) return;

            var versionNum = rollbackBtn.getAttribute('data-submit-value');
            if (!versionNum) return;

            var compareBtn = document.createElement('button');
            compareBtn.type = 'button';
            compareBtn.className = 'btn-compare';
            compareBtn.textContent = 'Compare';
            compareBtn.setAttribute('data-version', versionNum);
            compareBtn.addEventListener('click', function() {
                openCompareModal(versionNum);
            });

            actionCell.insertBefore(compareBtn, rollbackBtn);
        });

        // Create modal HTML
        createCompareModal();
    }

    function createCompareModal() {
        var modal = document.createElement('div');
        modal.id = 'version-compare-overlay';
        modal.className = 'version-compare-overlay';
        modal.innerHTML =
            '<div class="version-compare-modal">' +
                '<div class="version-compare-header">' +
                    '<span class="version-compare-title" id="version-compare-title">Version Comparison</span>' +
                    '<button class="version-compare-close" id="version-compare-close">&times;</button>' +
                '</div>' +
                '<div class="version-compare-body">' +
                    '<div class="version-compare-pane">' +
                        '<div class="version-pane-label" id="version-pane-left-label">Selected Version</div>' +
                        '<iframe class="version-compare-iframe" id="version-iframe-left"></iframe>' +
                    '</div>' +
                    '<div class="version-compare-divider"></div>' +
                    '<div class="version-compare-pane">' +
                        '<div class="version-pane-label" id="version-pane-right-label">Current Version</div>' +
                        '<iframe class="version-compare-iframe" id="version-iframe-right"></iframe>' +
                    '</div>' +
                '</div>' +
                '<div class="version-compare-footer">' +
                    '<button class="version-compare-btn" id="version-compare-restore">Restore This Version</button>' +
                    '<button class="version-compare-btn secondary" id="version-compare-cancel">Close</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(modal);

        // Bind close events
        document.getElementById('version-compare-close').addEventListener('click', closeCompareModal);
        document.getElementById('version-compare-cancel').addEventListener('click', closeCompareModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeCompareModal();
        });
    }

    function openCompareModal(versionNum) {
        var overlay = document.getElementById('version-compare-overlay');
        if (!overlay) return;

        // Get object ID and CSRF token from the page
        var previewBtn = document.getElementById('popup-preview-btn');
        var objectId = previewBtn ? previewBtn.getAttribute('data-object-id') : '';

        // Determine the API base from the current URL
        var currentPath = window.location.pathname;
        var apiBase = '';
        if (currentPath.indexOf('/homepage/') !== -1) {
            apiBase = '/pages/manage/home/';
        } else {
            apiBase = '/pages/manage/';
        }

        var title = document.getElementById('version-compare-title');
        title.textContent = 'Comparing Version ' + versionNum + ' with Current';

        var leftLabel = document.getElementById('version-pane-left-label');
        leftLabel.textContent = 'Version ' + versionNum;

        var rightLabel = document.getElementById('version-pane-right-label');
        rightLabel.textContent = 'Current Version';

        // Show modal
        overlay.classList.add('active');

        // Fetch version data
        var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        var csrfValue = csrfToken ? csrfToken.value : '';

        // Load current page data
        fetch(apiBase + objectId + '/', {
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfValue },
        })
        .then(function(res) { return res.json(); })
        .then(function(currentData) {
            // Render current version in right iframe
            renderInIframe('version-iframe-right', currentData.html || '', currentData.css || '');
        })
        .catch(function(err) {
            console.error('Failed to load current version:', err);
            renderInIframe('version-iframe-right', '<p style="color:red;">Failed to load current version</p>', '');
        });

        // Fetch the old version data using the Django admin's version API
        // The version data is embedded in the admin change form context
        // We'll use a simulated approach: fetch from the admin change history
        fetchVersionData(objectId, versionNum, apiBase, csrfValue)
            .then(function(versionData) {
                renderInIframe('version-iframe-left', versionData.html || '', versionData.css || '');
            })
            .catch(function(err) {
                console.error('Failed to load version ' + versionNum + ':', err);
                renderInIframe('version-iframe-left', '<p style="color:red;">Failed to load version data</p>', '');
            });

        // Bind restore button
        var restoreBtn = document.getElementById('version-compare-restore');
        restoreBtn.onclick = function() {
            if (confirm('Restore to version ' + versionNum + '? Current state will be saved first.')) {
                // Submit the rollback form
                var form = document.querySelector('#changelist-form, form[method="post"]');
                if (form) {
                    var hidden = document.createElement('input');
                    hidden.type = 'hidden';
                    hidden.name = '_rollback';
                    hidden.value = versionNum;
                    form.appendChild(hidden);
                    form.submit();
                }
            }
        };
    }

    function fetchVersionData(objectId, versionNum, apiBase, csrfToken) {
        // Try to fetch version data from the version endpoint
        // The ProjectControlModel stores versions as JSON, accessible via the admin
        // We'll attempt to get it from the page manage API with a version query param
        return fetch(apiBase + objectId + '/?version=' + versionNum, {
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken },
        })
        .then(function(res) {
            if (!res.ok) {
                // Fallback: version endpoint not implemented, show message
                return { html: '<div style="padding:40px;text-align:center;color:#666;">' +
                    '<h3>Version ' + versionNum + '</h3>' +
                    '<p>Direct version data loading requires the version API endpoint.</p>' +
                    '<p>Use the Rollback button to restore this version.</p>' +
                    '</div>', css: '' };
            }
            return res.json();
        });
    }

    function renderInIframe(iframeId, html, css) {
        var iframe = document.getElementById(iframeId);
        if (!iframe) return;

        var doc = iframe.contentDocument || iframe.contentWindow.document;
        doc.open();
        doc.write(
            '<!DOCTYPE html><html><head>' +
            '<meta charset="utf-8">' +
            '<meta name="viewport" content="width=device-width, initial-scale=1">' +
            '<style>' +
            'body { margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }' +
            (css || '') +
            '</style>' +
            '</head><body>' +
            (html || '<p style="color:#999;">No content</p>') +
            '</body></html>'
        );
        doc.close();
    }

    function closeCompareModal() {
        var overlay = document.getElementById('version-compare-overlay');
        if (overlay) overlay.classList.remove('active');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
