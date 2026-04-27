/**
 * System Intelligence — slash-command palette.
 *
 * Adds Claude-Code-style "/" command discovery + dispatch above the chat input:
 *   /plan <prompt>   — toggle plan mode (no write tools) and stream a plan
 *   /compact         — force-summarize older context to free up tokens
 *
 * Public surface (attached to SI):
 *   SI.initCommands(els)            wire up palette + plan-mode banner
 *   SI.maybeInterceptSend(text)     called by stream.js sendMessage; returns
 *                                   true if `text` was a recognized command
 *                                   (already dispatched) so the caller skips
 *                                   the normal /send path
 *   SI.setPlanMode(active)          show/hide the persistent plan-mode banner
 */
(function() {
  'use strict';

  var COMMANDS = [
    {
      command: 'plan',
      name: '/plan',
      description: 'Plan first — agent designs without running write tools. Approve to execute.',
      usage: '/plan <what you want to do>',
      requiresArgs: false,
    },
    {
      command: 'compact',
      name: '/compact',
      description: 'Summarize older messages to free up the conversation’s context window.',
      usage: '/compact',
      requiresArgs: false,
    },
    {
      command: 'retry',
      name: '/retry',
      description: 'Re-run the last user message (drops the previous assistant reply).',
      usage: '/retry',
      requiresArgs: false,
    },
    {
      command: 'title',
      name: '/title',
      description: 'Rename the current conversation.',
      usage: '/title <new title>',
      requiresArgs: true,
    },
    {
      command: 'new',
      name: '/new',
      description: 'Start a fresh conversation.',
      usage: '/new',
      requiresArgs: false,
    },
    {
      command: 'help',
      name: '/help',
      description: 'List all available slash commands.',
      usage: '/help',
      requiresArgs: false,
    },
  ];

  var COMMAND_INDEX = COMMANDS.reduce(function(acc, cmd) { acc[cmd.command] = cmd; return acc; }, {});

  var state = {
    els: null,
    paletteEl: null,
    bannerEl: null,
    activeIndex: 0,
    visibleCommands: [],
    planActive: false,
  };

  function initCommands(els) {
    state.els = els;
    ensurePalette(els);
    ensureBanner(els);
    bindEvents(els);
  }

  function ensurePalette(els) {
    if (state.paletteEl) return;
    els.inputBar.style.position = 'relative';
    var palette = document.createElement('div');
    palette.className = 'si-command-palette';
    palette.setAttribute('role', 'listbox');
    palette.hidden = true;
    els.inputBar.appendChild(palette);
    state.paletteEl = palette;
  }

  function ensureBanner(els) {
    if (state.bannerEl) return;
    var banner = document.createElement('div');
    banner.className = 'si-plan-mode-banner';
    banner.hidden = true;
    banner.innerHTML =
      '<span class="material-symbols-outlined !text-[18px]">edit_note</span>' +
      '<span class="si-plan-mode-text">' +
        '<strong>Plan mode active.</strong> ' +
        'The agent is designing without running write tools. Iterate freely, then exit to execute.' +
      '</span>' +
      '<button type="button" class="si-plan-mode-exit" data-si-plan-exit>Exit plan & execute</button>';
    var main = els.messagesEl && els.messagesEl.parentNode;
    if (main) main.insertBefore(banner, els.messagesEl);
    state.bannerEl = banner;
  }

  function bindEvents(els) {
    var input = els.input;
    input.addEventListener('input', handleInput);
    input.addEventListener('keydown', handlePaletteKeydown, true);
    input.addEventListener('blur', function() {
      // Defer so click on a palette item still registers.
      setTimeout(hidePalette, 120);
    });
    state.paletteEl.addEventListener('mousedown', function(e) {
      var item = e.target.closest('[data-si-command]');
      if (!item) return;
      e.preventDefault();
      var cmd = item.getAttribute('data-si-command');
      selectCommand(cmd);
    });
    state.bannerEl.addEventListener('click', function(e) {
      if (e.target.closest('[data-si-plan-exit]')) {
        e.preventDefault();
        exitPlanMode();
      }
    });
  }

  function handleInput() {
    var text = state.els.input.value;
    if (!shouldShowPalette(text)) {
      hidePalette();
      return;
    }
    var query = text.slice(1).split(/\s/, 1)[0].toLowerCase();
    var hasArgs = /\s/.test(text.slice(1));
    if (hasArgs) {
      hidePalette();
      return;
    }
    state.visibleCommands = COMMANDS.filter(function(cmd) {
      return cmd.command.indexOf(query) === 0;
    });
    if (!state.visibleCommands.length) {
      hidePalette();
      return;
    }
    state.activeIndex = 0;
    renderPalette();
  }

  function shouldShowPalette(text) {
    return typeof text === 'string' && text.charAt(0) === '/';
  }

  function renderPalette() {
    var html = '';
    for (var i = 0; i < state.visibleCommands.length; i++) {
      var cmd = state.visibleCommands[i];
      var active = i === state.activeIndex ? ' is-active' : '';
      html += '<div class="si-command-palette-item' + active + '" role="option" data-si-command="' + cmd.command + '">' +
        '<div class="si-command-palette-row">' +
          '<span class="si-command-palette-name">' + SI.escapeHtml(cmd.name) + '</span>' +
          '<span class="si-command-palette-usage">' + SI.escapeHtml(cmd.usage) + '</span>' +
        '</div>' +
        '<div class="si-command-palette-description">' + SI.escapeHtml(cmd.description) + '</div>' +
        '</div>';
    }
    state.paletteEl.innerHTML = html;
    state.paletteEl.hidden = false;
  }

  function hidePalette() {
    if (state.paletteEl) state.paletteEl.hidden = true;
    state.visibleCommands = [];
  }

  function isPaletteVisible() {
    return state.paletteEl && !state.paletteEl.hidden && state.visibleCommands.length;
  }

  function handlePaletteKeydown(e) {
    if (!isPaletteVisible()) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      state.activeIndex = (state.activeIndex + 1) % state.visibleCommands.length;
      renderPalette();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      state.activeIndex = (state.activeIndex - 1 + state.visibleCommands.length) % state.visibleCommands.length;
      renderPalette();
    } else if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
      e.preventDefault();
      e.stopPropagation();
      var cmd = state.visibleCommands[state.activeIndex];
      if (cmd) selectCommand(cmd.command);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      hidePalette();
    }
  }

  function selectCommand(cmdName) {
    var cmd = COMMAND_INDEX[cmdName];
    if (!cmd) return;
    var input = state.els.input;
    input.value = cmd.name + ' ';
    input.dispatchEvent(new Event('input'));
    input.focus();
    hidePalette();
  }

  function maybeInterceptSend(text) {
    var match = parseCommand(text);
    if (!match) return false;
    var cmd = COMMAND_INDEX[match.command];
    if (!cmd) return false;
    dispatchCommand(cmd, match.args);
    return true;
  }

  function parseCommand(text) {
    if (typeof text !== 'string' || text.charAt(0) !== '/') return null;
    var trimmed = text.trim();
    var space = trimmed.indexOf(' ');
    var name = (space === -1 ? trimmed : trimmed.slice(0, space)).slice(1).toLowerCase();
    var args = space === -1 ? '' : trimmed.slice(space + 1).trim();
    return {command: name, args: args};
  }

  function dispatchCommand(cmd, args) {
    if (cmd.command === 'plan') return runPlanCommand(args);
    if (cmd.command === 'compact') return runCompactCommand();
    if (cmd.command === 'retry') return runRetryCommand();
    if (cmd.command === 'title') return runTitleCommand(args);
    if (cmd.command === 'new') return runNewCommand();
    if (cmd.command === 'help') return runHelpCommand();
  }

  function commandUrl() {
    return state.els.root.getAttribute('data-new-url').replace('/new/', '/' + SI.activeConvoId + '/command/');
  }

  function runPlanCommand(args) {
    setPlanMode(true);
    if (!args) {
      // No prompt yet — just flip the mode and tell the user.
      SI.api(commandUrl(), {
        method: 'POST',
        body: JSON.stringify({command: 'plan', args: ''}),
      }).then(function(data) {
        if (data && data.message) renderInlineNotice(data.message, 'info');
      });
      return;
    }
    streamPlanCommand(args);
  }

  function streamPlanCommand(args) {
    if (!SI.startStreamForCommand) return;
    SI.startStreamForCommand({
      url: commandUrl(),
      body: {command: 'plan', args: args},
      displayPrompt: args,
    });
  }

  function runCompactCommand() {
    SI.api(commandUrl(), {
      method: 'POST',
      body: JSON.stringify({command: 'compact'}),
    }).then(function(data) {
      if (!data) return;
      if (data.error) {
        renderInlineNotice(data.error, 'error');
        return;
      }
      if (data.compacted) {
        var summarized = data.messages_summarized || 0;
        var label = summarized
          ? '✓ Context compacted: ' + summarized + ' message' + (summarized === 1 ? '' : 's') + ' summarized.'
          : '✓ Context compacted.';
        renderInlineNotice(label, 'ok');
      } else if (data.message) {
        renderInlineNotice(data.message, 'info');
      }
    });
  }

  function runRetryCommand() {
    var messages = state.els && state.els.messagesEl;
    if (!messages) return;
    var lastUser = findLastUserBubble(messages);
    if (!lastUser) {
      renderInlineNotice('Nothing to retry yet.', 'info');
      return;
    }
    if (!SI.startStreamForCommand) return;
    SI.startStreamForCommand({
      url: commandUrl(),
      body: {command: 'retry'},
      displayPrompt: lastUser,
    });
  }

  function findLastUserBubble(messagesEl) {
    var bubbles = messagesEl.querySelectorAll('.si-msg-user .si-msg-bubble');
    if (!bubbles.length) return '';
    var last = bubbles[bubbles.length - 1];
    return (last.textContent || '').trim();
  }

  function runTitleCommand(args) {
    if (!args) {
      renderInlineNotice('Usage: /title <new title>', 'info');
      return;
    }
    SI.api(commandUrl(), {
      method: 'POST',
      body: JSON.stringify({command: 'title', args: args}),
    }).then(function(data) {
      if (!data) return;
      if (data.error) {
        renderInlineNotice(data.error, 'error');
        return;
      }
      renderInlineNotice('Conversation renamed to “' + (data.title || args) + '”.', 'ok');
      if (SI.sidebar && SI.sidebar.loadConversations) SI.sidebar.loadConversations();
    });
  }

  function runNewCommand() {
    if (state.els && state.els.newBtn) state.els.newBtn.click();
  }

  function runHelpCommand() {
    var lines = COMMANDS.map(function(cmd) {
      return cmd.usage + ' — ' + cmd.description;
    });
    var notice = 'Available commands:\n' + lines.join('\n');
    renderInlineNotice(notice, 'info');
  }

  function exitPlanMode() {
    SI.api(commandUrl(), {
      method: 'POST',
      body: JSON.stringify({command: 'exit-plan'}),
    }).then(function(data) {
      if (data && data.error) {
        renderInlineNotice(data.error, 'error');
        return;
      }
      setPlanMode(false);
      renderInlineNotice('Plan mode exited. Send your next message to execute.', 'info');
    });
  }

  function renderInlineNotice(text, kind) {
    var els = state.els;
    if (!els || !els.messagesEl) return;
    var cls = 'si-system-notice';
    if (kind === 'error') cls += ' is-error';
    else if (kind === 'ok') cls += ' is-ok';
    var node = document.createElement('div');
    node.className = cls;
    node.textContent = text;
    els.messagesEl.appendChild(node);
    els.messagesEl.scrollTop = els.messagesEl.scrollHeight;
  }

  function setPlanMode(active) {
    state.planActive = !!active;
    if (state.bannerEl) state.bannerEl.hidden = !active;
    var root = state.els && state.els.root;
    if (root) root.classList.toggle('is-plan-mode', !!active);
  }

  SI.initCommands = initCommands;
  SI.maybeInterceptSend = maybeInterceptSend;
  SI.setPlanMode = setPlanMode;
  SI.SLASH_COMMANDS = COMMANDS;
})();
