(function () {
    function escapeSlug(slug) {
        return String(slug).replace(/"/g, '');
    }

    // The partner page sizes the iframe from the widget's resize messages, and lets the widget's
    // "Copy link" buttons use the clipboard (Chrome denies it to cross-origin frames by default).
    // It trusts only messages from the widget's own origin: any other frame could post one. A height
    // of zero (nothing rendered yet) leaves the iframe as it is, as the site's own embed block does.
    // It also scrolls the page for the widget, because WebKit does not let scrollIntoView in a frame
    // from another site scroll the page around it. The widget says hello, the page answers ready, and
    // from then on the widget asks for a box (top and height, in frame coordinates) to be brought on
    // screen as scrollIntoView({block: 'start' | 'nearest'}) would. Scroll messages count only from one
    // of these iframes (matched by e.source) and only with finite numbers. A widget whose hello gets no
    // answer, as with snippets pasted before this, keeps using scrollIntoView itself.
    function buildEmbedSnippet(embedUrl, slug) {
        const safeSlug = escapeSlug(slug);
        const origin = JSON.stringify(new URL(embedUrl).origin);
        return '<iframe src="' + embedUrl + '"\n'
            + '        data-i2g-embed="' + safeSlug + '"\n'
            + '        style="width:100%; border:0;"\n'
            + '        height="400"\n'
            + '        allow="clipboard-write"\n'
            + '        loading="lazy"></iframe>\n'
            + '<script>\n'
            + '(function(){\n'
            + '  var sel = \'iframe[data-i2g-embed="' + safeSlug + '"]\';\n'
            + '  function finite(n){ return typeof n === \'number\' && isFinite(n); }\n'
            + '  window.addEventListener(\'message\', function(e){\n'
            + '    if (e.origin !== ' + origin + ') return;\n'
            + '    var d = e.data;\n'
            + '    if (!d || d.slug !== \'' + safeSlug + '\') return;\n'
            + '    if (d.type === \'i2g-embed-resize\') {\n'
            + '      if (!(d.height > 0)) return;\n'
            + '      document.querySelectorAll(sel).forEach(function(f){\n'
            + '        f.style.height = d.height + \'px\';\n'
            + '      });\n'
            + '      return;\n'
            + '    }\n'
            + '    var f = [].filter.call(document.querySelectorAll(sel), function(x){\n'
            + '      return x.contentWindow === e.source;\n'
            + '    })[0];\n'
            + '    if (!f) return;\n'
            + '    if (d.type === \'i2g-embed-scroll-hello\') {\n'
            + '      f.contentWindow.postMessage({type: \'i2g-embed-scroll-ready\'}, ' + origin + ');\n'
            + '    } else if (d.type === \'i2g-embed-scroll-into-view\' && finite(d.top) && finite(d.height)) {\n'
            + '      var boxTop = f.getBoundingClientRect().top + d.top, boxBottom = boxTop + d.height;\n'
            + '      var vh = window.innerHeight, by = 0;\n'
            + '      if (d.block === \'start\') by = boxTop;\n'
            + '      else if (d.block === \'nearest\' && (boxTop < 0) !== (boxBottom > vh)) {\n'
            + '        by = (boxTop < 0) === (d.height > vh) ? boxBottom - vh : boxTop;\n'
            + '      }\n'
            + '      if (by) window.scrollTo({top: window.pageYOffset + by, behavior: d.smooth ? \'smooth\' : \'auto\'});\n'
            + '    }\n'
            + '  });\n'
            + '})();\n'
            + '</scr' + 'ipt>';
    }

    window.ITGEmbedSnippet = { buildEmbedSnippet: buildEmbedSnippet };
})();
