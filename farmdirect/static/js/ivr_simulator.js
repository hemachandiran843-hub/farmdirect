/* ============================================================
   IVR Simulator — in-browser client
   - Same backend as a real phone call (/api/ivr/incoming, /api/ivr/input)
   - Web Speech API for STT + TTS (Tamil & English)
   - DTMF keypad + free-text input fallback
   ============================================================ */

(function () {
  const S = window.IVR_SCRIPT_ROOT || '';
  let sessionToken = null;
  let callActive = false;
  let callStartTs = null;
  let timerHandle = null;
  let currentLang = 'ta';           // IVR-side language (server)
  let uiLang = 'ta';                  // simulator UI language
  let recognition = null;
  let recognizing = false;
  let lastRecognizedText = '';

  // ---------------- DOM helpers ----------------
  const $ = (id) => document.getElementById(id);

  function log(...args) { console.log('[IVR]', ...args); }

  // ---------------- TTS via browser SpeechSynthesis ----------------
  function speak(text, lang) {
    if (!('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang === 'en' ? 'en-IN' : 'ta-IN';
      u.rate = 0.95;
      u.pitch = 1;
      // try to pick a Tamil/English voice if available
      const voices = window.speechSynthesis.getVoices() || [];
      const want = lang === 'en' ? 'en-IN' : 'ta-IN';
      const match = voices.find(v => (v.lang || '').toLowerCase().startsWith(want.split('-')[0]));
      if (match) u.voice = match;
      window.speechSynthesis.speak(u);
    } catch (e) { log('TTS error', e); }
  }

  // ---------------- STT via browser SpeechRecognition ----------------
  function initRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;
    r.lang = (currentLang === 'en') ? 'en-IN' : 'ta-IN';
    r.onstart = () => {
      recognizing = true;
      $('ivr-mic-btn').classList.add('recording');
      $('ivr-mic-hint').textContent = 'Listening…';
    };
    r.onend = () => {
      recognizing = false;
      $('ivr-mic-btn').classList.remove('recording');
      $('ivr-mic-hint').textContent = 'Tap to speak (Tamil / English / Tanglish)';
      if (lastRecognizedText) {
        $('ivr-mic-result').textContent = lastRecognizedText;
        $('ivr-send-voice').disabled = false;
      }
    };
    r.onresult = (ev) => {
      let txt = '';
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        txt += ev.results[i][0].transcript;
      }
      lastRecognizedText = txt.trim();
      $('ivr-mic-result').textContent = lastRecognizedText;
      if (ev.results[ev.results.length - 1].isFinal) {
        $('ivr-send-voice').disabled = false;
      }
    };
    r.onerror = (e) => {
      log('STT error', e.error);
      recognizing = false;
      $('ivr-mic-btn').classList.remove('recording');
      $('ivr-mic-hint').textContent = 'Mic error — type instead';
    };
    return r;
  }

  // ---------------- API helpers ----------------
  async function apiPost(url, body) {
    const res = await fetch(S + url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Request failed');
    return json;
  }

  // ---------------- transcript rendering ----------------
  function addBubble(role, text, intent) {
    const wrap = $('ivr-transcript');
    // remove empty placeholder
    const empty = wrap.querySelector('.ivr-empty');
    if (empty) empty.remove();
    const div = document.createElement('div');
    div.className = 'ivr-bubble ' + (role === 'user' ? 'user' : 'system');
    if (role === 'user') {
      div.innerHTML = `<span class="ivr-bubble-tag">YOU</span>${escapeHtml(text)}` +
        (intent ? ` <span class="ivr-bubble-intent">${intent}</span>` : '');
    } else {
      div.innerHTML = `<span class="ivr-bubble-tag">IVR</span>${escapeHtml(text)}`;
    }
    wrap.appendChild(div);
    wrap.scrollTop = wrap.scrollHeight;
  }

  function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, m =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]);
  }

  // ---------------- call lifecycle ----------------
  function startCall() {
    const caller = currentCaller();
    if (!caller) { alert('Please pick a caller number first.'); return; }
    addBubble('system', 'Connecting…');
    apiPost('/api/ivr/incoming', { caller_number: caller, source: 'simulator' })
      .then(r => {
        if (!r.ok) throw new Error(r.error || 'Failed to start call');
        sessionToken = r.session_token;
        callActive = true;
        callStartTs = Date.now();
        currentLang = r.language || 'ta';
        uiLang = currentLang;
        updateModePill(r.mode);
        renderPrompts(r.prompt || []);
        updateState(r);
        startTimer();
        showCallUI();
      })
      .catch(e => {
        addBubble('system', 'Error: ' + e.message);
      });
  }

  function hangup() {
    if (!sessionToken) { stopCallUI(); return; }
    apiPost('/api/ivr/hangup', { session_token: sessionToken })
      .then(() => { log('hangup ok'); })
      .catch(e => { log('hangup err', e); })
      .finally(() => { stopCallUI(); });
  }

  function stopCallUI() {
    callActive = false;
    stopTimer();
    $('ivr-call-btn').style.display = '';
    $('ivr-hangup-btn').style.display = 'none';
    $('ivr-input-tabs').style.display = 'none';
    $('ivr-keypad').style.display = 'none';
    $('ivr-voice-input').style.display = 'none';
    $('ivr-text-input').style.display = 'none';
    $('ivr-actions').style.display = 'none';
    $('ivr-lang-row').style.display = 'none';
    $('ivr-call-state').textContent = 'Call ended';
  }

  function showCallUI() {
    $('ivr-call-btn').style.display = 'none';
    $('ivr-hangup-btn').style.display = '';
    $('ivr-input-tabs').style.display = 'flex';
    $('ivr-keypad').style.display = 'grid';
    $('ivr-lang-row').style.display = 'flex';
    $('ivr-actions').style.display = 'flex';
    $('ivr-call-state').textContent = 'Connected';
    $('ivr-state-card').style.display = '';
    $('ivr-intent-card').style.display = '';
    $('ivr-action-card').style.display = '';
    setUILang(currentLang);
  }

  function startTimer() {
    stopTimer();
    timerHandle = setInterval(() => {
      const sec = Math.floor((Date.now() - callStartTs) / 1000);
      const mm = String(Math.floor(sec / 60)).padStart(2, '0');
      const ss = String(sec % 60).padStart(2, '0');
      $('ivr-timer').textContent = `${mm}:${ss}`;
    }, 500);
  }
  function stopTimer() {
    if (timerHandle) clearInterval(timerHandle);
    timerHandle = null;
  }

  // ---------------- input handling ----------------
  function sendInput({ text, dtmf }) {
    if (!sessionToken) return;
    apiPost('/api/ivr/input', {
      session_token: sessionToken,
      input: text || null,
      dtmf: dtmf || null,
      caller_number: currentCaller(),
      source: 'simulator',
    })
      .then(r => {
        if (!r.ok) throw new Error(r.error || 'Request failed');
        // user bubble (what was sent)
        if (text) addBubble('user', text, r.intent || '');
        if (dtmf) addBubble('user', 'DTMF ' + dtmf, r.intent || '');
        renderPrompts(r.prompt || []);
        updateState(r);
        updateIntent(r);
        updateAction(r.action);
        updateModePill(r.mode);
        if (r.ended) {
          addBubble('system', 'Call ended by IVR.');
          stopCallUI();
        }
      })
      .catch(e => {
        addBubble('system', 'Error: ' + e.message);
      });
  }

  function renderPrompts(prompts) {
    if (!prompts || !prompts.length) return;
    const text = prompts.filter(p => p).join(' ');
    addBubble('system', text);
    speak(text, currentLang);
  }

  // ---------------- UI updates ----------------
  function updateState(r) {
    $('ivr-session-token').textContent = (r.session_token || '').slice(0, 12) + '…';
    $('ivr-session-lang').textContent = r.language || '—';
    $('ivr-session-menu').textContent = r.current_menu || '—';
    $('ivr-session-auth').textContent = (r.auth_status) || '—';
    $('ivr-session-farmer').textContent = r.farmer_name ||
      (window.IVR_FARMERS.find(f => f.phone === currentCaller()) || {}).name || '—';
    $('ivr-session-fails').textContent = String(r.failure_count || 0);
    $('ivr-contact-num').textContent = (r.session && r.session.caller_number)
      ? ('+91 ' + String(r.session.caller_number).slice(-10)) : '—';
  }

  function updateIntent(r) {
    $('ivr-intent-name').textContent = r.intent || '—';
    const conf = (r.intent_payload && r.intent_payload.confidence) || 0;
    $('ivr-intent-conf').textContent = (Math.round(conf * 100)) + '%';
    $('ivr-intent-json').textContent = JSON.stringify(r.intent_payload || {}, null, 2);
  }

  function updateAction(action) {
    if (!action) {
      $('ivr-action-card').style.display = 'none';
      return;
    }
    $('ivr-action-card').style.display = '';
    $('ivr-action-name').textContent = action.name || '—';
    $('ivr-action-json').textContent = JSON.stringify(action.result || action.error || {}, null, 2);
  }

  function updateModePill(mode) {
    if (!mode) return;
    const pill = $('ivr-mode-pill');
    pill.textContent = (mode.mode || 'mock').toUpperCase();
    pill.style.background = mode.mode === 'production' ? '#fdeaea' : 'var(--fd-amber-light)';
    pill.style.color = mode.mode === 'production' ? '#b03a2e' : '#9a6b06';
    $('ivr-provider').textContent = (mode.mode || 'sim').toUpperCase() + ' · ' + (mode.telephony || 'MOCK');
  }

  function currentCaller() {
    const checked = document.querySelector('input[name="caller_number"]:checked');
    if (checked && checked.value) return checked.value;
    const custom = $('ivr-custom-caller').value.trim();
    return custom || '';
  }

  function setUILang(lang) {
    currentLang = lang;
    uiLang = lang;
    document.querySelectorAll('.ivr-lang-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.lang === lang);
    });
  }

  // ---------------- wire events ----------------
  function wire() {
    // start / hangup
    $('ivr-call-btn').addEventListener('click', startCall);
    $('ivr-hangup-btn').addEventListener('click', hangup);

    // language toggle
    document.querySelectorAll('.ivr-lang-btn').forEach(b => {
      b.addEventListener('click', () => {
        setUILang(b.dataset.lang);
        if (callActive) {
          // tell IVR to switch language by sending DTMF 8 then re-selecting
          sendInput({ dtmf: '8' });
        }
      });
    });

    // input tabs
    document.querySelectorAll('.ivr-input-tabs button').forEach(b => {
      b.addEventListener('click', () => {
        document.querySelectorAll('.ivr-input-tabs button').forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        const mode = b.dataset.mode;
        $('ivr-keypad').style.display = mode === 'keypad' ? 'grid' : 'none';
        $('ivr-voice-input').style.display = mode === 'voice' ? 'flex' : 'none';
        $('ivr-text-input').style.display = mode === 'text' ? 'flex' : 'none';
      });
    });

    // keypad
    document.querySelectorAll('.ivr-key').forEach(k => {
      k.addEventListener('click', () => {
        if (!callActive) return;
        sendInput({ dtmf: k.dataset.d });
      });
    });

    // mic
    $('ivr-mic-btn').addEventListener('click', () => {
      if (!('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) {
        alert('SpeechRecognition not supported in this browser. Use the Text tab.');
        return;
      }
      if (!recognition) recognition = initRecognition();
      if (recognizing) { try { recognition.stop(); } catch (e) {} return; }
      lastRecognizedText = '';
      $('ivr-mic-result').textContent = '';
      $('ivr-send-voice').disabled = true;
      try { recognition.lang = currentLang === 'en' ? 'en-IN' : 'ta-IN'; recognition.start(); }
      catch (e) { log(e); }
    });

    $('ivr-send-voice').addEventListener('click', () => {
      if (!lastRecognizedText) return;
      sendInput({ text: lastRecognizedText });
      lastRecognizedText = '';
      $('ivr-mic-result').textContent = '';
      $('ivr-send-voice').disabled = true;
    });

    // text input
    $('ivr-text-field').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && e.target.value.trim()) {
        sendInput({ text: e.target.value.trim() });
        e.target.value = '';
      }
    });
    $('ivr-send-text').addEventListener('click', () => {
      const v = $('ivr-text-field').value.trim();
      if (!v) return;
      sendInput({ text: v });
      $('ivr-text-field').value = '';
    });

    // quick action buttons
    $('ivr-repeat').addEventListener('click', () => sendInput({ text: currentLang === 'ta' ? 'மீண்டும் சொல்லுங்கள்' : 'repeat' }));
    $('ivr-back').addEventListener('click', () => sendInput({ text: currentLang === 'ta' ? 'பின்னாடி போ' : 'go back' }));
    $('ivr-main').addEventListener('click', () => sendInput({ text: currentLang === 'ta' ? 'முக்கிய மெனு' : 'main menu' }));

    // custom caller
    $('ivr-use-custom').addEventListener('click', () => {
      const v = $('ivr-custom-caller').value.trim();
      if (!v) return;
      document.querySelectorAll('.ivr-caller-radio').forEach(r => r.checked = false);
      // update display
      $('ivr-contact-num').textContent = v;
    });

    // quick demo scripts
    document.querySelectorAll('.ivr-script-btn').forEach(btn => {
      btn.addEventListener('click', () => runScript(btn.dataset.script));
    });
  }

  // ---------------- scripted demos ----------------
  async function runScript(name) {
    if (!callActive) {
      // pick a Tamil-friendly caller if not already
      const first = document.querySelector('input[name="caller_number"]');
      if (first) first.checked = true;
      startCall();
      // wait for the call to come up
      await new Promise(r => setTimeout(r, 1200));
    }
    const scripts = {
      list_tamil: [
        { dtmf: '1' },                                         // choose Tamil
        { text: 'என்னிடம் 100 கிலோ தக்காளி இருக்கு' },
        { dtmf: '38' },                                        // won't parse as DTMF — use text
        { text: '38' },
        { text: 'இன்று' },
        { dtmf: '2' },                                         // grade A
        { dtmf: '1' },                                         // confirm
      ],
      list_en: [
        { dtmf: '2' },
        { text: 'I have 200 kilos of onion' },
        { text: '19' },
        { text: 'today' },
        { dtmf: '2' },
        { dtmf: '1' },
      ],
      price_tamil: [
        { dtmf: '1' },
        { text: 'இன்று தக்காளி விலை என்ன?' },
      ],
      order_tamil: [
        { dtmf: '1' },
        { text: 'என்னுடைய ஆர்டர் எங்கே?' },
      ],
      bulk_en: [
        { dtmf: '2' },
        { text: 'Are there any bulk orders?' },
        { dtmf: '1' },
      ],
      earn_tamil: [
        { dtmf: '1' },
        { text: 'எனக்கு எவ்வளவு பணம் வந்திருக்கு?' },
      ],
    };
    const steps = scripts[name] || [];
    for (const step of steps) {
      // skip the initial language DTMF if the session is already past language_select
      if (step.dtmf && step.dtmf.length > 1) {
        // multi-digit numeric input: send as text
        sendInput({ text: step.dtmf });
      } else {
        sendInput(step);
      }
      await new Promise(r => setTimeout(r, 1300));
    }
  }

  // ---------------- init ----------------
  if (document.readyState !== 'loading') wire();
  else document.addEventListener('DOMContentLoaded', wire);

  // warm up the voices list (Chrome)
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => { /* cached */ };
    window.speechSynthesis.getVoices();
  }
})();
