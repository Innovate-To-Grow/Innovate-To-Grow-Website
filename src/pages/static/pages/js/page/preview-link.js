/**
 * Shareable Preview Link Generator - Admin UI.
 * Phase 12: Generate, copy, and manage preview links for unpublished pages.
 */
(function() {
    'use strict';

    function init() {
        // Only initialize if we have the preview button (indicates we're on a change form)
        var previewBtn = document.getElementById('popup-preview-btn');
        if (!previewBtn) return;

        var objectId = previewBtn.getAttribute('data-object-id');
        if (!objectId) return;

        // Determine content type from URL
        var currentPath = window.location.pathname;
        var contentType = currentPath.indexOf('/homepage/') !== -1 ? 'homepage' : 'page';

        // Add "Share Preview" button next to "Open Live Preview"
        addShareButton(objectId, contentType);
    }

    function addShareButton(objectId, contentType) {
        var previewBtn = document.getElementById('popup-preview-btn');
        if (!previewBtn) return;

        var li = document.createElement('li');
        li.className = 'border border-base-200 max-lg:-mt-px max-lg:first:rounded-t-default max-lg:last:rounded-b-default min-lg:-ml-px min-lg:first:rounded-l-default min-lg:last:rounded-r-default';
        li.innerHTML = '<a href="#" id="share-preview-btn" class="cursor-pointer flex grow items-center gap-2 px-3 py-2 text-left whitespace-nowrap">' +
            '<span class="material-symbols-outlined">link</span>' +
            'Share Preview Link' +
            '</a>';

        var parentLi = previewBtn.closest('li');
        if (parentLi && parentLi.parentNode) {
            parentLi.parentNode.insertBefore(li, parentLi.nextSibling);
        }

        document.getElementById('share-preview-btn').addEventListener('click', function(e) {
            e.preventDefault();
            openShareModal(objectId, contentType);
        });

        // Create modal
        createShareModal();
    }

    function createShareModal() {
        var modal = document.createElement('div');
        modal.id = 'share-preview-overlay';
        modal.className = 'share-preview-overlay';
        modal.innerHTML =
            '<div class="share-preview-modal">' +
                '<div class="share-preview-header">' +
                    '<span class="share-preview-title">Shareable Preview Link</span>' +
                    '<button class="share-preview-close" id="share-preview-close">&times;</button>' +
                '</div>' +
                '<div class="share-preview-body">' +
                    '<div class="share-preview-generate">' +
                        '<div class="share-preview-field">' +
                            '<label>Expiry</label>' +
                            '<select id="share-preview-expiry">' +
                                '<option value="24">24 hours</option>' +
                                '<option value="72">3 days</option>' +
                                '<option value="168" selected>7 days</option>' +
                                '<option value="720">30 days</option>' +
                            '</select>' +
                        '</div>' +
                        '<div class="share-preview-field">' +
                            '<label>Note (optional)</label>' +
                            '<input type="text" id="share-preview-note" placeholder="e.g., For client review">' +
                        '</div>' +
                        '<button class="share-preview-btn primary" id="share-preview-generate-btn">Generate Link</button>' +
                    '</div>' +
                    '<div class="share-preview-result" id="share-preview-result" style="display:none;">' +
                        '<div class="share-preview-url-group">' +
                            '<input type="text" id="share-preview-url" readonly>' +
                            '<button class="share-preview-btn" id="share-preview-copy-btn">Copy</button>' +
                        '</div>' +
                        '<div class="share-preview-info" id="share-preview-info"></div>' +
                    '</div>' +
                    '<div class="share-preview-divider"></div>' +
                    '<div class="share-preview-existing">' +
                        '<h4>Active Preview Links</h4>' +
                        '<div id="share-preview-list" class="share-preview-list">' +
                            '<div class="share-preview-loading">Loading...</div>' +
                        '</div>' +
                    '</div>' +
                '</div>' +
            '</div>';

        document.body.appendChild(modal);

        // Close events
        document.getElementById('share-preview-close').addEventListener('click', closeShareModal);
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeShareModal();
        });
    }

    function openShareModal(objectId, contentType) {
        var overlay = document.getElementById('share-preview-overlay');
        if (!overlay) return;

        overlay.classList.add('active');

        var csrfToken = getCSRFToken();

        // Bind generate button
        var generateBtn = document.getElementById('share-preview-generate-btn');
        generateBtn.onclick = function() {
            var expiry = document.getElementById('share-preview-expiry').value;
            var note = document.getElementById('share-preview-note').value;
            generatePreviewLink(objectId, contentType, expiry, note, csrfToken);
        };

        // Bind copy button
        document.getElementById('share-preview-copy-btn').onclick = function() {
            var urlInput = document.getElementById('share-preview-url');
            urlInput.select();
            document.execCommand('copy');
            this.textContent = 'Copied!';
            var btn = this;
            setTimeout(function() { btn.textContent = 'Copy'; }, 2000);
        };

        // Load existing links
        loadExistingLinks(objectId, contentType, csrfToken);
    }

    function generatePreviewLink(objectId, contentType, expiryHours, note, csrfToken) {
        var generateBtn = document.getElementById('share-preview-generate-btn');
        generateBtn.textContent = 'Generating...';
        generateBtn.disabled = true;

        fetch('/pages/preview/tokens/create/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                object_id: objectId,
                content_type: contentType,
                expires_in_hours: parseInt(expiryHours),
                note: note,
            }),
        })
        .then(function(res) {
            if (!res.ok) throw new Error('Failed to generate preview link');
            return res.json();
        })
        .then(function(data) {
            // Show result
            var resultDiv = document.getElementById('share-preview-result');
            resultDiv.style.display = 'block';

            var urlInput = document.getElementById('share-preview-url');
            urlInput.value = data.preview_url;

            var infoDiv = document.getElementById('share-preview-info');
            infoDiv.textContent = 'Expires: ' + new Date(data.expires_at).toLocaleString();

            generateBtn.textContent = 'Generate Link';
            generateBtn.disabled = false;

            // Refresh existing links list
            loadExistingLinks(objectId, contentType === 'homepage' ? 'homepage' : 'page', csrfToken);
        })
        .catch(function(err) {
            console.error('Error generating preview link:', err);
            generateBtn.textContent = 'Generate Link';
            generateBtn.disabled = false;
            if (window.adminToast) {
                window.adminToast('Failed to generate preview link: ' + err.message, 'error');
            }
        });
    }

    function loadExistingLinks(objectId, contentType, csrfToken) {
        var listDiv = document.getElementById('share-preview-list');
        listDiv.innerHTML = '<div class="share-preview-loading">Loading...</div>';

        fetch('/pages/preview/tokens/?object_id=' + objectId + '&content_type=' + contentType, {
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken },
        })
        .then(function(res) {
            if (!res.ok) throw new Error('Failed to load links');
            return res.json();
        })
        .then(function(data) {
            var tokens = data.tokens || [];
            if (tokens.length === 0) {
                listDiv.innerHTML = '<div class="share-preview-empty">No active preview links</div>';
                return;
            }

            var html = '';
            tokens.forEach(function(token) {
                html += '<div class="share-preview-item">' +
                    '<div class="share-preview-item-info">' +
                        '<span class="share-preview-item-note">' + (token.note || 'Preview link') + '</span>' +
                        '<span class="share-preview-item-expires">Expires: ' + new Date(token.expires_at).toLocaleString() + '</span>' +
                    '</div>' +
                    '<div class="share-preview-item-actions">' +
                        '<button class="share-preview-btn small revoke" data-token="' + token.token + '">Revoke</button>' +
                    '</div>' +
                '</div>';
            });
            listDiv.innerHTML = html;

            // Bind revoke buttons
            listDiv.querySelectorAll('.revoke').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var tokenVal = this.getAttribute('data-token');
                    revokeToken(tokenVal, csrfToken, objectId, contentType);
                });
            });
        })
        .catch(function(err) {
            console.error('Error loading preview links:', err);
            listDiv.innerHTML = '<div class="share-preview-empty">Could not load preview links</div>';
        });
    }

    function revokeToken(token, csrfToken, objectId, contentType) {
        fetch('/pages/preview/tokens/' + token + '/revoke/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
        })
        .then(function(res) {
            if (!res.ok) throw new Error('Failed to revoke');
            loadExistingLinks(objectId, contentType, csrfToken);
            if (window.adminToast) {
                window.adminToast('Preview link revoked.', 'success');
            }
        })
        .catch(function(err) {
            console.error('Error revoking token:', err);
            if (window.adminToast) {
                window.adminToast('Failed to revoke preview link.', 'error');
            }
        });
    }

    function closeShareModal() {
        var overlay = document.getElementById('share-preview-overlay');
        if (overlay) overlay.classList.remove('active');
    }

    function getCSRFToken() {
        var el = document.querySelector('[name=csrfmiddlewaretoken]');
        return el ? el.value : '';
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
