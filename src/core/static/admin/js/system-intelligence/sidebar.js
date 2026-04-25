/**
 * System Intelligence — sidebar (conversation list).
 *
 * Loads, renders, and handles clicks/deletes on conversations.
 */
(function() {
  'use strict';

  var api = SI.api;
  var escapeHtml = SI.escapeHtml;

  function initSidebar(els) {
    var root = els.root;
    var convoList = els.convoList;
    var messagesEl = els.messagesEl;
    var emptyEl = els.emptyEl;
    var inputBar = els.inputBar;
    var newBtn = els.newBtn;
    var updateContextUsage = SI.updateContextUsage;
    var latestContextUsage = SI.latestContextUsage;
    var replaceActionRequestCard = SI.replaceActionRequestCard;

    function loadConversations() {
      api(root.getAttribute('data-conversations-url')).then(function(data) {
        renderConversations(data.conversations || []);
      });
    }

    function renderConversations(convos) {
      if (!convos.length) {
        convoList.innerHTML = '<div class="p-4 text-center text-sm opacity-40">No conversations yet</div>';
        return;
      }
      var html = '';
      for (var i = 0; i < convos.length; i++) {
        var c = convos[i];
        var active = c.id === SI.activeConvoId ? ' is-active' : '';
        html += '<div class="si-convo-item' + active + '" data-convo-id="' + c.id + '">' +
          '<span class="material-symbols-outlined !text-[18px] opacity-40">chat_bubble_outline</span>' +
          '<span class="si-convo-title">' + escapeHtml(c.title) + '</span>' +
          '<span class="si-convo-date">' + c.updated_at + '</span>' +
          '<span class="si-convo-actions">' +
            '<button data-delete-convo="' + c.id + '" title="Delete"><span class="material-symbols-outlined !text-[16px]">delete</span></button>' +
          '</span>' +
        '</div>';
      }
      convoList.innerHTML = html;
    }

    function loadMessages(convoId) {
      SI.activeConvoId = convoId;
      emptyEl.style.display = 'none';
      inputBar.style.display = 'flex';
      updateContextUsage(null, {state: 'loading', detail: 'Loading...'});
      messagesEl.innerHTML = '<div class="si-empty"><span class="material-symbols-outlined !text-[24px] mb-2" style="animation:si-dot-pulse 1.2s infinite;">hourglass_empty</span><p class="text-sm">Loading...</p></div>';

      convoList.querySelectorAll('.si-convo-item').forEach(function(el) {
        el.classList.toggle('is-active', el.getAttribute('data-convo-id') === convoId);
      });

      var url = root.getAttribute('data-new-url').replace('/new/', '/' + convoId + '/');
      api(url).then(function(data) {
        if (data.error) {
          messagesEl.innerHTML = '<div class="p-4 text-sm text-red-600">' + escapeHtml(data.error) + '</div>';
          updateContextUsage(null, {state: 'empty', detail: 'Ready'});
          return;
        }
        renderMessages(data.messages || []);
      });
    }

    function renderMessages(msgs) {
      if (!msgs.length) {
        messagesEl.innerHTML = '<div class="si-empty"><span class="material-symbols-outlined !text-[48px] mb-3 opacity-30">chat</span><p class="text-sm opacity-40">Send a message to start the conversation</p></div>';
        updateContextUsage(null, {state: 'empty', detail: 'Ready'});
        return;
      }
      var html = '';
      for (var i = 0; i < msgs.length; i++) {
        html += SI.renderOneMessage(msgs[i]);
      }
      messagesEl.innerHTML = html;
      updateContextUsage(latestContextUsage(msgs), {state: 'ready'});
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // --- New chat button ---
    newBtn.addEventListener('click', function() {
      api(root.getAttribute('data-new-url'), {method: 'POST'}).then(function(data) {
        if (data.id) {
          loadConversations();
          loadMessages(data.id);
        }
      });
    });

    // --- Sidebar click delegation ---
    document.body.addEventListener('click', function(e) {
      var toolToggle = e.target.closest('[data-tool-toggle]');
      if (toolToggle) {
        toolToggle.classList.toggle('is-expanded');
        return;
      }

      var approveBtn = e.target.closest('[data-si-action-approve]');
      var rejectBtn = e.target.closest('[data-si-action-reject]');
      if (approveBtn || rejectBtn) {
        e.preventDefault();
        var actionId = (approveBtn || rejectBtn).getAttribute(approveBtn ? 'data-si-action-approve' : 'data-si-action-reject');
        var verb = approveBtn ? 'approve' : 'reject';
        if (!actionId) return;
        setActionButtonsDisabled(actionId, true);
        api(actionUrl(actionId, verb), {method: 'POST'}).then(function(data) {
          if (data.action_request) replaceActionRequestCard(data.action_request);
          if (data.error) alert(data.error);
        }).catch(function() {
          alert('Action request failed. Please try again.');
          setActionButtonsDisabled(actionId, false);
        });
        return;
      }

      var item = e.target.closest('.si-convo-item');
      var deleteBtn = e.target.closest('[data-delete-convo]');

      if (deleteBtn) {
        e.stopPropagation();
        var id = deleteBtn.getAttribute('data-delete-convo');
        if (!confirm('Delete this conversation?')) return;
        var deleteUrl = root.getAttribute('data-new-url').replace('/new/', '/' + id + '/delete/');
        api(deleteUrl, {method: 'POST'}).then(function() {
          if (SI.activeConvoId === id) {
            SI.activeConvoId = null;
            messagesEl.innerHTML = '';
            emptyEl.style.display = '';
            messagesEl.appendChild(emptyEl);
            inputBar.style.display = 'none';
            updateContextUsage(null, {state: 'empty', detail: 'Ready'});
          }
          loadConversations();
        });
        return;
      }

      if (item) {
        var id = item.getAttribute('data-convo-id');
        if (id) loadMessages(id);
      }
    });

    loadConversations();

    return {
      loadConversations: loadConversations,
      loadMessages: loadMessages,
    };

    function actionUrl(actionId, verb) {
      return root.getAttribute('data-new-url').replace('/new/', '/actions/' + actionId + '/' + verb + '/');
    }

    function setActionButtonsDisabled(actionId, disabled) {
      var card = document.querySelector('[data-si-action-id="' + CSS.escape(actionId) + '"]');
      if (!card) return;
      card.querySelectorAll('button').forEach(function(button) {
        button.disabled = disabled;
      });
    }
  }

  SI.initSidebar = initSidebar;
})();
