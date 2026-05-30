(function () {
    function escapeSlug(slug) {
        return String(slug).replace(/"/g, '');
    }

    function buildEmbedSnippet(embedUrl, slug) {
        const safeSlug = escapeSlug(slug);
        return '<iframe src="' + embedUrl + '"\n'
            + '        data-i2g-embed="' + safeSlug + '"\n'
            + '        style="width:100%; border:0;"\n'
            + '        height="400"\n'
            + '        loading="lazy"></iframe>\n'
            + '<script>\n'
            + '(function(){\n'
            + '  window.addEventListener(\'message\', function(e){\n'
            + '    if (!e.data || e.data.type !== \'i2g-embed-resize\' || e.data.slug !== \'' + safeSlug + '\') return;\n'
            + '    document.querySelectorAll(\'iframe[data-i2g-embed="' + safeSlug + '"]\').forEach(function(f){\n'
            + '      f.style.height = e.data.height + \'px\';\n'
            + '    });\n'
            + '  });\n'
            + '})();\n'
            + '</scr' + 'ipt>';
    }

    window.ITGEmbedSnippet = { buildEmbedSnippet: buildEmbedSnippet };
})();
