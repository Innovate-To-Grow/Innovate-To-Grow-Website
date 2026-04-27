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
          if (SI.setPlanMode) SI.setPlanMode(false);
          return;
        }
        if (SI.setPlanMode) SI.setPlanMode(data.mode === 'plan');
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
          if (SI.setPlanMode) SI.setPlanMode(false);
          loadConversations();
          loadMessages(data.id);
        }
      });
    });

    // --- Sidebar click delegation ---
    document.body.addEventListener('click', function(e) {
      var confirmationSendBtn = e.target.closest('[data-si-confirmation-send]');
      if (confirmationSendBtn) {
        e.preventDefault();
        handleConfirmationSend(confirmationSendBtn);
        return;
      }

      var confirmationFillBtn = e.target.closest('[data-si-confirmation-fill]');
      if (confirmationFillBtn) {
        e.preventDefault();
        handleConfirmationFill(confirmationFillBtn);
        return;
      }

      var toolToggle = e.target.closest('[data-tool-toggle]');
      if (toolToggle) {
        toolToggle.classList.toggle('is-expanded');
        return;
      }

      var previewBtn = e.target.closest('[data-si-action-preview]');
      if (previewBtn) {
        e.preventDefault();
        toggleActionPreview(previewBtn);
        return;
      }

      var approveBtn = e.target.closest('[data-si-action-approve]');
      var rejectBtn = e.target.closest('[data-si-action-reject]');
      if (approveBtn || rejectBtn) {
        e.preventDefault();
        var actionId = (approveBtn || rejectBtn).getAttribute(approveBtn ? 'data-si-action-approve' : 'data-si-action-reject');
        var verb = approveBtn ? 'approve' : 'reject';
        if (!actionId) return;
        if (approveBtn) {
          var actionCard = approveBtn.closest('[data-si-action-id]');
          var actionType = actionCard && actionCard.getAttribute('data-si-action-type');
          if (actionType === 'db_delete' && !confirm('Delete this record? This cannot be undone.')) return;
        }
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

    function handleConfirmationSend(button) {
      if (!SI.sendSystemIntelligenceMessage) return;
      var text = decodeURIComponent(button.getAttribute('data-si-confirmation-send') || '');
      var displayText = decodeURIComponent(button.getAttribute('data-si-confirmation-display') || '');
      if (!text) return;
      if (SI.sendSystemIntelligenceMessage(text, displayText || text)) markConfirmationChosen(button);
    }

    function handleConfirmationFill(button) {
      if (!SI.fillSystemIntelligenceMessage) return;
      var text = decodeURIComponent(button.getAttribute('data-si-confirmation-fill') || '');
      if (!text) return;
      SI.fillSystemIntelligenceMessage(text);
      markConfirmationChosen(button, false);
    }

    function markConfirmationChosen(button, disable) {
      var card = button.closest('.si-confirmation-card');
      if (!card) return;
      card.querySelectorAll('[data-si-confirmation-send], [data-si-confirmation-fill]').forEach(function(item) {
        item.disabled = disable !== false;
      });
      card.querySelectorAll('.si-confirmation-option').forEach(function(item) {
        item.classList.toggle('is-selected', item.contains(button));
      });
    }

    var SAFE_PREVIEW_PATH_RE = /^\/admin\/[A-Za-z0-9_\/-]+\/preview\/?$/;
    var SAFE_ACTION_ID_RE = /^[A-Za-z0-9-]{1,64}$/;

    function actionPreviewUrl(actionId, iframe) {
      if (actionId && SAFE_ACTION_ID_RE.test(actionId)) {
        var base = root.getAttribute('data-new-url') || '';
        var candidate = base.replace('/new/', '/actions/' + actionId + '/preview/');
        if (SAFE_PREVIEW_PATH_RE.test(candidate)) return candidate;
      }
      var external = iframe.getAttribute('data-si-preview-external-src') || '';
      return SAFE_PREVIEW_PATH_RE.test(external) ? external : 'about:blank';
    }

    function setActionButtonsDisabled(actionId, disabled) {
      var card = document.querySelector('[data-si-action-id="' + CSS.escape(actionId) + '"]');
      if (!card) return;
      card.querySelectorAll('button').forEach(function(button) {
        button.disabled = disabled;
      });
    }

    function toggleActionPreview(button) {
      var card = button.closest('[data-si-action-id]');
      var panel = card ? card.querySelector('[data-si-preview-panel]') : null;
      var iframe = panel ? panel.querySelector('[data-si-preview-frame]') : null;
      if (!panel || !iframe) return;

      var shouldOpen = panel.hidden;
      panel.hidden = !shouldOpen;
      button.setAttribute('aria-expanded', shouldOpen ? 'true' : 'false');
      button.classList.toggle('is-active', shouldOpen);

      if (shouldOpen && !iframe.getAttribute('src')) {
        iframe.addEventListener('load', function() {
          resizeActionPreviewFrame(iframe);
          setTimeout(function() { resizeActionPreviewFrame(iframe); }, 250);
          setTimeout(function() { resizeActionPreviewFrame(iframe); }, 900);
        }, {once: true});
        iframe.setAttribute('src', actionPreviewUrl(card.getAttribute('data-si-action-id'), iframe));
      }
      if (shouldOpen) resizeActionPreviewFrame(iframe);
      if (shouldOpen) {
        setTimeout(function() {
          messagesEl.scrollTop = Math.min(messagesEl.scrollHeight, card.offsetTop + panel.offsetTop - 12);
        }, 0);
      }
    }

    function resizeActionPreviewFrame(iframe) {
      try {
        var doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
        if (!doc || !doc.body) return;
        var height = Math.max(
          doc.body.scrollHeight,
          doc.documentElement ? doc.documentElement.scrollHeight : 0,
          180
        );
        iframe.style.height = Math.min(height + 2, 520) + 'px';
      } catch (e) {
        iframe.style.height = '260px';
      }
    }
  }

  SI.initSidebar = initSidebar;
})();
