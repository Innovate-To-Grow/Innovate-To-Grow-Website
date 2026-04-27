(function() {
  'use strict';

  function initStream(els) {
    var sending = false;
    var input = els.input;
    var sendBtn = els.sendBtn;

    function autoResize() {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    }

    function sendMessageText(text, displayText) {
      text = (text || '').trim();
      if (!text) return false;
      return startStream({
        displayPrompt: (displayText || text).trim(),
        url: sendUrl(els.root),
        body: {message: text},
      });
    }

    function startStream(opts) {
      var displayPrompt = (opts && opts.displayPrompt || '').trim();
      if (!displayPrompt || sending || !SI.activeConvoId) return false;
      sending = true;
      sendBtn.disabled = true;
      input.value = '';
      autoResize();
      SI.updateContextUsage(null, {state: 'loading', detail: 'Preparing...'});
      appendUserAndStreamShell(els, displayPrompt);
      fetchStream(els, opts.url, opts.body).finally(function() {
        sending = false;
        sendBtn.disabled = !input.value.trim();
        input.focus();
      });
      return true;
    }

    function sendMessage() {
      var text = (input.value || '').trim();
      if (!text) return;
      if (SI.maybeInterceptSend && SI.maybeInterceptSend(text)) {
        input.value = '';
        autoResize();
        sendBtn.disabled = true;
        return;
      }
      sendMessageText(text);
    }

    function fillMessage(text) {
      input.value = text || '';
      autoResize();
      sendBtn.disabled = !input.value.trim() || sending;
      input.focus();
    }

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
    sendBtn.addEventListener('click', sendMessage);

    SI.sendSystemIntelligenceMessage = sendMessageText;
    SI.fillSystemIntelligenceMessage = fillMessage;
    SI.startStreamForCommand = startStream;
  }

  function appendUserAndStreamShell(els, text) {
    var existingEmpty = els.messagesEl.querySelector('.si-empty');
    if (existingEmpty) existingEmpty.remove();
    els.messagesEl.insertAdjacentHTML('beforeend', SI.renderOneMessage({role: 'user', content: text}));
    var streamId = 'stream-' + Date.now();
    els.currentStreamId = streamId;
    els.messagesEl.insertAdjacentHTML('beforeend', streamShell(streamId));
    els.messagesEl.scrollTop = els.messagesEl.scrollHeight;
  }

  function streamShell(streamId) {
    return '<div id="' + streamId + '-tools" class="si-tool-calls" style="display:none;"></div>' +
      '<div class="si-msg si-msg-assistant" id="' + streamId + '"><div class="si-msg-avatar">' +
      '<span class="material-symbols-outlined !text-[16px]">smart_toy</span></div><div class="si-msg-content">' +
      '<div class="si-msg-bubble si-typing-dots"><span></span><span></span><span></span></div>' +
      '<div class="si-token-usage si-token-live" id="' + streamId + '-usage" style="display:none;">' +
      '<span id="' + streamId + '-usage-text">0 tokens</span></div>' +
      '<div class="si-action-requests" id="' + streamId + '-actions"></div></div></div>';
  }

  function fetchStream(els, url, body) {
    var streamId = els.currentStreamId;
    var ctx = {
      streamId: streamId,
      convoList: els.convoList,
      messagesEl: els.messagesEl,
      toolsContainer: document.getElementById(streamId + '-tools'),
      actionsContainer: document.getElementById(streamId + '-actions'),
      contextUsage: null,
      rawText: '',
      bubbleStarted: false,
      bubbleEl: null,
    };
    return fetch(url, requestOptions(body))
      .then(validateResponse)
      .then(function(response) { return readSSE(response, SI.createStreamEventHandler(ctx)); })
      .catch(function() { networkError(ctx); });
  }

  function sendUrl(root) {
    return root.getAttribute('data-new-url').replace('/new/', '/' + SI.activeConvoId + '/send/');
  }

  function requestOptions(body) {
    return {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': SI.csrfToken(), 'X-Requested-With': 'XMLHttpRequest'},
      body: JSON.stringify(body || {}),
    };
  }

  function validateResponse(response) {
    if (!response.ok || !response.body) throw new Error('Stream request failed');
    return response;
  }

  function readSSE(response, handleEvent) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    function pump() {
      return reader.read().then(function(result) {
        if (result.done) return;
        buffer += decoder.decode(result.value, {stream: true});
        buffer = processSSEBuffer(buffer, handleEvent);
        return pump();
      });
    }
    return pump();
  }

  function processSSEBuffer(buffer, handleEvent) {
    var lines = buffer.split('\n');
    var nextBuffer = '';
    var currentEvent = '';
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (line.indexOf('event: ') === 0) {
        currentEvent = line.substring(7).trim();
      } else if (line.indexOf('data: ') === 0) {
        try {
          handleEvent(currentEvent, JSON.parse(line.substring(6)));
        } catch (e) {}
        currentEvent = '';
      } else if (line !== '') {
        nextBuffer += line + '\n';
      }
    }
    return nextBuffer;
  }

  function networkError(ctx) {
    var streamEl = document.getElementById(ctx.streamId);
    if (streamEl) streamEl.remove();
    if (ctx.toolsContainer) ctx.toolsContainer.remove();
    ctx.messagesEl.insertAdjacentHTML(
      'beforeend',
      '<div class="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg">Network error. Please try again.</div>'
    );
  }

  SI.initStream = initStream;
})();
