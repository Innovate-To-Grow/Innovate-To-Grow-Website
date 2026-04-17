(function () {
    const P = window.ITGCmsBlockPrimitives;
    const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

    function renderAll(embeds, blocks) {
        const container = document.getElementById('cms-embeds-container');
        if (!container) return;
        if (!embeds.length) {
            container.innerHTML = '<p class="cms-embeds-empty">No embeds configured. Click "Add Embed" to bundle blocks into an iframe widget.</p>';
            return;
        }
        container.innerHTML = embeds.map((embed, idx) => renderEmbedCard(embed, idx, blocks)).join('');
    }

    function renderEmbedCard(embed, idx, blocks) {
        const slug = String(embed.slug || '');
        const label = String(embed.admin_label || '');
        const selected = new Set((embed.block_sort_orders || []).map(n => Number(n)));
        const frontendUrl = (window.CMS_ROUTE_EDITOR && window.CMS_ROUTE_EDITOR.frontendUrl) || '';
        const slugValid = !!slug && SLUG_RE.test(slug);
        const canShowSnippet = slugValid && frontendUrl && selected.size > 0;
        const embedUrl = canShowSnippet ? (frontendUrl + '/_embed/' + slug) : '';
        const snippet = canShowSnippet ? buildEmbedSnippet(embedUrl, slug) : '';

        const blocksList = blocks.map((b, bIdx) => {
            const isChecked = selected.has(bIdx);
            const cbId = 'cb-embed-' + idx + '-block-' + bIdx;
            const typeLabel = P.getTypeLabel(b.block_type);
            const admin = b.admin_label ? ' — ' + b.admin_label : '';
            return '<div class="cms-embed-block-row">'
                + '<input type="checkbox" id="' + cbId + '"' + (isChecked ? ' checked' : '')
                + ' onchange="toggleEmbedBlock(' + idx + ', ' + bIdx + ', this.checked)">'
                + '<label for="' + cbId + '"><span class="cms-embed-block-order">#' + (bIdx + 1) + '</span>'
                + '<span class="cms-embed-block-type">' + P.escapeHtml(typeLabel) + '</span>'
                + P.escapeHtml(admin) + '</label>'
                + '</div>';
        }).join('');

        let html = '<div class="cms-embed-card" data-embed-index="' + idx + '">';
        html += '<div class="cms-embed-card-header">';
        html += '<span class="cms-embed-card-title">Embed #' + (idx + 1);
        if (label) html += ' — <span class="cms-embed-card-label">' + P.escapeHtml(label) + '</span>';
        html += '</span>';
        html += '<button type="button" class="btn-embed-delete" onclick="removeEmbedConfig(' + idx + ')" title="Delete embed">&times;</button>';
        html += '</div>';
        html += '<div class="cms-embed-card-body">';

        // Slug + label
        html += '<div class="cms-embed-field-row">';
        html += '<div class="cms-embed-field"><label>Slug</label>'
            + '<input type="text" value="' + P.escapeAttr(slug) + '" placeholder="kebab-case-slug" '
            + 'onchange="updateEmbedSlug(' + idx + ', this.value)">'
            + '<span class="field-hint">Lowercase, digits, hyphens only. Globally unique across all pages.</span>';
        if (slug && !slugValid) html += '<span class="field-error">Invalid format.</span>';
        html += '</div>';
        html += '<div class="cms-embed-field"><label>Admin label <span class="field-optional">(optional)</span></label>'
            + '<input type="text" value="' + P.escapeAttr(label) + '" placeholder="e.g. Contact form widget" '
            + 'onchange="updateEmbedLabel(' + idx + ', this.value)"></div>';
        html += '</div>';

        // Blocks list
        html += '<div class="cms-embed-field"><label>Include blocks ';
        html += '<span class="field-hint">Selected blocks render in page order inside the iframe.</span></label>';
        if (!blocks.length) {
            html += '<p class="cms-embed-block-empty">Add some content blocks above first.</p>';
        } else {
            html += '<div class="cms-embed-blocks-list">' + blocksList + '</div>';
        }
        html += '</div>';

        // Snippet
        if (canShowSnippet) {
            html += '<div class="cms-embed-field"><label>Embed URL</label>'
                + '<div class="cms-embed-url-row"><code>' + P.escapeHtml(embedUrl) + '</code>'
                + ' <a href="' + P.escapeAttr(embedUrl) + '" target="_blank" rel="noopener">Open preview &rarr;</a>'
                + '</div></div>';
            html += '<div class="cms-embed-field"><label>Iframe snippet</label>'
                + '<textarea class="cms-embed-snippet" readonly onclick="this.select()">' + P.escapeHtml(snippet) + '</textarea>'
                + '<button type="button" class="btn-embed-copy" onclick="copyEmbedSnippet(' + idx + ')">Copy snippet</button>'
                + '</div>';
        } else if (!slug) {
            html += '<p class="cms-embed-hint">Enter a slug to generate the embed snippet.</p>';
        } else if (!slugValid) {
            html += '<p class="cms-embed-hint cms-embed-hint-warn">Fix slug format to generate the snippet.</p>';
        } else if (selected.size === 0) {
            html += '<p class="cms-embed-hint">Select at least one block to generate the snippet.</p>';
        } else if (!frontendUrl) {
            html += '<p class="cms-embed-hint cms-embed-hint-warn">FRONTEND_URL is not configured — snippet preview unavailable.</p>';
        }

        html += '</div></div>';
        return html;
    }

    function buildEmbedSnippet(embedUrl, slug) {
        const safeSlug = String(slug).replace(/"/g, '');
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

    /**
     * Adjust block_sort_orders after blocks are reordered or removed.
     *  - movedFrom / movedTo: swap indices (one block swapped with its neighbor)
     *  - removed: drop that index and shift higher indices down by 1
     */
    function reindexAfterBlockMove(embeds, fromIdx, toIdx) {
        return embeds.map(embed => ({
            ...embed,
            block_sort_orders: (embed.block_sort_orders || []).map(i => {
                if (i === fromIdx) return toIdx;
                if (i === toIdx) return fromIdx;
                return i;
            }),
        }));
    }

    function reindexAfterBlockRemove(embeds, removedIdx) {
        return embeds.map(embed => ({
            ...embed,
            block_sort_orders: (embed.block_sort_orders || [])
                .filter(i => i !== removedIdx)
                .map(i => (i > removedIdx ? i - 1 : i)),
        }));
    }

    /**
     * Convert free-text into a valid embed slug: lowercase, kebab-case,
     * alphanumeric + hyphens, must start with an alphanumeric.
     */
    function normalizeSlug(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    /**
     * Generate a default embed slug that is unique within the current page's
     * embed configs. Prefers the page's slug field; falls back to the route
     * or the literal "embed". Appends "-embed", "-embed-2", "-embed-3", ...
     * until a non-colliding slug is found.
     *
     * Global uniqueness (across pages) is still enforced server-side at save.
     */
    function generateDefaultSlug(existingEmbeds) {
        var slugEl = document.getElementById('id_slug');
        var routeEl = document.getElementById('id_route');
        var base = normalizeSlug(slugEl && slugEl.value);
        if (!base) base = normalizeSlug(routeEl && routeEl.value);
        if (!base) base = 'embed';

        var used = new Set((existingEmbeds || []).map(e => String(e.slug || '')));
        var candidate = base + '-embed';
        var n = 2;
        while (used.has(candidate) || !SLUG_RE.test(candidate)) {
            candidate = base + '-embed-' + n;
            n += 1;
            if (n > 999) break;
        }
        return candidate;
    }

    window.ITGCmsEmbeds = {
        renderAll,
        reindexAfterBlockMove,
        reindexAfterBlockRemove,
        generateDefaultSlug,
    };
})();
