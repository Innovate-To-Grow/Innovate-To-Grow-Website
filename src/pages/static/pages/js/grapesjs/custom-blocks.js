/**
 * Custom GrapesJS blocks for the ITG website editor.
 * Phase 3: Content, Interactive, Data, Embed, and Navigation blocks.
 */
var gjsCustomBlocks = (function() {
    'use strict';

    function register(editor) {
        var bm = editor.BlockManager;

        // =============================================
        // CONTENT category
        // =============================================

        bm.add('hero-section', {
            label: 'Hero Section',
            category: 'Content',
            attributes: { class: 'fa fa-header' },
            content: '<section style="background:#003366;color:#fff;padding:80px 20px;text-align:center;">' +
                '<div style="max-width:900px;margin:0 auto;">' +
                    '<h1 style="font-size:48px;margin-bottom:16px;font-weight:700;">Your Headline Here</h1>' +
                    '<p style="font-size:20px;margin-bottom:32px;opacity:0.9;">A compelling subtitle that describes your value proposition</p>' +
                    '<a href="#" style="display:inline-block;padding:14px 32px;background:#C4972F;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Get Started</a>' +
                '</div>' +
            '</section>',
        });

        bm.add('cta-button', {
            label: 'CTA Button',
            category: 'Content',
            attributes: { class: 'fa fa-hand-pointer-o' },
            content: '<a href="#" style="display:inline-block;padding:12px 28px;background:#003366;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;text-align:center;">Call to Action</a>',
        });

        bm.add('card', {
            label: 'Card',
            category: 'Content',
            attributes: { class: 'fa fa-id-card' },
            content: '<div style="border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;max-width:350px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">' +
                '<img src="https://placehold.co/350x200/e8e8e8/999?text=Card+Image" alt="Card image" style="width:100%;height:200px;object-fit:cover;">' +
                '<div style="padding:20px;">' +
                    '<h3 style="margin:0 0 8px;font-size:20px;font-weight:600;">Card Title</h3>' +
                    '<p style="margin:0 0 16px;color:#666;font-size:14px;line-height:1.5;">A brief description of this card content goes here. Keep it concise and informative.</p>' +
                    '<a href="#" style="color:#003366;text-decoration:none;font-weight:600;font-size:14px;">Learn More &rarr;</a>' +
                '</div>' +
            '</div>',
        });

        bm.add('feature-box', {
            label: 'Feature Box',
            category: 'Content',
            attributes: { class: 'fa fa-star' },
            content: '<div style="display:flex;gap:16px;padding:24px;align-items:flex-start;">' +
                '<div style="width:48px;height:48px;background:#003366;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:24px;flex-shrink:0;">&#9733;</div>' +
                '<div>' +
                    '<h4 style="margin:0 0 8px;font-size:18px;font-weight:600;">Feature Title</h4>' +
                    '<p style="margin:0;color:#666;font-size:14px;line-height:1.6;">Describe this feature and why it matters to your audience.</p>' +
                '</div>' +
            '</div>',
        });

        bm.add('testimonial', {
            label: 'Testimonial',
            category: 'Content',
            attributes: { class: 'fa fa-quote-left' },
            content: '<div style="padding:32px;background:#f8f9fa;border-radius:8px;border-left:4px solid #C4972F;max-width:600px;">' +
                '<p style="font-size:18px;line-height:1.6;color:#333;margin:0 0 16px;font-style:italic;">&ldquo;This is a testimonial quote. Share what someone said about your organization or product.&rdquo;</p>' +
                '<div style="display:flex;align-items:center;gap:12px;">' +
                    '<img src="https://placehold.co/48x48/003366/fff?text=JS" alt="Author" style="width:48px;height:48px;border-radius:50%;object-fit:cover;">' +
                    '<div>' +
                        '<div style="font-weight:600;font-size:14px;">Jane Smith</div>' +
                        '<div style="color:#888;font-size:13px;">Director of Innovation</div>' +
                    '</div>' +
                '</div>' +
            '</div>',
        });

        // =============================================
        // INTERACTIVE category
        // =============================================

        bm.add('accordion', {
            label: 'Accordion / FAQ',
            category: 'Interactive',
            attributes: { class: 'fa fa-bars' },
            content: '<div class="itg-accordion">' +
                '<details style="border:1px solid #e0e0e0;border-radius:6px;margin-bottom:8px;">' +
                    '<summary style="padding:16px;cursor:pointer;font-weight:600;font-size:16px;background:#f8f9fa;">Question or Section Title 1</summary>' +
                    '<div style="padding:16px;border-top:1px solid #e0e0e0;"><p style="margin:0;color:#555;line-height:1.6;">Answer or content goes here. You can add any content inside this section.</p></div>' +
                '</details>' +
                '<details style="border:1px solid #e0e0e0;border-radius:6px;margin-bottom:8px;">' +
                    '<summary style="padding:16px;cursor:pointer;font-weight:600;font-size:16px;background:#f8f9fa;">Question or Section Title 2</summary>' +
                    '<div style="padding:16px;border-top:1px solid #e0e0e0;"><p style="margin:0;color:#555;line-height:1.6;">Answer or content for the second section.</p></div>' +
                '</details>' +
                '<details style="border:1px solid #e0e0e0;border-radius:6px;margin-bottom:8px;">' +
                    '<summary style="padding:16px;cursor:pointer;font-weight:600;font-size:16px;background:#f8f9fa;">Question or Section Title 3</summary>' +
                    '<div style="padding:16px;border-top:1px solid #e0e0e0;"><p style="margin:0;color:#555;line-height:1.6;">Answer or content for the third section.</p></div>' +
                '</details>' +
            '</div>',
        });

        bm.add('stats-counter', {
            label: 'Stats Counter',
            category: 'Interactive',
            attributes: { class: 'fa fa-sort-numeric-asc' },
            content: '<div style="display:flex;gap:40px;justify-content:center;padding:40px 20px;text-align:center;flex-wrap:wrap;">' +
                '<div>' +
                    '<div style="font-size:48px;font-weight:700;color:#003366;">500+</div>' +
                    '<div style="font-size:14px;color:#666;margin-top:4px;">Students Served</div>' +
                '</div>' +
                '<div>' +
                    '<div style="font-size:48px;font-weight:700;color:#003366;">50+</div>' +
                    '<div style="font-size:14px;color:#666;margin-top:4px;">Programs</div>' +
                '</div>' +
                '<div>' +
                    '<div style="font-size:48px;font-weight:700;color:#003366;">95%</div>' +
                    '<div style="font-size:14px;color:#666;margin-top:4px;">Satisfaction Rate</div>' +
                '</div>' +
            '</div>',
        });

        // =============================================
        // DATA category
        // =============================================

        bm.add('pricing-table', {
            label: 'Pricing Table',
            category: 'Data',
            attributes: { class: 'fa fa-usd' },
            content: '<div style="border:2px solid #003366;border-radius:12px;padding:32px;max-width:320px;text-align:center;">' +
                '<h3 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#003366;">Pro Plan</h3>' +
                '<div style="font-size:48px;font-weight:700;color:#333;margin:16px 0;">$29<span style="font-size:16px;color:#888;font-weight:400;">/month</span></div>' +
                '<ul style="list-style:none;padding:0;margin:24px 0;text-align:left;">' +
                    '<li style="padding:8px 0;border-bottom:1px solid #eee;">&#10003; Feature One</li>' +
                    '<li style="padding:8px 0;border-bottom:1px solid #eee;">&#10003; Feature Two</li>' +
                    '<li style="padding:8px 0;border-bottom:1px solid #eee;">&#10003; Feature Three</li>' +
                    '<li style="padding:8px 0;">&#10003; Feature Four</li>' +
                '</ul>' +
                '<a href="#" style="display:block;padding:14px;background:#003366;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Get Started</a>' +
            '</div>',
        });

        bm.add('team-member', {
            label: 'Team Member',
            category: 'Data',
            attributes: { class: 'fa fa-user' },
            content: '<div style="text-align:center;max-width:280px;">' +
                '<img src="https://placehold.co/200x200/003366/fff?text=Photo" alt="Team member" style="width:160px;height:160px;border-radius:50%;object-fit:cover;margin-bottom:16px;">' +
                '<h4 style="margin:0 0 4px;font-size:18px;font-weight:600;">John Doe</h4>' +
                '<p style="margin:0 0 12px;color:#C4972F;font-size:14px;font-weight:500;">Program Director</p>' +
                '<p style="margin:0;color:#666;font-size:14px;line-height:1.5;">Brief bio or description of this team member and their role.</p>' +
            '</div>',
        });

        bm.add('icon-box', {
            label: 'Icon Box',
            category: 'Data',
            attributes: { class: 'fa fa-cube' },
            content: '<div style="text-align:center;padding:32px 20px;max-width:300px;">' +
                '<div style="width:64px;height:64px;background:#003366;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 16px;color:#fff;font-size:28px;">&#9998;</div>' +
                '<h4 style="margin:0 0 8px;font-size:18px;font-weight:600;">Box Title</h4>' +
                '<p style="margin:0;color:#666;font-size:14px;line-height:1.5;">A short description of this item or service.</p>' +
            '</div>',
        });

        // =============================================
        // EMBED category
        // =============================================

        bm.add('map-embed', {
            label: 'Map Embed',
            category: 'Embed',
            attributes: { class: 'fa fa-map-marker' },
            content: '<div style="position:relative;width:100%;height:400px;border-radius:8px;overflow:hidden;">' +
                '<iframe src="https://www.openstreetmap.org/export/embed.html?bbox=-120.4336%2C37.3517%2C-120.4136%2C37.3717&layer=mapnik" ' +
                'style="width:100%;height:100%;border:none;" loading="lazy" title="Map"></iframe>' +
            '</div>',
        });

        bm.add('social-embed', {
            label: 'Social Embed',
            category: 'Embed',
            attributes: { class: 'fa fa-share-alt' },
            content: '<div style="display:flex;gap:12px;justify-content:center;padding:20px;">' +
                '<a href="#" style="width:40px;height:40px;background:#1877F2;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;text-decoration:none;font-size:18px;" title="Facebook">f</a>' +
                '<a href="#" style="width:40px;height:40px;background:#1DA1F2;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;text-decoration:none;font-size:18px;" title="Twitter">t</a>' +
                '<a href="#" style="width:40px;height:40px;background:#0A66C2;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;text-decoration:none;font-size:18px;" title="LinkedIn">in</a>' +
                '<a href="#" style="width:40px;height:40px;background:#E4405F;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;text-decoration:none;font-size:18px;" title="Instagram">ig</a>' +
            '</div>',
        });

        // =============================================
        // NAVIGATION category
        // =============================================

        bm.add('breadcrumb', {
            label: 'Breadcrumb',
            category: 'Navigation',
            attributes: { class: 'fa fa-angle-double-right' },
            content: '<nav style="padding:12px 0;font-size:14px;">' +
                '<a href="#" style="color:#003366;text-decoration:none;">Home</a>' +
                '<span style="margin:0 8px;color:#ccc;">/</span>' +
                '<a href="#" style="color:#003366;text-decoration:none;">Section</a>' +
                '<span style="margin:0 8px;color:#ccc;">/</span>' +
                '<span style="color:#666;">Current Page</span>' +
            '</nav>',
        });

        bm.add('back-to-top', {
            label: 'Back to Top',
            category: 'Navigation',
            attributes: { class: 'fa fa-arrow-up' },
            content: '<a href="#" onclick="window.scrollTo({top:0,behavior:\'smooth\'});return false;" ' +
                'style="position:fixed;bottom:24px;right:24px;width:48px;height:48px;background:#003366;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;text-decoration:none;font-size:20px;box-shadow:0 2px 8px rgba(0,0,0,0.2);z-index:100;">&uarr;</a>',
        });

        bm.add('alert-banner', {
            label: 'Alert Banner',
            category: 'Content',
            attributes: { class: 'fa fa-exclamation-triangle' },
            content: '<div style="padding:16px 24px;background:#fff3cd;border:1px solid #ffc107;border-radius:6px;display:flex;align-items:center;gap:12px;">' +
                '<span style="font-size:20px;">&#9888;</span>' +
                '<p style="margin:0;color:#856404;font-size:14px;line-height:1.5;">Important announcement or alert message goes here.</p>' +
            '</div>',
        });

        bm.add('progress-bar', {
            label: 'Progress Bar',
            category: 'Interactive',
            attributes: { class: 'fa fa-tasks' },
            content: '<div style="padding:8px 0;">' +
                '<div style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px;">' +
                    '<span>Progress</span><span>75%</span>' +
                '</div>' +
                '<div style="background:#e9ecef;border-radius:4px;height:12px;overflow:hidden;">' +
                    '<div style="width:75%;height:100%;background:#003366;border-radius:4px;"></div>' +
                '</div>' +
            '</div>',
        });

        bm.add('badge-group', {
            label: 'Badge Group',
            category: 'Content',
            attributes: { class: 'fa fa-tags' },
            content: '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
                '<span style="padding:4px 12px;background:#003366;color:#fff;border-radius:20px;font-size:13px;">Tag 1</span>' +
                '<span style="padding:4px 12px;background:#C4972F;color:#fff;border-radius:20px;font-size:13px;">Tag 2</span>' +
                '<span style="padding:4px 12px;background:#52b5f7;color:#fff;border-radius:20px;font-size:13px;">Tag 3</span>' +
            '</div>',
        });

        bm.add('timeline', {
            label: 'Timeline',
            category: 'Data',
            attributes: { class: 'fa fa-clock-o' },
            content: '<div style="padding:20px;max-width:600px;">' +
                '<div style="display:flex;gap:16px;margin-bottom:24px;">' +
                    '<div style="display:flex;flex-direction:column;align-items:center;">' +
                        '<div style="width:16px;height:16px;background:#003366;border-radius:50%;"></div>' +
                        '<div style="width:2px;flex:1;background:#e0e0e0;"></div>' +
                    '</div>' +
                    '<div style="padding-bottom:8px;">' +
                        '<div style="font-size:13px;color:#C4972F;font-weight:600;margin-bottom:4px;">2024</div>' +
                        '<h4 style="margin:0 0 4px;font-size:16px;">Milestone One</h4>' +
                        '<p style="margin:0;color:#666;font-size:14px;">Description of this milestone event.</p>' +
                    '</div>' +
                '</div>' +
                '<div style="display:flex;gap:16px;margin-bottom:24px;">' +
                    '<div style="display:flex;flex-direction:column;align-items:center;">' +
                        '<div style="width:16px;height:16px;background:#003366;border-radius:50%;"></div>' +
                        '<div style="width:2px;flex:1;background:#e0e0e0;"></div>' +
                    '</div>' +
                    '<div style="padding-bottom:8px;">' +
                        '<div style="font-size:13px;color:#C4972F;font-weight:600;margin-bottom:4px;">2025</div>' +
                        '<h4 style="margin:0 0 4px;font-size:16px;">Milestone Two</h4>' +
                        '<p style="margin:0;color:#666;font-size:14px;">Description of this milestone event.</p>' +
                    '</div>' +
                '</div>' +
                '<div style="display:flex;gap:16px;">' +
                    '<div style="display:flex;flex-direction:column;align-items:center;">' +
                        '<div style="width:16px;height:16px;background:#C4972F;border-radius:50%;"></div>' +
                    '</div>' +
                    '<div>' +
                        '<div style="font-size:13px;color:#C4972F;font-weight:600;margin-bottom:4px;">2026</div>' +
                        '<h4 style="margin:0 0 4px;font-size:16px;">Current</h4>' +
                        '<p style="margin:0;color:#666;font-size:14px;">Where we are today.</p>' +
                    '</div>' +
                '</div>' +
            '</div>',
        });
    }

    return { register: register };
})();
