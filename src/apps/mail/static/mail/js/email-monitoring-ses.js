/*
 * Mail → Delivery Operations → Email Monitoring → Amazon SES: filters the suppression-list table in place (a search
 * on the address, domain, status, reason and source, and a status choice) and exports the rows shown as CSV, TSV,
 * JSON or an Excel sheet. The rows, the counts and every notice are rendered by the server; this script only hides
 * rows and builds the file. Spreadsheet cells are neutralised so a value is never evaluated as a formula, as the
 * Bounced addresses export does.
 */
(function () {
    'use strict';

    var HEADERS = ['Email', 'Domain', 'Status', 'Last Seen', 'Reason', 'Source', 'Context'];
    var FIELDS = {
        Email: 'email', Domain: 'domain', Status: 'label', 'Last Seen': 'lastSeen',
        Reason: 'reason', Source: 'source', Context: 'context'
    };
    var FORMULA_TRIGGERS = ['=', '+', '-', '@', '\t', '\r'];

    function fmt(value) { return Number(value || 0).toLocaleString(); }

    function record(row) {
        var data = {};
        HEADERS.forEach(function (header) { data[header] = row.dataset[FIELDS[header]] || ''; });
        return data;
    }

    function haystack(row) {
        var data = row.dataset;
        return [data.email, data.domain, data.reason, data.label, data.source, data.context].join(' ').toLowerCase();
    }

    function spreadsheetText(value) {
        var text = String(value == null ? '' : value);
        return FORMULA_TRIGGERS.indexOf(text.charAt(0)) !== -1 ? "'" + text : text;
    }

    function delimitedCell(value, delimiter) {
        var text = spreadsheetText(value);
        if (/["\n\r]/.test(text) || text.indexOf(delimiter) !== -1) {
            return '"' + text.replace(/"/g, '""') + '"';
        }
        return text;
    }

    function delimited(records, delimiter) {
        var lines = [HEADERS.map(function (header) { return delimitedCell(header, delimiter); }).join(delimiter)];
        records.forEach(function (item) {
            lines.push(HEADERS.map(function (header) { return delimitedCell(item[header], delimiter); }).join(delimiter));
        });
        return lines.join('\n') + '\n';
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char];
        });
    }

    function excelSheet(records) {
        var cells = function (values, tag) {
            return values.map(function (value) { return '<' + tag + '>' + escapeHtml(value) + '</' + tag + '>'; }).join('');
        };
        var body = records.map(function (item) {
            return '<tr>' + cells(HEADERS.map(function (header) { return spreadsheetText(item[header]); }), 'td') + '</tr>';
        }).join('');
        return '<html><head><meta charset="utf-8"></head><body><table><thead><tr>' + cells(HEADERS, 'th') +
            '</tr></thead><tbody>' + body + '</tbody></table></body></html>';
    }

    function download(filename, type, content) {
        var url = URL.createObjectURL(new Blob([content], {type: type}));
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function start() {
        var root = document.querySelector('[data-ses-recipients]');
        if (!root) { return; }
        var search = root.querySelector('[data-ses-search]');
        var status = root.querySelector('[data-ses-status]');
        var format = root.querySelector('[data-ses-format]');
        var button = root.querySelector('[data-ses-export]');
        var showing = root.querySelector('[data-ses-showing]');
        var noMatch = root.querySelector('[data-ses-no-match]');
        var rows = Array.prototype.slice.call(root.querySelectorAll('[data-ses-row]'));
        if (!rows.length) { return; }

        function filters() {
            return {query: search ? search.value.trim().toLowerCase() : '', status: status ? status.value : 'all'};
        }

        function visible() {
            return rows.filter(function (row) { return !row.hidden; });
        }

        function apply() {
            var wanted = filters();
            rows.forEach(function (row) {
                var statusMatches = wanted.status === 'all' || row.dataset.status === wanted.status;
                row.hidden = !(statusMatches && (!wanted.query || haystack(row).indexOf(wanted.query) !== -1));
            });
            var count = visible().length;
            if (showing) { showing.textContent = count === rows.length ? fmt(count) : fmt(count) + ' / ' + fmt(rows.length); }
            if (noMatch) { noMatch.hidden = count > 0; }
            if (button) { button.disabled = count === 0; }
        }

        function exportShown() {
            var records = visible().map(record);
            if (!records.length) { return; }
            var chosen = format ? format.value : 'csv';
            var stem = 'ses-problem-recipients-' + (root.dataset.windowShort || '') + '-' + new Date().toISOString().slice(0, 10);
            if (chosen === 'json') {
                download(stem + '.json', 'application/json;charset=utf-8', JSON.stringify({
                    generated_at: new Date().toISOString(),
                    window_days: Number(root.dataset.windowDays) || null,
                    window_label: root.dataset.windowLabel || '',
                    filters: filters(),
                    count: records.length,
                    records: records
                }, null, 2) + '\n');
            } else if (chosen === 'tsv') {
                download(stem + '.tsv', 'text/tab-separated-values;charset=utf-8', delimited(records, '\t'));
            } else if (chosen === 'xls') {
                download(stem + '.xls', 'application/vnd.ms-excel;charset=utf-8', excelSheet(records));
            } else {
                download(stem + '.csv', 'text/csv;charset=utf-8', delimited(records, ','));
            }
        }

        if (search) { search.addEventListener('input', apply); }
        if (status) { status.addEventListener('change', apply); }
        if (button) { button.addEventListener('click', exportShown); }
        apply();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
