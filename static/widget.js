/* static/widget.js - AI Assistant Chatbot Widget */

(function () {
  // 1. Inject HTML for the floating assistant
  const widgetHtml = `
    <!-- Launcher Button -->
    <button id="assistant-launcher" aria-label="Open Jio AI Assistant">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 3C7.03 3 3 6.58 3 11c0 2.39 1.19 4.53 3.08 6.02-.11.99-.54 2.15-1.4 3.31-.15.2 0 .49.25.47 1.94-.19 3.5-.9 4.6-1.62.79.17 1.62.27 2.47.27 4.97 0 9-3.58 9-8s-4.03-8-9-8z" fill="white"/>
      </svg>
    </button>

    <!-- Assistant Chat Panel -->
    <div id="assistant-panel">
      <div class="panel-header">
        <div class="panel-header-title">
          <div class="panel-header-orb"></div>
          <div>
            <div class="panel-header-text">Jio AI Assistant</div>
            <div class="panel-header-sub">Online & Grounded</div>
          </div>
        </div>
        <button id="panel-close" aria-label="Close panel">&times;</button>
      </div>

      <div id="chat-messages">
        <div class="welcome-msg">
          Hello! I am your Jio AI Assistant, grounded in real plan data and FAQs. Ask me anything about mobile recharges, fiber connections, AirFiber, or business solutions.
        </div>
      </div>

      <div id="chat-input-row">
        <button id="chat-mic" aria-label="Speak your question">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <input id="chat-input" type="text" placeholder="Ask about plans, features..." autocomplete="off">
        <button id="chat-send" aria-label="Send query">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M2 12L21 3L14 21L11 13L2 12Z" stroke="white" stroke-width="2" stroke-linejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', widgetHtml);

  // 2. Fetch DOM elements
  const launcher = document.getElementById('assistant-launcher');
  const panel = document.getElementById('assistant-panel');
  const closeBtn = document.getElementById('panel-close');
  const messagesContainer = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');
  const micBtn = document.getElementById('chat-mic');

  let isOpen = false;
  let currentSessionId = null;

  // 2b. Speech-to-text (Web Speech API) - mic input
  const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;

  const originalPlaceholder = chatInput.placeholder;
  let finalTranscript = '';

  if (SpeechRecognitionCtor) {
    recognition = new SpeechRecognitionCtor();
    recognition.lang = 'en-IN';
    recognition.interimResults = true; // show a live preview while the user is still speaking
    recognition.maxAlternatives = 1;

    recognition.addEventListener('start', () => {
      isListening = true;
      finalTranscript = '';
      micBtn.classList.add('listening');
      chatInput.placeholder = 'Listening...';
    });

    recognition.addEventListener('result', (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interim += transcript;
        }
      }
      // Show live preview (final so far + interim tail) while listening
      chatInput.value = (finalTranscript + interim).trim();
    });

    recognition.addEventListener('error', () => {
      micBtn.classList.add('mic-error');
      setTimeout(() => micBtn.classList.remove('mic-error'), 600);
    });

    recognition.addEventListener('end', () => {
      isListening = false;
      micBtn.classList.remove('listening');
      chatInput.placeholder = originalPlaceholder;

      // Auto-send once the user pauses and recognition naturally ends,
      // as long as something was actually transcribed.
      const transcript = finalTranscript.trim() || chatInput.value.trim();
      if (transcript) {
        chatInput.value = transcript;
        handleSendMessage();
      } else {
        chatInput.focus();
      }
    });

    micBtn.addEventListener('click', () => {
      if (isListening) {
        recognition.stop();
      } else {
        try {
          recognition.start();
        } catch (e) {
          // start() throws if already started; ignore
        }
      }
    });
  } else {
    // Browser doesn't support speech recognition (e.g. Firefox) - hide the mic button
    micBtn.style.display = 'none';
  }

  // 2c. Text-to-speech (Web Speech API) - read bot replies aloud
  function speak(text) {
    if (!('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel(); // stop any ongoing speech
    const plainText = text.replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '');
    const utterance = new SpeechSynthesisUtterance(plainText);
    utterance.lang = 'en-IN';
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  // 3. Toggle Assistant Panel
  function toggleAssistant() {
    isOpen = !isOpen;
    if (isOpen) {
      panel.style.display = 'flex';
      // Force reflow for transitions
      panel.offsetHeight;
      panel.classList.add('open');
      setTimeout(() => chatInput.focus(), 150);
    } else {
      panel.classList.remove('open');
      setTimeout(() => {
        if (!isOpen) panel.style.display = 'none';
      }, 250);
    }
  }

  // Bind toggle events
  launcher.addEventListener('click', toggleAssistant);
  closeBtn.addEventListener('click', toggleAssistant);

  // Expose function globally in case standard inline buttons want to launch it
  window.openAssistant = function () {
    if (!isOpen) toggleAssistant();
  };

  // 4. Message Appending & Formatting
  function addMessage(text, className) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${className}`;
    
    // Simple markdown link conversion & formatting
    if (className.includes('msg-bot') && !className.includes('loading')) {
      // Escape HTML to prevent injection
      let formattedText = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      // Convert bullet points
      formattedText = formattedText.replace(/^\s*[-*]\s+(.+)$/gm, '• $1');
      // Line breaks
      formattedText = formattedText.replace(/\n/g, '<br>');
      
      msgDiv.innerHTML = formattedText;

      // Add a read-aloud button for bot replies (Web Speech API text-to-speech)
      if ('speechSynthesis' in window) {
        const speakBtn = document.createElement('button');
        speakBtn.className = 'msg-speak-btn';
        speakBtn.setAttribute('aria-label', 'Read reply aloud');
        speakBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="13" height="13">
          <path d="M4 9v6h4l5 5V4L8 9H4z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
          <path d="M17 8a5 5 0 0 1 0 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        </svg>`;
        speakBtn.addEventListener('click', () => speak(text));
        msgDiv.appendChild(speakBtn);
      }
    } else {
      msgDiv.textContent = text;
    }

    messagesContainer.appendChild(msgDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return msgDiv;
  }

  // 5. Send Message to Backend
  async function handleSendMessage() {
    const question = chatInput.value.trim();
    if (!question) return;

    if (isListening) recognition.stop();

    // Display user message
    addMessage(question, 'msg-user');
    chatInput.value = '';
    sendBtn.disabled = true;

    // Show typing/thinking indicator
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'msg msg-bot loading';
    loadingDiv.innerHTML = `
      <div class="dot-typing">
        <div></div><div></div><div></div>
      </div>
      <span style="font-size: 12.5px; margin-left: 8px;">Searching plans...</span>
    `;
    messagesContainer.appendChild(loadingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
      const payload = { question };
      if (currentSessionId) {
        payload.session_id = currentSessionId;
      }

      const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();
      loadingDiv.remove();

      if (!response.ok) {
        addMessage(`Error: ${data.detail || 'unable to process request'}`, 'msg-bot');
      } else {
        if (data.session_id) {
          currentSessionId = data.session_id;
        }
        const botMsgDiv = addMessage(data.answer, 'msg-bot');

        // Append source references and tool tag if present
        if (data.tool_used || (data.sources && data.sources.length)) {
          const metaDiv = document.createElement('div');
          metaDiv.className = 'msg-meta';

          let sourceLabel = '';
          if (data.tool_used === 'sql') {
            sourceLabel = 'Source: Database Query';
          } else if (data.tool_used === 'vector') {
            sourceLabel = 'Source: Document Search';
          } else if (data.tool_used === 'both') {
            sourceLabel = 'Source: Hybrid DB + FAQ Search';
          }

          if (sourceLabel) {
            const tag = document.createElement('span');
            tag.className = 'source-tag';
            tag.textContent = sourceLabel;
            metaDiv.appendChild(tag);
          }

          if (data.sources && data.sources.length > 0) {
            const linkHeader = document.createElement('div');
            linkHeader.style.fontWeight = '600';
            linkHeader.style.marginTop = '4px';
            linkHeader.textContent = 'Reference Links:';
            metaDiv.appendChild(linkHeader);

            const linksContainer = document.createElement('div');
            linksContainer.className = 'source-links';

            data.sources.forEach(src => {
              const a = document.createElement('a');
              a.className = 'source-link-item';
              a.href = src.url || '#';
              a.target = '_blank';
              a.textContent = src.title || 'Plan Detail';
              linksContainer.appendChild(a);
            });
            metaDiv.appendChild(linksContainer);
          }

          botMsgDiv.appendChild(metaDiv);
          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
      }
    } catch (error) {
      loadingDiv.remove();
      addMessage('Network error - please check if the server is running.', 'msg-bot');
      console.error('Chat widget error:', error);
    }

    sendBtn.disabled = false;
    chatInput.focus();
  }

  // Bind input trigger events
  sendBtn.addEventListener('click', handleSendMessage);
  chatInput.addEventListener('keypress', (event) => {
    if (event.key === 'Enter') {
      handleSendMessage();
    }
  });
})();
