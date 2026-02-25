/**
 * GrapesJS Style Manager configuration with I2G brand theming.
 * Phase 4: Typography, Layout, Background, Border sectors + brand color palette.
 */
var gjsStyleConfig = (function() {
    'use strict';

    var I2G_COLORS = [
        '#003366', '#C4972F', '#52b5f7', '#1a1a2e',
        '#f5f5f5', '#ffffff', '#333333', '#666666',
        '#28a745', '#dc3545', '#ffc107', '#17a2b8',
    ];

    var FONT_OPTIONS = [
        { id: 'Inter, sans-serif',          label: 'Inter' },
        { id: 'Roboto, sans-serif',         label: 'Roboto' },
        { id: 'Open Sans, sans-serif',      label: 'Open Sans' },
        { id: 'Lato, sans-serif',           label: 'Lato' },
        { id: 'Montserrat, sans-serif',     label: 'Montserrat' },
        { id: 'Poppins, sans-serif',        label: 'Poppins' },
        { id: 'Georgia, serif',             label: 'Georgia' },
        { id: 'Times New Roman, serif',     label: 'Times New Roman' },
        { id: 'Arial, sans-serif',          label: 'Arial' },
        { id: 'Helvetica, sans-serif',      label: 'Helvetica' },
        { id: 'system-ui, sans-serif',      label: 'System Default' },
    ];

    var sectors = [
        {
            name: 'Typography',
            open: true,
            properties: [
                {
                    name: 'Font Family',
                    property: 'font-family',
                    type: 'select',
                    options: FONT_OPTIONS,
                },
                {
                    name: 'Font Size',
                    property: 'font-size',
                    type: 'select',
                    options: [
                        { id: '12px', label: '12px' },
                        { id: '14px', label: '14px' },
                        { id: '16px', label: '16px (base)' },
                        { id: '18px', label: '18px' },
                        { id: '20px', label: '20px' },
                        { id: '24px', label: '24px' },
                        { id: '30px', label: '30px' },
                        { id: '36px', label: '36px' },
                        { id: '48px', label: '48px' },
                        { id: '64px', label: '64px' },
                    ],
                },
                {
                    name: 'Font Weight',
                    property: 'font-weight',
                    type: 'select',
                    options: [
                        { id: '300', label: 'Light' },
                        { id: '400', label: 'Regular' },
                        { id: '500', label: 'Medium' },
                        { id: '600', label: 'Semi-Bold' },
                        { id: '700', label: 'Bold' },
                    ],
                },
                {
                    name: 'Line Height',
                    property: 'line-height',
                    type: 'select',
                    options: [
                        { id: '1',   label: '1 (tight)' },
                        { id: '1.2', label: '1.2' },
                        { id: '1.4', label: '1.4' },
                        { id: '1.5', label: '1.5 (normal)' },
                        { id: '1.6', label: '1.6' },
                        { id: '1.8', label: '1.8' },
                        { id: '2',   label: '2 (loose)' },
                    ],
                },
                { name: 'Letter Spacing', property: 'letter-spacing', type: 'number', units: ['px', 'em'] },
                {
                    name: 'Text Align',
                    property: 'text-align',
                    type: 'radio',
                    options: [
                        { id: 'left',    label: 'L' },
                        { id: 'center',  label: 'C' },
                        { id: 'right',   label: 'R' },
                        { id: 'justify', label: 'J' },
                    ],
                },
                {
                    name: 'Text Transform',
                    property: 'text-transform',
                    type: 'select',
                    options: [
                        { id: 'none',       label: 'None' },
                        { id: 'uppercase',  label: 'UPPERCASE' },
                        { id: 'lowercase',  label: 'lowercase' },
                        { id: 'capitalize', label: 'Capitalize' },
                    ],
                },
                { name: 'Color', property: 'color', type: 'color' },
                {
                    name: 'Text Decoration',
                    property: 'text-decoration',
                    type: 'select',
                    options: [
                        { id: 'none',         label: 'None' },
                        { id: 'underline',    label: 'Underline' },
                        { id: 'line-through', label: 'Line-through' },
                    ],
                },
            ],
        },
        {
            name: 'Layout',
            open: false,
            properties: [
                {
                    name: 'Display',
                    property: 'display',
                    type: 'select',
                    options: [
                        { id: 'block',        label: 'Block' },
                        { id: 'flex',         label: 'Flex' },
                        { id: 'grid',         label: 'Grid' },
                        { id: 'inline-block', label: 'Inline Block' },
                        { id: 'inline',       label: 'Inline' },
                        { id: 'none',         label: 'None' },
                    ],
                },
                {
                    name: 'Flex Direction',
                    property: 'flex-direction',
                    type: 'select',
                    options: [
                        { id: 'row',            label: 'Row' },
                        { id: 'column',         label: 'Column' },
                        { id: 'row-reverse',    label: 'Row Reverse' },
                        { id: 'column-reverse', label: 'Column Reverse' },
                    ],
                },
                {
                    name: 'Justify Content',
                    property: 'justify-content',
                    type: 'select',
                    options: [
                        { id: 'flex-start',    label: 'Start' },
                        { id: 'center',        label: 'Center' },
                        { id: 'flex-end',      label: 'End' },
                        { id: 'space-between', label: 'Space Between' },
                        { id: 'space-around',  label: 'Space Around' },
                    ],
                },
                {
                    name: 'Align Items',
                    property: 'align-items',
                    type: 'select',
                    options: [
                        { id: 'stretch',    label: 'Stretch' },
                        { id: 'flex-start', label: 'Start' },
                        { id: 'center',     label: 'Center' },
                        { id: 'flex-end',   label: 'End' },
                        { id: 'baseline',   label: 'Baseline' },
                    ],
                },
                { name: 'Gap', property: 'gap', type: 'number', units: ['px', '%', 'em', 'rem'] },
                { name: 'Flex Wrap', property: 'flex-wrap', type: 'select', options: [
                    { id: 'nowrap', label: 'No Wrap' }, { id: 'wrap', label: 'Wrap' },
                ]},
                { name: 'Width',      property: 'width',      type: 'number', units: ['px', '%', 'vw', 'auto'] },
                { name: 'Height',     property: 'height',     type: 'number', units: ['px', '%', 'vh', 'auto'] },
                { name: 'Max Width',  property: 'max-width',  type: 'number', units: ['px', '%', 'vw', 'none'] },
                { name: 'Min Height', property: 'min-height', type: 'number', units: ['px', '%', 'vh'] },
                {
                    name: 'Overflow',
                    property: 'overflow',
                    type: 'select',
                    options: [
                        { id: 'visible', label: 'Visible' },
                        { id: 'hidden',  label: 'Hidden' },
                        { id: 'auto',    label: 'Auto' },
                        { id: 'scroll',  label: 'Scroll' },
                    ],
                },
                { name: 'Position', property: 'position', type: 'select', options: [
                    { id: 'static', label: 'Static' }, { id: 'relative', label: 'Relative' },
                    { id: 'absolute', label: 'Absolute' }, { id: 'fixed', label: 'Fixed' },
                    { id: 'sticky', label: 'Sticky' },
                ]},
            ],
        },
        {
            name: 'Spacing',
            open: false,
            properties: [
                { name: 'Margin',  property: 'margin',  type: 'composite', properties: [
                    { name: 'Top',    property: 'margin-top',    type: 'number', units: ['px', '%', 'em', 'rem', 'auto'] },
                    { name: 'Right',  property: 'margin-right',  type: 'number', units: ['px', '%', 'em', 'rem', 'auto'] },
                    { name: 'Bottom', property: 'margin-bottom', type: 'number', units: ['px', '%', 'em', 'rem', 'auto'] },
                    { name: 'Left',   property: 'margin-left',   type: 'number', units: ['px', '%', 'em', 'rem', 'auto'] },
                ]},
                { name: 'Padding', property: 'padding', type: 'composite', properties: [
                    { name: 'Top',    property: 'padding-top',    type: 'number', units: ['px', '%', 'em', 'rem'] },
                    { name: 'Right',  property: 'padding-right',  type: 'number', units: ['px', '%', 'em', 'rem'] },
                    { name: 'Bottom', property: 'padding-bottom', type: 'number', units: ['px', '%', 'em', 'rem'] },
                    { name: 'Left',   property: 'padding-left',   type: 'number', units: ['px', '%', 'em', 'rem'] },
                ]},
            ],
        },
        {
            name: 'Background',
            open: false,
            properties: [
                { name: 'Background Color', property: 'background-color', type: 'color' },
            ],
        },
        {
            name: 'Border',
            open: false,
            properties: [
                { name: 'Border Width',  property: 'border-width',  type: 'number', units: ['px'] },
                { name: 'Border Style',  property: 'border-style',  type: 'select', options: [
                    { id: 'none', label: 'None' }, { id: 'solid', label: 'Solid' },
                    { id: 'dashed', label: 'Dashed' }, { id: 'dotted', label: 'Dotted' },
                    { id: 'double', label: 'Double' },
                ]},
                { name: 'Border Color',  property: 'border-color',  type: 'color' },
                { name: 'Border Radius', property: 'border-radius', type: 'composite', properties: [
                    { name: 'TL', property: 'border-top-left-radius',     type: 'number', units: ['px', '%'] },
                    { name: 'TR', property: 'border-top-right-radius',    type: 'number', units: ['px', '%'] },
                    { name: 'BR', property: 'border-bottom-right-radius', type: 'number', units: ['px', '%'] },
                    { name: 'BL', property: 'border-bottom-left-radius',  type: 'number', units: ['px', '%'] },
                ]},
                { name: 'Box Shadow', property: 'box-shadow', type: 'stack', properties: [
                    { name: 'X',      property: 'box-shadow-h',      type: 'number', units: ['px'], defaults: '0' },
                    { name: 'Y',      property: 'box-shadow-v',      type: 'number', units: ['px'], defaults: '2' },
                    { name: 'Blur',   property: 'box-shadow-blur',   type: 'number', units: ['px'], defaults: '8' },
                    { name: 'Spread', property: 'box-shadow-spread', type: 'number', units: ['px'], defaults: '0' },
                    { name: 'Color',  property: 'box-shadow-color',  type: 'color', defaults: 'rgba(0,0,0,0.1)' },
                ]},
            ],
        },
        {
            name: 'Extra',
            open: false,
            properties: [
                { name: 'Opacity',    property: 'opacity',    type: 'slider', min: 0, max: 1, step: 0.05 },
                { name: 'Cursor',     property: 'cursor',     type: 'select', options: [
                    { id: 'auto', label: 'Auto' }, { id: 'pointer', label: 'Pointer' },
                    { id: 'default', label: 'Default' }, { id: 'not-allowed', label: 'Not Allowed' },
                ]},
                { name: 'Transition', property: 'transition', type: 'base', defaults: 'all 0.3s ease' },
            ],
        },
    ];

    function apply(editor) {
        // Populate the color picker palette with I2G brand colors
        try {
            var config = editor.getConfig();
            var picker = config && config.colorPicker;
            if (picker) {
                var existing = picker.palette || [];
                var merged = existing.slice();
                I2G_COLORS.forEach(function(c) {
                    if (merged.indexOf(c) === -1) merged.push(c);
                });
                picker.palette = merged;
            }
        } catch (e) {
            // Color picker API may not be available — non-critical
        }
    }

    return { sectors: sectors, apply: apply };
})();
