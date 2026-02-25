/**
 * GrapesJS Page Templates - Starter layouts.
 * Phase 6: Pre-built templates for common page types.
 */
var gjsPageTemplates = (function() {
    'use strict';

    var templates = [
        {
            name: 'Marketing Landing',
            category: 'Landing Pages',
            icon: 'fa-rocket',
            html: '<section style="background:#003366;color:#fff;padding:80px 20px;text-align:center;">' +
                '<div style="max-width:900px;margin:0 auto;">' +
                    '<h1 style="font-size:52px;margin-bottom:16px;font-weight:700;">Launch Your Next Big Idea</h1>' +
                    '<p style="font-size:20px;margin-bottom:32px;opacity:0.9;">Join hundreds of innovators building the future at UC Merced</p>' +
                    '<a href="#" style="display:inline-block;padding:16px 36px;background:#C4972F;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:18px;">Get Started Today</a>' +
                '</div>' +
                '</section>' +
                '<section style="padding:60px 20px;max-width:1100px;margin:0 auto;">' +
                '<h2 style="text-align:center;font-size:32px;margin-bottom:40px;">Why Choose Us</h2>' +
                '<div style="display:flex;gap:30px;flex-wrap:wrap;justify-content:center;">' +
                    '<div style="flex:1;min-width:280px;text-align:center;padding:24px;"><div style="width:56px;height:56px;background:#003366;border-radius:50%;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:24px;">&#9733;</div><h3 style="font-size:20px;margin-bottom:8px;">Innovation</h3><p style="color:#666;font-size:15px;">Cutting-edge programs designed for the next generation.</p></div>' +
                    '<div style="flex:1;min-width:280px;text-align:center;padding:24px;"><div style="width:56px;height:56px;background:#003366;border-radius:50%;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:24px;">&#9733;</div><h3 style="font-size:20px;margin-bottom:8px;">Community</h3><p style="color:#666;font-size:15px;">A supportive network of mentors and peers.</p></div>' +
                    '<div style="flex:1;min-width:280px;text-align:center;padding:24px;"><div style="width:56px;height:56px;background:#003366;border-radius:50%;margin:0 auto 16px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:24px;">&#9733;</div><h3 style="font-size:20px;margin-bottom:8px;">Impact</h3><p style="color:#666;font-size:15px;">Real-world projects that make a difference.</p></div>' +
                '</div></section>' +
                '<section style="padding:60px 20px;background:#f8f9fa;text-align:center;">' +
                '<h2 style="font-size:32px;margin-bottom:32px;">Ready to Start?</h2>' +
                '<a href="#" style="display:inline-block;padding:14px 32px;background:#003366;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;font-size:16px;">Apply Now</a>' +
                '</section>',
        },
        {
            name: 'About Us',
            category: 'Content Pages',
            icon: 'fa-info-circle',
            html: '<section style="padding:60px 20px;max-width:900px;margin:0 auto;">' +
                '<h1 style="font-size:40px;margin-bottom:16px;">About Innovate to Grow</h1>' +
                '<p style="font-size:18px;color:#555;line-height:1.7;margin-bottom:32px;">Our mission is to empower UC Merced students through innovation, entrepreneurship, and technology. We provide the tools and mentorship needed to turn ideas into reality.</p>' +
                '<h2 style="font-size:28px;margin-bottom:24px;">Our Team</h2>' +
                '<div style="display:flex;gap:30px;flex-wrap:wrap;">' +
                    '<div style="text-align:center;width:200px;"><img src="https://placehold.co/160x160/003366/fff?text=JD" alt="Team member" style="width:120px;height:120px;border-radius:50%;margin-bottom:12px;"><h4 style="margin:0 0 4px;font-size:16px;">Jane Doe</h4><p style="color:#C4972F;font-size:13px;">Director</p></div>' +
                    '<div style="text-align:center;width:200px;"><img src="https://placehold.co/160x160/003366/fff?text=JS" alt="Team member" style="width:120px;height:120px;border-radius:50%;margin-bottom:12px;"><h4 style="margin:0 0 4px;font-size:16px;">John Smith</h4><p style="color:#C4972F;font-size:13px;">Program Lead</p></div>' +
                '</div></section>',
        },
        {
            name: 'Contact Us',
            category: 'Content Pages',
            icon: 'fa-envelope',
            html: '<section style="padding:60px 20px;max-width:1000px;margin:0 auto;">' +
                '<h1 style="font-size:40px;margin-bottom:32px;">Contact Us</h1>' +
                '<div style="display:flex;gap:40px;flex-wrap:wrap;">' +
                    '<div style="flex:1;min-width:300px;">' +
                        '<h3 style="margin-bottom:16px;">Get in Touch</h3>' +
                        '<p style="color:#666;margin-bottom:24px;">Have questions? We\'d love to hear from you.</p>' +
                        '<p style="margin-bottom:8px;"><strong>Email:</strong> info@innovatetogrow.ucmerced.edu</p>' +
                        '<p style="margin-bottom:8px;"><strong>Phone:</strong> (209) 555-0100</p>' +
                        '<p style="margin-bottom:8px;"><strong>Address:</strong> UC Merced, 5200 N Lake Rd, Merced, CA 95343</p>' +
                    '</div>' +
                    '<div style="flex:1;min-width:300px;">' +
                        '<form style="display:flex;flex-direction:column;gap:16px;">' +
                            '<input type="text" placeholder="Your Name" style="padding:12px;border:1px solid #ddd;border-radius:6px;font-size:15px;">' +
                            '<input type="email" placeholder="Email Address" style="padding:12px;border:1px solid #ddd;border-radius:6px;font-size:15px;">' +
                            '<textarea placeholder="Your Message" rows="5" style="padding:12px;border:1px solid #ddd;border-radius:6px;font-size:15px;resize:vertical;"></textarea>' +
                            '<button type="submit" style="padding:14px;background:#003366;color:#fff;border:none;border-radius:6px;font-size:16px;font-weight:600;cursor:pointer;">Send Message</button>' +
                        '</form>' +
                    '</div>' +
                '</div></section>',
        },
        {
            name: 'Event Page',
            category: 'Landing Pages',
            icon: 'fa-calendar',
            html: '<section style="background:linear-gradient(135deg,#003366,#1a1a2e);color:#fff;padding:80px 20px;text-align:center;">' +
                '<h1 style="font-size:48px;margin-bottom:12px;">Innovation Summit 2026</h1>' +
                '<p style="font-size:20px;opacity:0.9;margin-bottom:24px;">March 15, 2026 | UC Merced Campus</p>' +
                '<a href="#" style="display:inline-block;padding:14px 32px;background:#C4972F;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Register Now</a>' +
                '</section>' +
                '<section style="padding:60px 20px;max-width:900px;margin:0 auto;text-align:center;">' +
                '<h2 style="font-size:32px;margin-bottom:16px;">About the Event</h2>' +
                '<p style="font-size:16px;color:#555;line-height:1.7;">Join us for a day of inspiring talks, workshops, and networking with industry leaders and fellow innovators.</p>' +
                '</section>',
        },
        {
            name: 'Blog Article',
            category: 'Content Pages',
            icon: 'fa-pencil',
            html: '<article style="max-width:750px;margin:0 auto;padding:40px 20px;">' +
                '<img src="https://placehold.co/750x400/e8e8e8/999?text=Featured+Image" alt="Featured image" style="width:100%;border-radius:8px;margin-bottom:24px;">' +
                '<h1 style="font-size:36px;line-height:1.3;margin-bottom:12px;">Article Title Goes Here</h1>' +
                '<p style="color:#888;font-size:14px;margin-bottom:32px;">By Author Name | February 25, 2026</p>' +
                '<p style="font-size:17px;line-height:1.8;color:#333;margin-bottom:20px;">Start your article with a compelling introduction that hooks the reader and sets the stage for the content.</p>' +
                '<h2 style="font-size:24px;margin:32px 0 12px;">Section Heading</h2>' +
                '<p style="font-size:17px;line-height:1.8;color:#333;margin-bottom:20px;">Continue with the main body of your article. Use headings to break up sections and make the content scannable.</p>' +
                '<blockquote style="border-left:4px solid #C4972F;padding:16px 24px;margin:24px 0;background:#f8f9fa;"><p style="font-size:18px;font-style:italic;color:#555;margin:0;">"A memorable quote that reinforces your point."</p></blockquote>' +
                '<p style="font-size:17px;line-height:1.8;color:#333;">Wrap up with a conclusion that ties everything together.</p>' +
                '</article>',
        },
        {
            name: 'Blank with Nav',
            category: 'Minimal',
            icon: 'fa-file-o',
            html: '<div style="min-height:60vh;padding:40px 20px;max-width:1200px;margin:0 auto;">' +
                '<p style="color:#999;text-align:center;padding-top:100px;">Start building your page by dragging blocks from the left panel.</p>' +
                '</div>',
        },
    ];

    function apply(editor) {
        var pnManager = editor.Panels;

        pnManager.addButton('options', {
            id: 'page-templates',
            className: 'fa fa-file-text-o',
            command: function() { showTemplateModal(editor); },
            attributes: { title: 'Page Templates' },
        });
    }

    function showTemplateModal(editor) {
        var modal = editor.Modal;
        var html = '<div class="gjs-tpl-gallery">';

        templates.forEach(function(tpl, idx) {
            html += '<div class="gjs-tpl-item" data-tpl-index="' + idx + '">' +
                '<div class="gjs-tpl-icon"><i class="fa ' + tpl.icon + '"></i></div>' +
                '<div class="gjs-tpl-name">' + tpl.name + '</div>' +
                '<div class="gjs-tpl-cat">' + tpl.category + '</div>' +
            '</div>';
        });

        html += '</div>';

        modal.open({
            title: 'Choose a Template',
            content: html,
        });

        // Bind click events
        setTimeout(function() {
            var items = document.querySelectorAll('.gjs-tpl-item');
            items.forEach(function(item) {
                item.addEventListener('click', function() {
                    var idx = parseInt(item.getAttribute('data-tpl-index'));
                    var tpl = templates[idx];

                    var hasContent = editor.getHtml().replace(/<body[^>]*>|<\/body>/gi, '').trim().length > 0;
                    if (hasContent) {
                        if (!confirm('Replace existing content with "' + tpl.name + '" template?')) {
                            return;
                        }
                    }

                    editor.setComponents(tpl.html);
                    modal.close();

                    if (window.adminToast) {
                        window.adminToast('Template "' + tpl.name + '" applied.', 'success');
                    }
                });
            });
        }, 100);
    }

    return { apply: apply };
})();
