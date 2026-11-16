(function () {
    'use strict';

    // Site Settings: edit the custom CSS with CodeMirror (CSS mode). fromTextArea writes the
    // editor's text back into the textarea when the form submits, so the server sees no change.
    var textarea = document.getElementById('id_custom_css');
    if (!textarea || typeof window.CodeMirror !== 'function') return;

    var wrapper = document.createElement('div');
    wrapper.className = 'itg-custom-css-editor';
    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);

    window.CodeMirror.fromTextArea(textarea, {
        mode: 'css',
        lineNumbers: true,
        lineWrapping: true,
        indentUnit: 2,
        tabSize: 2,
    });
})();
