/**
 * System Intelligence — SSE streaming & message sending.
 *
 * Handles the streaming chat send flow: builds the assistant bubble,
 * processes SSE events (text / tool_call / usage / done / error),
 * and persists the final result.
 */
(function() {
  'use strict';

  var csrfToken = SI.csrfToken;
  var formatMarkdown = SI.formatMarkdown;
  var escapeHtml = SI.escapeHtml;
  var renderOneMessage = SI.renderOneMessage;
  var renderTokenBadge = SI.renderTokenBadge;
  var renderToolCallPill = SI.renderToolCallPill;

  function initStream(els, sidebar) {
    var root = els.root;
    var convoList = els.convoList;
    var messagesEl = els.messagesEl;
    var input = els.input;
    var sendBtn = els.sendBtn;

    var sending = false;

    function autoResize() {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    function sendMessage() {
      var text = input.value.trim();
      if (!text || sending || !SI.activeConvoId) return;

      sending = true;
      sendBtn.disabled = true;
      input.value = '';
      autoResize();

      var existingEmpty = messagesEl.querySelector('.si-empty');
      if (existingEmpty) existingEmpty.remove();
      messagesEl.insertAdjacentHTML('beforeend', renderOneMessage({role: 'user', content: text}));

      var streamId = 'stream-' + Date.now();
      messagesEl.insertAdjacentHTML('beforeend',
        '<div id="' + streamId + '-tools" class="si-tool-calls" style="display:none;"></div>' +
        '<div class="si-msg si-msg-assistant" id="' + streamId + '">' +
          '<div class="si-msg-avatar"><span class="material-symbols-outlined !text-[16px]">smart_toy</span></div>' +
          '<div class="si-msg-content">' +
            '<div class="si-msg-bubble si-typing-dots"><span></span><span></span><span></span></div>' +
            '<div class="si-token-usage si-token-live" id="' + streamId + '-usage" style="display:none;">' +
              '<span id="' + streamId + '-usage-text">0 tokens</span>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
      messagesEl.scrollTop = messagesEl.scrollHeight;

      var sendUrl = root.getAttribute('data-new-url').replace('/new/', '/' + SI.activeConvoId + '/send/');
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
              /* empty line separates events */
            } else {
              sseBuffer += line + '\n';
            }
          }
        }

        function handleSSEEvent(eventType, data) {
          if (eventType === 'text') {
            if (!bubbleStarted) {
              bubbleStarted = true;
              if (toolsContainer) {
                var actives = toolsContainer.querySelectorAll('.si-tool-call.is-active');
                for (var a = 0; a < actives.length; a++) actives[a].classList.remove('is-active');
              }
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
              var lastPill = toolsContainer.lastElementChild;
              if (lastPill) {
                lastPill.classList.add('is-expanded', 'is-active');
                lastPill.style.animation = 'si-tool-enter 0.35s ease both';
              }
              messagesEl.scrollTop = messagesEl.scrollHeight;
            }

          } else if (eventType === 'usage') {
            var usageEl = document.getElementById(streamId + '-usage');
            var usageText = document.getElementById(streamId + '-usage-text');
            if (usageEl) usageEl.style.display = '';
            if (usageText) {
              usageText.textContent =
                (data.inputTokens || 0).toLocaleString() + ' in / ' +
                (data.outputTokens || 0).toLocaleString() + ' out / ' +
                (data.totalTokens || 0).toLocaleString() + ' total';
            }

          } else if (eventType === 'done') {
            if (toolsContainer) {
              var pills = toolsContainer.querySelectorAll('.si-tool-call');
              for (var p = 0; p < pills.length; p++) {
                pills[p].classList.remove('is-expanded', 'is-active');
              }
            }
            if (data.title) {
              var item = convoList.querySelector('[data-convo-id="' + SI.activeConvoId + '"] .si-convo-title');
              if (item) item.textContent = data.title;
            }
            var liveUsage = document.getElementById(streamId + '-usage');
            if (liveUsage) {
              liveUsage.classList.remove('si-token-live');
              if (data.token_usage && data.token_usage.totalTokens) {
                liveUsage.innerHTML = renderTokenBadge(data.token_usage).replace(/^<div[^>]*>/, '').replace(/<\/div>$/, '');
                liveUsage.style.display = '';
              }
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
      }).catch(function() {
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

    // --- Bind input events ---
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
  }

  SI.initStream = initStream;
})();
