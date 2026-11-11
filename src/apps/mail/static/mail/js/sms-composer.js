/*
 * Broadcast SMS composer: a live count, under the message field, of what one text costs.
 *
 * It measures the text as it will be sent (apps/mail/services/sms/compose.py): example names, every link placeholder
 * as long as a real link, line breaks as the form submits them (CR LF), and the opt-out footer unless the message
 * already says STOP. The count follows apps/core/services/delivery_rates/rules/sms_parts.py (GSM 03.38): 160 GSM-7
 * characters fit one text and 153 each part once it is split, an extension character takes two; any other character
 * makes the whole text UCS-2, 70 per text and 67 per part. The settings come from #sms-composer-settings.
 */
(function () {
  'use strict';

  var GSM_SINGLE = 160;
  var GSM_PART = 153;
  var UCS2_SINGLE = 70;
  var UCS2_PART = 67;
  var GSM_BASIC = '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !"#¤%&\'()*+,-./0123456789:;<=>?' +
    '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà';
  var GSM_EXTENSION = '\f^{}\\[~]|€';
  var STOP_RE = /\bstop\b/i;

  function gsmSizes(characters) {
    var sizes = [];
    for (var i = 0; i < characters.length; i += 1) {
      if (GSM_BASIC.indexOf(characters[i]) !== -1) {
        sizes.push(1);
      } else if (GSM_EXTENSION.indexOf(characters[i]) !== -1) {
        sizes.push(2);
      } else {
        return null;
      }
    }
    return sizes;
  }

  function parts(sizes, single, part) {
    var total = sizes.reduce(function (sum, size) { return sum + size; }, 0);
    if (total <= single) {
      return 1;
    }
    var count = 1;
    var used = 0;
    sizes.forEach(function (size) {
      if (used + size > part) {
        count += 1;
        used = 0;
      }
      used += size;
    });
    return count;
  }

  /* The encoding, length and segments of ``text``, and the characters that make it UCS-2. */
  function measure(text) {
    var characters = Array.from(String(text || ''));
    var gsm = gsmSizes(characters);
    if (gsm !== null) {
      return {encoding: 'GSM-7', characters: characters.length, segments: parts(gsm, GSM_SINGLE, GSM_PART), offenders: []};
    }
    var offenders = [];
    characters.forEach(function (character) {
      var outside = GSM_BASIC.indexOf(character) === -1 && GSM_EXTENSION.indexOf(character) === -1;
      if (outside && offenders.indexOf(character) === -1) {
        offenders.push(character);
      }
    });
    var ucs2 = characters.map(function (character) { return character.codePointAt(0) > 0xFFFF ? 2 : 1; });
    return {encoding: 'UCS-2', characters: characters.length, segments: parts(ucs2, UCS2_SINGLE, UCS2_PART), offenders: offenders};
  }

  function fill(text, key, value) {
    return text.split('{{' + key + '}}').join(value).split('{{ ' + key + ' }}').join(value);
  }

  /* ``message`` as one recipient's text: names, full-length links, CR LF line breaks and the footer. */
  function compose(message, settings) {
    var text = String(message || '').replace(/\r\n|\r|\n/g, '\r\n');
    var names = settings.names || {};
    Object.keys(names).forEach(function (key) { text = fill(text, key, names[key]); });
    var link = new Array((settings.linkLength || 0) + 1).join('x');
    (settings.linkPlaceholders || []).forEach(function (key) { text = fill(text, key, link); });
    var footer = String(settings.footer || '').trim();
    if (footer && !STOP_RE.test(text)) {
      text = text.replace(/\s+$/, '') + '\n' + footer;
    }
    return text;
  }

  function usesLinks(message, settings) {
    return (settings.linkPlaceholders || []).some(function (key) {
      return message.indexOf('{{' + key + '}}') !== -1 || message.indexOf('{{ ' + key + ' }}') !== -1;
    });
  }

  /* The counter's sentences for ``message``. */
  function describe(message, settings) {
    var result = measure(compose(message, settings));
    var price = Number(settings.costPerSegment || 0);
    var cost = (price * result.segments).toFixed(4);
    var lines = [
      result.encoding + ' · ' + result.characters + ' characters · ' + result.segments + ' segment' +
        (result.segments === 1 ? '' : 's') + ' · ≈ $' + cost + ' per recipient',
    ];
    if (result.encoding === 'UCS-2') {
      lines.push('These characters make every segment hold only 70 (67 when split): ' + result.offenders.join(' '));
    }
    if (usesLinks(message, settings) && !settings.linksEnabled) {
      lines.push('Links in SMS are turned off (SMS Settings): this campaign cannot be saved with a link placeholder.');
    }
    return {lines: lines, warn: result.encoding === 'UCS-2' || result.segments > 2};
  }

  function render(counter, message, settings) {
    var described = describe(message, settings);
    counter.textContent = '';
    described.lines.forEach(function (line) {
      var paragraph = document.createElement('p');
      paragraph.textContent = line;
      counter.appendChild(paragraph);
    });
    counter.className = 'mt-2 text-xs ' + (described.warn ? 'text-red-600 dark:text-red-400' : 'text-base-500 dark:text-base-300');
  }

  function init() {
    var source = document.getElementById('sms-composer-settings');
    var counter = document.getElementById('sms-composer-counter');
    var field = document.getElementById('id_message');
    if (!source || !counter || !field) {
      return;
    }
    var settings = JSON.parse(source.textContent);
    field.insertAdjacentElement('afterend', counter);
    var update = function () { render(counter, field.value, settings); };
    field.addEventListener('input', update);
    update();
  }

  window.I2GSmsComposer = {measure: measure, compose: compose, describe: describe};
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
