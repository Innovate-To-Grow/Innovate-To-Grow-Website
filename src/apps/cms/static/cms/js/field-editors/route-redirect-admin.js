(function () {
    var config = window.ROUTE_REDIRECT_ADMIN || {};

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

    function init() {
        var sourceInput = document.querySelector('[data-role="route-redirect-source"]');
        var destinationInput = document.getElementById('id_destination_path');
        var status = document.getElementById('route-redirect-conflict-status');
        if (!destinationInput || !status || !config.checkUrl) return;

        var check = debounce(function () {
            var sourcePath = sourceInput ? sourceInput.value : config.sourcePath;
            if (!sourcePath || !destinationInput.value) {
                status.textContent = 'Choose both a source and destination to check conflicts.';
                return;
            }

            var url = new URL(config.checkUrl, window.location.origin);
            url.searchParams.set('source_path', sourcePath);
            url.searchParams.set('destination_path', destinationInput.value);
            if (config.redirectId) url.searchParams.set('redirect_id', config.redirectId);

            fetch(url.toString(), {credentials: 'same-origin'})
                .then(function (response) { return response.json(); })
                .then(function (result) {
                    if (sourceInput && result.is_valid && result.source_path) {
                        sourceInput.value = result.source_path;
                    }
                    status.textContent = result.message || '';
                    status.dataset.state = result.has_conflict ? 'conflict' : 'available';
                })
                .catch(function () {
                    status.textContent = 'Could not verify route conflicts right now.';
                    status.dataset.state = 'error';
                });
        }, 250);

        if (sourceInput) sourceInput.addEventListener('input', check);
        destinationInput.addEventListener('change', check);
        check();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
