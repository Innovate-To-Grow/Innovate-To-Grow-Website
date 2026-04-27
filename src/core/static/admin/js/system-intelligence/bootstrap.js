(function() {
  'use strict';

  SI.activeConvoId = null;

  var els = {
    root: document.getElementById('si-root'),
    convoList: document.getElementById('si-convo-list'),
    messagesEl: document.getElementById('si-messages'),
    emptyEl: document.getElementById('si-empty'),
    inputBar: document.getElementById('si-input-bar'),
    input: document.getElementById('si-input'),
    sendBtn: document.getElementById('si-send-btn'),
    newBtn: document.getElementById('si-new-btn'),
  };

  var sidebar = SI.initSidebar(els);
  SI.sidebar = sidebar;
  SI.initStream(els, sidebar);
  if (SI.initCommands) SI.initCommands(els);
})();
