/**
 * System Intelligence — application entry point.
 *
 * Gathers DOM references, initialises the sidebar and stream modules.
 * Must be loaded after si-utils.js, si-render.js, si-sidebar.js, si-stream.js.
 */
(function() {
  'use strict';

  SI.activeConvoId = null;

  var els = {
    root:       document.getElementById('si-root'),
    convoList:  document.getElementById('si-convo-list'),
    messagesEl: document.getElementById('si-messages'),
    emptyEl:    document.getElementById('si-empty'),
    inputBar:   document.getElementById('si-input-bar'),
    input:      document.getElementById('si-input'),
    sendBtn:    document.getElementById('si-send-btn'),
    newBtn:     document.getElementById('si-new-btn'),
  };

  var sidebar = SI.initSidebar(els);
  SI.initStream(els, sidebar);
})();
