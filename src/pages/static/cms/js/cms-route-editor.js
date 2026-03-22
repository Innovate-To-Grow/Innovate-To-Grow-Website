(function () {
    var config = window.CMS_ROUTE_EDITOR || {};

    function normalizeSegments(values) {
        var segments = [];

        values.forEach(function (value) {
            String(value || '')
                .split('/')
                .forEach(function (part) {
                    var segment = part.trim();
                    if (segment) {
                        segments.push(segment);
                    }
                });
        });

        return segments;
    }

    function buildRoute(segments) {
        return segments.length ? '/' + segments.join('/') : '/';
    }

    function debounce(fn, wait) {
        var timeoutId = null;
        return function () {
            var args = arguments;
            clearTimeout(timeoutId);
            timeoutId = setTimeout(function () {
                fn.apply(null, args);
            }, wait);
        };
    }

    function createSegmentRow(value, index, state) {
        var row = document.createElement('div');
        row.className = 'cms-route-segment-row';

        var slash = document.createElement('span');
        slash.className = 'cms-route-slash';
        slash.textContent = '/';

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'cms-route-segment-input';
        input.placeholder = index === 0 ? 'path' : 'path-segment';
        input.value = value || '';

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'cms-route-remove';
        removeBtn.textContent = 'Remove';
        removeBtn.disabled = state.inputs.length <= 1;
        removeBtn.addEventListener('click', function () {
            state.inputs.splice(index, 1);
            if (state.inputs.length === 0) {
                state.inputs.push('');
            }
            renderEditor(state, true);
        });

        input.addEventListener('input', function () {
            state.inputs[index] = input.value;
            syncRoute(state, false);
        });

        input.addEventListener('blur', function () {
            state.inputs[index] = input.value;
            syncRoute(state, true);
        });

        row.appendChild(slash);
        row.appendChild(input);
        row.appendChild(removeBtn);
        return row;
    }

    function setStatus(state, message, className) {
        state.statusEl.textContent = message;
        state.statusEl.className = 'cms-route-status' + (className ? ' ' + className : '');
    }

    function renderEditor(state, rerenderInputs) {
        if (rerenderInputs) {
            state.segmentsEl.innerHTML = '';
            state.inputs.forEach(function (value, index) {
                state.segmentsEl.appendChild(createSegmentRow(value, index, state));
            });
        }

        state.previewEl.textContent = state.sourceInput.value || '/';
    }

    var runConflictCheck = debounce(function (state, route) {
        if (!config.checkUrl) return;

        var url = new URL(config.checkUrl, window.location.origin);
        url.searchParams.set('route', route);
        if (config.pageId) {
            url.searchParams.set('page_id', config.pageId);
        }

        fetch(url.toString(), {credentials: 'same-origin'})
            .then(function (response) {
                return response.json();
            })
            .then(function (result) {
                state.sourceInput.value = result.normalized_route || route;
                state.previewEl.textContent = state.sourceInput.value;

                if (!result.is_valid) {
                    setStatus(state, result.message || 'Invalid route.', 'is-invalid');
                    return;
                }

                if (result.has_conflict) {
                    setStatus(state, result.message || 'Route conflict detected.', 'is-conflict');
                    return;
                }

                setStatus(state, 'Route is available.', 'is-valid');
            })
            .catch(function () {
                setStatus(state, 'Could not verify route availability right now.', 'is-invalid');
            });
    }, 250);

    function syncRoute(state, rerenderInputs) {
        var segments = normalizeSegments(state.inputs);
        state.inputs = segments.length ? segments.slice() : [''];
        state.sourceInput.value = buildRoute(segments);
        renderEditor(state, rerenderInputs);
        runConflictCheck(state, state.sourceInput.value);
    }

    function init() {
        var sourceInput = document.querySelector('[data-role="cms-route-source"]');
        if (!sourceInput) return;

        var sourceRow = sourceInput.closest('.form-row') || sourceInput.closest('.fieldBox') || sourceInput.parentElement;
        if (!sourceRow || !sourceRow.parentNode) return;

        var initialSegments = normalizeSegments([sourceInput.value]);
        var editor = document.createElement('div');
        editor.className = 'cms-route-editor';
        editor.innerHTML =
            '<div class="cms-route-editor-header">' +
            '<p class="cms-route-editor-title">Page Path</p>' +
            '<p class="cms-route-editor-help">Edit one or more path segments. Input is normalized to a no-trailing-slash route.</p>' +
            '</div>' +
            '<div class="cms-route-preview"></div>' +
            '<div class="cms-route-segments"></div>' +
            '<div style="margin-top:0.75rem;">' +
            '<button type="button" class="cms-route-add">+ Add Segment</button>' +
            '</div>' +
            '<div class="cms-route-status"></div>';

        sourceRow.parentNode.insertBefore(editor, sourceRow.nextSibling);
        sourceRow.style.display = 'none';

        var state = {
            sourceInput: sourceInput,
            previewEl: editor.querySelector('.cms-route-preview'),
            segmentsEl: editor.querySelector('.cms-route-segments'),
            statusEl: editor.querySelector('.cms-route-status'),
            addBtn: editor.querySelector('.cms-route-add'),
            inputs: initialSegments.length ? initialSegments.slice() : [''],
        };

        state.addBtn.addEventListener('click', function () {
            state.inputs.push('');
            renderEditor(state, true);
            var inputs = editor.querySelectorAll('.cms-route-segment-input');
            if (inputs.length > 0) {
                inputs[inputs.length - 1].focus();
            }
        });

        syncRoute(state, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
