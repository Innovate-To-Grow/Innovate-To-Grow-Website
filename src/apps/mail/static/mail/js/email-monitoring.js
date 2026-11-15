/*
 * Mail → Delivery Operations → Email Monitoring: draws the charts of the page from its JSON payload
 * (<script type="application/json" id="…">) into SVG, and shows the custom-range date fields only when needed.
 *
 * Every chart has a server-rendered legend and data table beside it, so nothing here gates a value: the tooltip
 * (hover or keyboard focus) only repeats what the table holds. Labels are inserted with textContent.
 */
(function () {
    'use strict';

    var SVG_NS = 'http://www.w3.org/2000/svg';
    var PLOT_HEIGHT = 200;
    var AXIS_BAND = 28;
    var PAD_TOP = 10;
    var PAD_LEFT = 44;
    var BAR_MAX = 24;
    var GAP = 2;
    var RADIUS = 4;

    function svgEl(name, attrs) {
        var node = document.createElementNS(SVG_NS, name);
        Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, attrs[key]); });
        return node;
    }

    function fmt(value) {
        var number = Number(value || 0);
        if (Math.abs(number) >= 10000) {
            return (Math.round(number / 100) / 10).toLocaleString() + 'K';
        }
        return number.toLocaleString();
    }

    function niceStep(max) {
        if (max <= 4) { return 1; }
        var rough = max / 4;
        var power = Math.pow(10, Math.floor(Math.log10(rough)));
        var candidates = [1, 2, 2.5, 5, 10];
        for (var i = 0; i < candidates.length; i += 1) {
            if (candidates[i] * power >= rough) { return Math.max(1, candidates[i] * power); }
        }
        return 10 * power;
    }

    function topPath(x, y, width, height, radius) {
        // A column with a rounded data end (top) and a square end at the baseline.
        var r = Math.max(0, Math.min(radius, width / 2, height));
        var base = y + height;
        return 'M' + x + ',' + base + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
            'H' + (x + width - r) + 'Q' + (x + width) + ',' + y + ' ' + (x + width) + ',' + (y + r) + 'V' + base + 'Z';
    }

    function bucketTotals(data, kind) {
        var names = data.names.map(function (item) { return item.key; });
        return data.labels.map(function (_label, index) {
            var values = names.map(function (name) { return Number(data.series[name][index] || 0); });
            return kind === 'lines' ? Math.max.apply(null, values.concat([0])) : values.reduce(function (a, b) { return a + b; }, 0);
        });
    }

    function Tooltip(host) {
        var box = document.createElement('div');
        box.className = 'i2g-monitor-tooltip';
        box.hidden = true;
        host.appendChild(box);
        this.show = function (title, rows, x, y) {
            box.textContent = '';
            var head = document.createElement('div');
            head.className = 'i2g-monitor-tooltip-title';
            head.textContent = title;
            box.appendChild(head);
            rows.forEach(function (row) {
                var line = document.createElement('div');
                line.className = 'i2g-monitor-tooltip-row';
                var key = document.createElement('span');
                key.className = 'i2g-monitor-key i2g-monitor-key--line i2g-series-' + row.slot;
                var value = document.createElement('strong');
                value.textContent = fmt(row.value);
                var name = document.createElement('span');
                name.textContent = row.label;
                line.appendChild(key);
                line.appendChild(value);
                line.appendChild(name);
                box.appendChild(line);
            });
            box.hidden = false;
            var maxLeft = host.clientWidth - box.offsetWidth - 4;
            box.style.left = Math.max(0, Math.min(x + 12, maxLeft)) + 'px';
            box.style.top = Math.max(0, y - box.offsetHeight - 8) + 'px';
        };
        this.hide = function () { box.hidden = true; };
    }

    function drawAxes(svg, layout, data) {
        for (var tick = 0; tick <= layout.max; tick += layout.step) {
            var y = layout.y(tick);
            svg.appendChild(svgEl('line', { x1: PAD_LEFT, x2: layout.plotRight, y1: y, y2: y, class: tick === 0 ? 'i2g-axis' : 'i2g-grid' }));
            var label = svgEl('text', { x: PAD_LEFT - 6, y: y + 4, 'text-anchor': 'end', class: 'i2g-tick' });
            label.textContent = fmt(tick);
            svg.appendChild(label);
        }
        var every = Math.max(1, Math.ceil(78 / layout.band));
        data.display.forEach(function (text, index) {
            if (index % every !== 0) { return; }
            var label = svgEl('text', { x: layout.center(index), y: PAD_TOP + PLOT_HEIGHT + 18, 'text-anchor': 'middle', class: 'i2g-tick' });
            label.textContent = text;
            svg.appendChild(label);
        });
    }

    function rowsAt(data, index) {
        return data.names.map(function (item, position) {
            return { label: item.label, value: data.series[item.key][index] || 0, slot: position + 1 };
        });
    }

    function drawColumns(svg, layout, data, stacked, tooltip) {
        var barWidth = Math.max(2, Math.min(BAR_MAX, layout.band * 0.7));
        var hits = [];
        data.labels.forEach(function (_label, index) {
            var group = svgEl('g', { class: 'i2g-band' });
            var baseline = layout.y(0);
            var x = layout.center(index) - barWidth / 2;
            var segments = data.names.map(function (item, position) {
                return { value: Number(data.series[item.key][index] || 0), slot: position + 1 };
            }).filter(function (segment) { return segment.value > 0; });
            segments.forEach(function (segment, order) {
                var height = layout.y(0) - layout.y(segment.value);
                var top = baseline - height;
                // A 2px surface gap separates stacked segments; the bottom one stays on the baseline.
                var drawn = Math.max(1, height - (order > 0 ? GAP : 0));
                var shape = order === segments.length - 1
                    ? svgEl('path', { d: topPath(x, top, barWidth, drawn, RADIUS), class: 'i2g-mark i2g-fill-' + segment.slot })
                    : svgEl('rect', { x: x, y: top, width: barWidth, height: drawn, class: 'i2g-mark i2g-fill-' + segment.slot });
                group.appendChild(shape);
                baseline = stacked ? top : baseline;
            });
            // The whole band is the hit target, larger than the bar; one band at a time takes keyboard focus.
            var hit = svgEl('rect', {
                x: layout.center(index) - layout.band / 2, y: PAD_TOP, width: layout.band, height: PLOT_HEIGHT,
                class: 'i2g-hit', tabindex: index === data.labels.length - 1 ? '0' : '-1', role: 'img',
                'aria-label': data.display[index] + ': ' + rowsAt(data, index).map(function (row) {
                    return row.label + ' ' + row.value;
                }).join(', '),
            });
            function show() {
                group.classList.add('is-active');
                tooltip.show(data.display[index], rowsAt(data, index), layout.center(index), PAD_TOP + 20);
            }
            function hide() { group.classList.remove('is-active'); tooltip.hide(); }
            hit.addEventListener('pointerenter', show);
            hit.addEventListener('focus', show);
            hit.addEventListener('pointerleave', hide);
            hit.addEventListener('blur', hide);
            hit.addEventListener('keydown', function (event) {
                if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') { return; }
                event.preventDefault();
                var next = hits[Math.max(0, Math.min(hits.length - 1, index + (event.key === 'ArrowLeft' ? -1 : 1)))];
                hits.forEach(function (item) { item.setAttribute('tabindex', item === next ? '0' : '-1'); });
                next.focus();
            });
            hits.push(hit);
            group.appendChild(hit);
            svg.appendChild(group);
        });
    }

    function endLabels(svg, layout, data) {
        // Direct labels at the line ends, only where they do not collide; the legend names every series anyway.
        var count = data.labels.length;
        var ends = data.names.map(function (item) {
            return { label: item.label, y: layout.y(data.series[item.key][count - 1] || 0) };
        }).sort(function (a, b) { return a.y - b.y; });
        var lastY = -Infinity;
        ends.forEach(function (end) {
            if (end.y - lastY < 13) { return; }
            lastY = end.y;
            var text = svgEl('text', { x: layout.center(count - 1) + 8, y: end.y + 4, class: 'i2g-end-label' });
            text.textContent = end.label;
            svg.appendChild(text);
        });
    }

    function drawLines(svg, layout, data, tooltip) {
        var count = data.labels.length;
        data.names.forEach(function (item, position) {
            var values = data.series[item.key];
            var path = values.map(function (value, index) {
                return (index ? 'L' : 'M') + layout.center(index) + ',' + layout.y(value || 0);
            }).join('');
            svg.appendChild(svgEl('path', { d: path, class: 'i2g-line i2g-stroke-' + (position + 1) }));
            var lastY = layout.y(values[count - 1] || 0);
            svg.appendChild(svgEl('circle', { cx: layout.center(count - 1), cy: lastY, r: 4, class: 'i2g-dot i2g-fill-' + (position + 1) }));
        });
        if (layout.labelled) { endLabels(svg, layout, data); }
        var cross = svgEl('line', { y1: PAD_TOP, y2: PAD_TOP + PLOT_HEIGHT, class: 'i2g-crosshair', visibility: 'hidden' });
        svg.appendChild(cross);
        var overlay = svgEl('rect', {
            x: PAD_LEFT, y: PAD_TOP, width: layout.plotRight - PAD_LEFT, height: PLOT_HEIGHT, class: 'i2g-hit', tabindex: '0',
            role: 'img', 'aria-label': 'Use the left and right arrow keys to read each period; the data table lists every value.',
        });
        var current = count - 1;
        function showAt(index) {
            current = Math.max(0, Math.min(count - 1, index));
            var x = layout.center(current);
            cross.setAttribute('x1', x);
            cross.setAttribute('x2', x);
            cross.setAttribute('visibility', 'visible');
            tooltip.show(data.display[current], rowsAt(data, current), x, PAD_TOP + 20);
        }
        function hide() { cross.setAttribute('visibility', 'hidden'); tooltip.hide(); }
        overlay.addEventListener('pointermove', function (event) {
            var box = svg.getBoundingClientRect();
            var scale = layout.width / box.width;
            showAt(Math.round(((event.clientX - box.left) * scale - PAD_LEFT - layout.band / 2) / layout.band));
        });
        overlay.addEventListener('pointerleave', hide);
        overlay.addEventListener('focus', function () { showAt(current); });
        overlay.addEventListener('blur', hide);
        overlay.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
                event.preventDefault();
                showAt(current + (event.key === 'ArrowLeft' ? -1 : 1));
            }
        });
        svg.appendChild(overlay);
    }

    function draw(plot, data, kind, title) {
        plot.textContent = '';
        var width = Math.max(320, plot.clientWidth || 600);
        var count = data.labels.length;
        var peak = Math.max.apply(null, bucketTotals(data, kind).concat([0]));
        var step = niceStep(peak);
        var max = Math.max(step, Math.ceil(peak / step) * step);
        // Wide line charts keep room on the right for direct end labels; narrow ones rely on the legend alone.
        var labelled = kind === 'lines' && data.names.length > 1 && width >= 520;
        var plotRight = width - (labelled ? 104 : 8);
        var band = (plotRight - PAD_LEFT) / Math.max(1, count);
        var layout = {
            width: width, plotRight: plotRight, band: band, step: step, max: max, labelled: labelled,
            center: function (index) { return PAD_LEFT + band * index + band / 2; },
            y: function (value) { return PAD_TOP + PLOT_HEIGHT - (value / max) * PLOT_HEIGHT; },
        };
        var svg = svgEl('svg', {
            viewBox: '0 0 ' + width + ' ' + (PAD_TOP + PLOT_HEIGHT + AXIS_BAND), role: 'group',
            'aria-label': title + ' (' + count + ' periods; the data table below lists every value)',
        });
        plot.appendChild(svg);
        drawAxes(svg, layout, data);
        var tooltip = new Tooltip(plot);
        if (kind === 'lines') {
            drawLines(svg, layout, data, tooltip);
        } else {
            drawColumns(svg, layout, data, kind === 'stacked', tooltip);
        }
    }

    function payloads() {
        var cache = {};
        return function (id) {
            if (!(id in cache)) {
                var node = document.getElementById(id);
                try { cache[id] = node ? JSON.parse(node.textContent) : null; } catch (error) { cache[id] = null; }
            }
            return cache[id];
        };
    }

    function renderAll() {
        var read = payloads();
        document.querySelectorAll('.i2g-monitor-chart[data-chart]').forEach(function (figure) {
            var plot = figure.querySelector('[data-chart-plot]');
            var payload = read(figure.getAttribute('data-source'));
            var data = payload && payload[figure.getAttribute('data-chart')];
            if (!plot || !data || !data.labels || !data.labels.length) { return; }
            var heading = figure.querySelector('h3');
            draw(plot, data, figure.getAttribute('data-kind'), heading ? heading.textContent : 'Chart');
        });
    }

    function customRangeFields() {
        var select = document.querySelector('[data-monitor-range]');
        if (!select) { return; }
        var fields = document.querySelectorAll('[data-monitor-custom]');
        function sync() {
            fields.forEach(function (field) {
                field.hidden = select.value !== 'custom';
                field.querySelectorAll('input').forEach(function (input) { input.disabled = select.value !== 'custom'; });
            });
        }
        select.addEventListener('change', sync);
        sync();
    }

    function start() {
        customRangeFields();
        renderAll();
        var pending = false;
        window.addEventListener('resize', function () {
            if (pending) { return; }
            pending = true;
            window.requestAnimationFrame(function () { pending = false; renderAll(); });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
