(function() {
  'use strict';

  var root = document.getElementById('si-root');
  var convoList = document.getElementById('si-convo-list');
  var messagesEl = document.getElementById('si-messages');
  var emptyEl = document.getElementById('si-empty');
  var inputBar = document.getElementById('si-input-bar');
  var input = document.getElementById('si-input');
  var sendBtn = document.getElementById('si-send-btn');
  var newBtn = document.getElementById('si-new-btn');

  var activeConvoId = null;
  var sending = false;

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function api(url, opts) {
    opts = opts || {};
    opts.credentials = 'same-origin';
    opts.headers = Object.assign({'X-Requested-With': 'XMLHttpRequest'}, opts.headers || {});
    if (opts.json) {
      opts.body = JSON.stringify(opts.json);
      opts.headers['Content-Type'] = 'application/json';
      opts.method = opts.method || 'POST';
      delete opts.json;
    }
    if (opts.method === 'POST' || opts.method === 'DELETE') {
      opts.headers['X-CSRFToken'] = csrfToken();
    }
    return fetch(url, opts).then(function(r) { return r.json(); });
  }

  // --- Conversation list ---

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
      var active = c.id === activeConvoId ? ' is-active' : '';
      html += '<div class="si-convo-item' + active + '" data-convo-id="' + c.id + '">' +
        '<span class="material-symbols-outlined !text-[18px] opacity-40">chat_bubble_outline</span>' +
        '<span class="si-convo-title">' + escapeHtml(c.title) + '</span>' +
        '<span class="si-convo-date">' + c.updated_at + '</span>' +
        '<span class="si-convo-actions">' +
          '<button data-rename-convo="' + c.id + '" title="Rename"><span class="material-symbols-outlined !text-[16px]">edit</span></button>' +
          '<button data-delete-convo="' + c.id + '" title="Delete"><span class="material-symbols-outlined !text-[16px]">delete</span></button>' +
        '</span>' +
      '</div>';
    }
    convoList.innerHTML = html;
  }

  function escapeHtml(str) {
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  // --- Messages ---

  function loadMessages(convoId) {
    activeConvoId = convoId;
    emptyEl.style.display = 'none';
    inputBar.style.display = 'flex';
    messagesEl.innerHTML = '<div class="si-empty"><span class="material-symbols-outlined !text-[24px] mb-2" style="animation:si-dot-pulse 1.2s infinite;">hourglass_empty</span><p class="text-sm">Loading...</p></div>';

    // highlight active in sidebar
    convoList.querySelectorAll('.si-convo-item').forEach(function(el) {
      el.classList.toggle('is-active', el.getAttribute('data-convo-id') === convoId);
    });

    var url = root.getAttribute('data-new-url').replace('/new/', '/' + convoId + '/');
    api(url).then(function(data) {
      if (data.error) {
        messagesEl.innerHTML = '<div class="p-4 text-sm text-red-600">' + escapeHtml(data.error) + '</div>';
        return;
      }
      renderMessages(data.messages || []);
    });
  }

  function renderMessages(msgs) {
    if (!msgs.length) {
      messagesEl.innerHTML = '<div class="si-empty"><span class="material-symbols-outlined !text-[48px] mb-3 opacity-30">chat</span><p class="text-sm opacity-40">Send a message to start the conversation</p></div>';
      return;
    }
    var html = '';
    for (var i = 0; i < msgs.length; i++) {
      html += renderOneMessage(msgs[i]);
    }
    messagesEl.innerHTML = html;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function renderOneMessage(m) {
    var cls = m.role === 'user' ? 'si-msg-user' : 'si-msg-assistant';
    var avatar = m.role === 'user'
      ? '<span class="material-symbols-outlined !text-[16px]">person</span>'
      : '<span class="material-symbols-outlined !text-[16px]">smart_toy</span>';
    var content = m.role === 'assistant' ? formatMarkdown(m.content) : escapeHtml(m.content);

    var toolCallsHtml = '';
    if (m.tool_calls && m.tool_calls.length) {
      toolCallsHtml = '<div class="si-tool-calls">';
      for (var t = 0; t < m.tool_calls.length; t++) {
        toolCallsHtml += renderToolCallPill(m.tool_calls[t]);
      }
      toolCallsHtml += '</div>';
    }

    return toolCallsHtml +
      '<div class="si-msg ' + cls + '">' +
        '<div class="si-msg-avatar">' + avatar + '</div>' +
        '<div class="si-msg-bubble">' + content + '</div>' +
      '</div>';
  }

  function renderToolCallPill(tc) {
    var paramStr = '';
    if (tc.input) {
      var keys = Object.keys(tc.input);
      var parts = [];
      for (var k = 0; k < keys.length; k++) {
        parts.push(keys[k] + ': ' + JSON.stringify(tc.input[keys[k]]));
      }
      paramStr = parts.join(', ');
    }
    var displayName = tc.name.replace(/_/g, ' ');
    var preview = tc.result_preview || '';
    // Format the preview: try to show row count prominently
    var countMatch = preview.match(/^(Showing \d+ of \d+ result\(s\)|Count: \d+|Registration count: \d+|Total[^.]*: \d+)/);
    var summaryLine = countMatch ? countMatch[1] : '';
    var detailText = summaryLine ? preview.substring(summaryLine.length).trim() : preview;
    return '<div class="si-tool-call" data-tool-toggle>' +
      '<span class="material-symbols-outlined !text-[15px] si-tool-call-icon">manage_search</span>' +
      '<span class="si-tool-call-name">' + escapeHtml(displayName) + '</span>' +
      (paramStr ? '<span class="si-tool-call-params">' + escapeHtml(paramStr) + '</span>' : '') +
      '<span class="material-symbols-outlined !text-[16px] si-tool-call-arrow">expand_more</span>' +
      '<div class="si-tool-call-detail">' +
        (summaryLine ? '<strong>' + escapeHtml(summaryLine) + '</strong>\n' : '') +
        escapeHtml(detailText) +
      '</div>' +
    '</div>';
  }

  function formatMarkdown(text) {
    // Lightweight markdown: code blocks, inline code, bold, italic, paragraphs
    var escaped = escapeHtml(text);

    // Code blocks: ```...```
    escaped = escaped.replace(/```(\w*)\n?([\s\S]*?)```/g, function(_, lang, code) {
      return '<pre><code>' + code.trim() + '</code></pre>';
    });

    // Inline code: `...`
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold: **...**
    escaped = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic: *...*
    escaped = escaped.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

    // Paragraphs
    escaped = escaped.replace(/\n\n+/g, '</p><p>');
    escaped = escaped.replace(/\n/g, '<br>');
    escaped = '<p>' + escaped + '</p>';

    return escaped;
  }

  // --- Sending (streaming SSE) ---

  function sendMessage() {
    var text = input.value.trim();
    if (!text || sending || !activeConvoId) return;

    sending = true;
    sendBtn.disabled = true;
    input.value = '';
    autoResize();

    var existingEmpty = messagesEl.querySelector('.si-empty');
    if (existingEmpty) existingEmpty.remove();
    messagesEl.insertAdjacentHTML('beforeend', renderOneMessage({role: 'user', content: text}));

    // Create a tool-calls container and an empty assistant bubble
    var streamId = 'stream-' + Date.now();
    messagesEl.insertAdjacentHTML('beforeend',
      '<div id="' + streamId + '-tools" class="si-tool-calls" style="display:none;"></div>' +
      '<div class="si-msg si-msg-assistant" id="' + streamId + '">' +
        '<div class="si-msg-avatar"><span class="material-symbols-outlined !text-[16px]">smart_toy</span></div>' +
        '<div class="si-msg-bubble si-typing-dots"><span></span><span></span><span></span></div>' +
      '</div>'
    );
    messagesEl.scrollTop = messagesEl.scrollHeight;

    var sendUrl = root.getAttribute('data-new-url').replace('/new/', '/' + activeConvoId + '/send/');
    var rawText = '';
    var bubbleStarted = false;
    var bubbleEl = null;
    var toolsContainer = document.getElementById(streamId + '-tools');

    fetch(sendUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({message: text}),
    }).then(function(response) {
      if (!response.ok || !response.body) {
        throw new Error('Stream request failed');
      }
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var sseBuffer = '';

      function pump() {
        return reader.read().then(function(result) {
          if (result.done) return;
          sseBuffer += decoder.decode(result.value, {stream: true});
          processSSEBuffer();
          return pump();
        });
      }

      function processSSEBuffer() {
        var lines = sseBuffer.split('\n');
        sseBuffer = '';
        var currentEvent = '';
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (line.indexOf('event: ') === 0) {
            currentEvent = line.substring(7).trim();
          } else if (line.indexOf('data: ') === 0) {
            var dataStr = line.substring(6);
            try {
              var data = JSON.parse(dataStr);
              handleSSEEvent(currentEvent, data);
            } catch (e) {}
            currentEvent = '';
          } else if (line === '') {
            // empty line separates events — already handled above
          } else {
            sseBuffer += line + '\n';
          }
        }
      }

      function handleSSEEvent(eventType, data) {
        if (eventType === 'text') {
          if (!bubbleStarted) {
            bubbleStarted = true;
            var streamEl = document.getElementById(streamId);
            if (streamEl) {
              bubbleEl = streamEl.querySelector('.si-msg-bubble');
              if (bubbleEl) {
                bubbleEl.classList.remove('si-typing-dots');
                bubbleEl.innerHTML = '';
              }
            }
          }
          rawText += data.chunk;
          if (bubbleEl) {
            bubbleEl.innerHTML = formatMarkdown(rawText);
          }
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (eventType === 'tool_call') {
          if (toolsContainer) {
            toolsContainer.style.display = 'flex';
            toolsContainer.insertAdjacentHTML('beforeend', renderToolCallPill(data));
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        } else if (eventType === 'done') {
          if (data.title) {
            var item = convoList.querySelector('[data-convo-id="' + activeConvoId + '"] .si-convo-title');
            if (item) item.textContent = data.title;
          }
        } else if (eventType === 'error') {
          var streamEl = document.getElementById(streamId);
          if (streamEl) streamEl.remove();
          messagesEl.insertAdjacentHTML('beforeend',
            '<div class="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg">' + escapeHtml(data.error) + '</div>'
          );
        }
      }

      return pump();
    }).catch(function(err) {
      var streamEl = document.getElementById(streamId);
      if (streamEl) streamEl.remove();
      if (toolsContainer) toolsContainer.remove();
      messagesEl.insertAdjacentHTML('beforeend',
        '<div class="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg">Network error. Please try again.</div>'
      );
    }).finally(function() {
      sending = false;
      sendBtn.disabled = !input.value.trim();
      input.focus();
    });
  }

  // --- Auto-resize textarea ---
  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  // --- Event listeners ---

  newBtn.addEventListener('click', function() {
    api(root.getAttribute('data-new-url'), {method: 'POST'}).then(function(data) {
      if (data.id) {
        loadConversations();
        loadMessages(data.id);
      }
    });
  });

  input.addEventListener('input', function() {
    sendBtn.disabled = !input.value.trim() || sending;
    autoResize();
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener('click', function() {
    sendMessage();
  });

  document.body.addEventListener('click', function(e) {
    // Tool call toggle
    var toolToggle = e.target.closest('[data-tool-toggle]');
    if (toolToggle) {
      toolToggle.classList.toggle('is-expanded');
      return;
    }

    // Conversation click
    var item = e.target.closest('.si-convo-item');
    var deleteBtn = e.target.closest('[data-delete-convo]');
    var renameBtn = e.target.closest('[data-rename-convo]');

    if (deleteBtn) {
      e.stopPropagation();
      var id = deleteBtn.getAttribute('data-delete-convo');
      if (!confirm('Delete this conversation?')) return;
      var deleteUrl = root.getAttribute('data-new-url').replace('/new/', '/' + id + '/delete/');
      api(deleteUrl, {method: 'POST'}).then(function() {
        if (activeConvoId === id) {
          activeConvoId = null;
          messagesEl.innerHTML = '';
          emptyEl.style.display = '';
          messagesEl.appendChild(emptyEl);
          inputBar.style.display = 'none';
        }
        loadConversations();
      });
      return;
    }

    if (renameBtn) {
      e.stopPropagation();
      var id = renameBtn.getAttribute('data-rename-convo');
      var titleEl = renameBtn.closest('.si-convo-item').querySelector('.si-convo-title');
      var current = titleEl ? titleEl.textContent : '';
      var newTitle = prompt('Rename conversation:', current);
      if (newTitle && newTitle.trim()) {
        var renameUrl = root.getAttribute('data-new-url').replace('/new/', '/' + id + '/rename/');
        api(renameUrl, {method: 'POST', json: {title: newTitle.trim()}}).then(function(data) {
          if (data.ok && titleEl) titleEl.textContent = data.title;
        });
      }
      return;
    }

    if (item && !deleteBtn && !renameBtn) {
      var id = item.getAttribute('data-convo-id');
      if (id) loadMessages(id);
    }
  });

  // Initial load
  loadConversations();
})();
