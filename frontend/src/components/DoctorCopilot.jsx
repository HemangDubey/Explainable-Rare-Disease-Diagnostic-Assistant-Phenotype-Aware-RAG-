import React, { useState, useRef, useEffect } from 'react';

const SUGGESTED_QUESTIONS = [
  "Why was this disease candidate prioritized first?",
  "Which patient phenotypes match the leading candidate?",
  "What population-frequency evidence is available, and is IndiGen data available?",
  "What important distinguishing phenotype is missing?",
  "What genetic and confirmatory molecular tests are indicated?"
];

// ---- Voice (browser Web Speech API; no extra provider, nothing is sent to this app until the user presses Ask) ----
const SpeechRecognitionCtor = typeof window !== 'undefined' ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;
// spoken text: drop evidence ids like (C1-E12) and bracketed refs, keep the sentence
const toSpeech = (t) => String(t || '').replace(/\s*\(?\bC\d+-E\d+(?:\s*,\s*C\d+-E\d+)*\)?/g, '').replace(/\[[^\]]*\]/g, '').replace(/\s+/g, ' ').trim();

export default function DoctorCopilot({ onAsk, isLoading, currentCase }) {
  const [query, setQuery] = useState('');
  const [listening, setListening] = useState(false);
  const [voiceMsg, setVoiceMsg] = useState(null);
  const [autoSend, setAutoSend] = useState(false);
  const [readAloud, setReadAloud] = useState(false);
  const [speakingIdx, setSpeakingIdx] = useState(null);
  const recRef = useRef(null);
  const transcriptRef = useRef('');
  const spokenRef = useRef(0);

  const stopSpeaking = () => { if (speechSupported) window.speechSynthesis.cancel(); setSpeakingIdx(null); };
  const speak = (text, idx) => {
    if (!speechSupported) return;
    window.speechSynthesis.cancel();
    const clean = toSpeech(text);
    if (!clean) return;
    const u = new SpeechSynthesisUtterance(clean);
    u.lang = 'en-IN';
    u.onend = () => setSpeakingIdx(null);
    u.onerror = () => setSpeakingIdx(null);
    setSpeakingIdx(idx);
    window.speechSynthesis.speak(u);
  };

  const toggleListening = () => {
    if (!SpeechRecognitionCtor) { setVoiceMsg('Voice input is not supported in this browser (use Chrome or Edge). You can still type.'); return; }
    if (listening) { recRef.current?.stop(); return; }
    stopSpeaking();
    setVoiceMsg(null);
    transcriptRef.current = '';
    const rec = new SpeechRecognitionCtor();
    rec.lang = 'en-IN';
    rec.interimResults = true;
    rec.continuous = false;
    rec.onresult = (e) => {
      let text = '';
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      transcriptRef.current = text.trim();
      setQuery(text.trim());
    };
    rec.onerror = (e) => {
      const m = { 'not-allowed': 'Microphone permission was denied. Allow microphone access in the browser to dictate.', 'service-not-allowed': 'Speech service is not allowed in this browser.',
        'no-speech': 'No speech was detected. Try again.', 'audio-capture': 'No microphone was found.', network: 'The browser speech service is unreachable (network).' };
      setVoiceMsg(m[e.error] || `Voice input error: ${e.error}`);
    };
    rec.onend = () => {
      setListening(false);
      const said = transcriptRef.current;
      if (said && autoSend) handleSend(said);
    };
    recRef.current = rec;
    try { rec.start(); setListening(true); } catch (err) { setVoiceMsg('Could not start voice input.'); }
  };

  useEffect(() => () => { try { recRef.current?.abort(); } catch (e) { /* ignore */ } if (speechSupported) window.speechSynthesis.cancel(); }, []);
  const [conversation, setConversation] = useState([
    {
      role: 'assistant',
      text: "Hello, I am your Explainable AI Doctor Copilot. I can synthesize phenotype alignment, knowledge-base retrieval, and population-frequency evidence for this patient's case. How can I assist with your clinical evaluation?",
      evidence: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);

  useEffect(() => {
    if (!readAloud || conversation.length <= spokenRef.current) { spokenRef.current = conversation.length; return; }
    const last = conversation[conversation.length - 1];
    spokenRef.current = conversation.length;
    if (last.role === 'assistant' && !last.error && conversation.length > 1) speak(last.text, conversation.length - 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversation, readAloud]);

  const handleSend = async (questionText) => {
    const textToSend = questionText || query;
    if (!textToSend.trim() || isLoading) return;

    const userMsg = {
      role: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    setConversation((prev) => [...prev, userMsg]);
    if (!questionText) setQuery('');

    try {
      const response = await onAsk(textToSend);
      const assistantMsg = {
        role: 'assistant',
        text: response.answer || response,
        evidence: response.evidence_points || [],
        areas: response.candidate_annotations_not_in_record || [],
        missing: response.missing_evidence || [],
        patientFindings: response.patient_record_findings || [],
        generatedBy: response.generated_by || null,
        failureCategory: response.failure_category || null,
        requestId: response.request_id || null,
        question: textToSend,
        provider: response.provider || null,
        fallback: !!response.fallback,
        sources: response.source_references || [],
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setConversation((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setConversation((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: err instanceof TypeError
            ? 'Copilot error: the backend could not be reached. Please verify it is running, then retry.'
            : err.httpStatus === 401
              ? 'Your session has expired. Sign in again (the sign-in window is shown), then retry the question.'
              : err.httpStatus === 429
                ? 'Too many requests were sent to the server in the last minute. Wait a moment, then retry.'
                : `Copilot error: ${err.message}`,
          error: true,
          question: textToSend,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
    }
  };

  return (
    <div className="bg-surface-container-lowest rounded-2xl shadow-sm border border-outline-variant/30 flex flex-col h-[650px] overflow-hidden">
      {/* Header */}
      <div className="p-space-md bg-surface-container-low border-b border-outline-variant/30 flex items-center justify-between">
        <div className="flex items-center gap-space-xs">
          <div className="w-8 h-8 rounded-lg bg-secondary text-on-secondary flex items-center justify-center">
            <span className="material-symbols-outlined text-[20px]">smart_toy</span>
          </div>
          <div>
            <h3 className="font-title-md text-primary font-bold">AI Doctor Copilot</h3>
            <span className="text-label-sm text-on-surface-variant flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-secondary animate-pulse"></span>
              Grounded in current patient case evidence
            </span>
          </div>
        </div>

        {currentCase?.fused_candidates?.[0] && (
          <div className="text-right hidden sm:block">
            <span className="text-[11px] text-on-surface-variant block uppercase font-bold">Top Priority</span>
            <span className="font-label-md font-semibold text-primary truncate max-w-[200px] block">
              {currentCase.fused_candidates[0].disease_name}
            </span>
          </div>
        )}
      </div>

      {/* Suggested Quick Prompts */}
      <div className="px-space-md py-space-xs bg-surface-container-lowest border-b border-outline-variant/20 flex items-center gap-space-2xs overflow-x-auto">
        <span className="text-[11px] font-bold text-on-surface-variant uppercase whitespace-nowrap mr-1">
          Suggested:
        </span>
        {SUGGESTED_QUESTIONS.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q)}
            disabled={isLoading}
            className="whitespace-nowrap px-space-xs py-1 rounded-full bg-surface-container hover:bg-secondary-fixed/30 hover:text-on-secondary-fixed text-label-sm text-on-surface transition-colors border border-outline-variant/30 disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Chat Messages */}
      <div className="flex-1 p-space-md overflow-y-auto flex flex-col gap-space-md">
        {conversation.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl p-space-md shadow-sm ${
                msg.role === 'user'
                  ? 'bg-primary text-on-primary rounded-tr-none'
                  : msg.error
                  ? 'bg-error-container text-on-error-container rounded-tl-none'
                  : 'bg-surface-container-low text-on-surface rounded-tl-none border border-outline-variant/30'
              }`}
            >
              {msg.role === 'assistant' && !msg.error && msg.provider && (
                <span className={`inline-block mb-space-2xs px-space-xs py-0.5 rounded text-[10px] font-bold ${
                  msg.fallback ? 'bg-error-container text-on-error-container' : 'bg-primary-fixed text-on-primary-fixed'
                }`}>
                  {msg.generatedBy === 'assistant_notice'
                    ? 'ASSISTANT NOTICE — no language model used'
                    : msg.generatedBy === 'evidence_summary' && !msg.fallback
                    ? 'EVIDENCE SUMMARY — rule-based, no language model (scope-limited question)'
                    : msg.fallback
                    ? `DETERMINISTIC FALLBACK — language model ${(msg.provider.status || 'unavailable').replace(/_/g, ' ')}${msg.provider.reason ? ` (${msg.provider.reason})` : ''}`
                    : 'AI-generated from the recorded evidence'}
                </span>
              )}
              <p className="font-body-md whitespace-pre-wrap leading-relaxed">{msg.text}</p>

              {/* Retryable provider failure */}
              {msg.role === 'assistant' && (msg.provider?.retryable || msg.error) && msg.question && (
                <div className="mt-space-xs flex flex-wrap items-center gap-2">
                  <button onClick={() => handleSend(msg.question)} disabled={isLoading}
                    className="px-space-sm py-1 rounded-lg bg-primary text-on-primary text-label-sm font-bold disabled:opacity-50">
                    Retry this question
                  </button>
                  {msg.provider?.retry_after_seconds > 60 && (
                    <span className="text-label-sm text-on-surface-variant">
                      The language-model service {msg.provider.limit || 'usage'} limit is reached; a retry before about {Math.ceil(msg.provider.retry_after_seconds / 60)} min will also fall back.
                      The answer above is a rule-based summary of the recorded evidence, not a model answer.
                    </span>
                  )}
                </div>
              )}

              {/* What the record lacks (insufficient-evidence answers) */}
              {msg.missing && msg.missing.length > 0 && (
                <div className="mt-space-xs p-space-xs rounded bg-surface-container text-label-sm text-on-surface-variant">
                  <strong className="text-primary">Evidence not available:</strong>
                  <ul className="list-disc list-inside">{msg.missing.map((m, i) => <li key={i}>{m}</li>)}</ul>
                </div>
              )}

              {/* Evidence Points */}
              {msg.evidence && msg.evidence.length > 0 && (
                <div className="mt-space-xs pt-space-xs border-t border-outline-variant/20 text-body-sm">
                  <span className="font-bold text-primary block text-label-sm mb-1">
                    Referenced Evidence:
                  </span>
                  <ul className="list-disc list-inside space-y-0.5 text-on-surface-variant">
                    {msg.evidence.map((ev, i) => (
                      <li key={i}>
                        {typeof ev === 'string' ? ev : ev.text}
                        {ev.evidence_ids && <span className="font-code-metric text-[10px] opacity-70"> [{ev.evidence_ids.join(', ')}]</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Areas to verify - computed from the knowledge base; not medical advice */}
              {msg.areas && msg.areas.length > 0 && (
                <div className="mt-space-xs p-space-xs rounded bg-surface-container text-label-sm text-on-surface-variant">
                  <strong className="text-primary">Candidate DISEASE annotations — NOT findings in this patient (not stated in the record; absence not established):</strong>
                  <ul className="list-disc list-inside">
                    {msg.areas.map((a2, i) => <li key={i}>{a2.candidate}: {(a2.disease_annotations_not_stated_in_record || []).join(', ')} <span className="font-code-metric text-[10px] opacity-70">[{a2.evidence_id}]</span></li>)}
                  </ul>
                </div>
              )}
              {msg.patientFindings && msg.patientFindings.length > 0 && msg.role === 'assistant' && !msg.error && msg.provider && (
                <details className="mt-space-2xs text-label-sm text-on-surface-variant">
                  <summary className="cursor-pointer font-bold text-primary">Patient-record findings used ({msg.patientFindings.length})</summary>
                  <p>{msg.patientFindings.map((f) => `${f.name} (${f.hpo_id})`).join('; ')}</p>
                </details>
              )}
              {msg.failureCategory && msg.failureCategory !== 'none' && msg.requestId && (
                <span className="block mt-1 font-code-metric text-[10px] text-on-surface-variant opacity-70">ref {msg.requestId} · {msg.failureCategory}</span>
              )}
              {msg.sources && msg.sources.length > 0 && (
                <details className="mt-space-2xs text-label-sm text-on-surface-variant">
                  <summary className="cursor-pointer font-bold text-primary">Source references ({msg.sources.length})</summary>
                  <ul>{msg.sources.map((r) => <li key={r.evidence_id}><span className="font-code-metric">{r.evidence_id}</span> — {r.source}</li>)}</ul>
                </details>
              )}
            </div>
            {msg.role === 'assistant' && !msg.error && speechSupported && (
              <button type="button" onClick={() => (speakingIdx === idx ? stopSpeaking() : speak(msg.text, idx))}
                className="mt-1 px-1 text-[11px] text-secondary font-semibold flex items-center gap-1" title="Read this answer aloud">
                <span className="material-symbols-outlined text-[14px]">{speakingIdx === idx ? 'stop_circle' : 'volume_up'}</span>
                {speakingIdx === idx ? 'Stop' : 'Read aloud'}
              </button>
            )}
            <span className="text-[10px] text-on-surface-variant mt-1 px-1">
              {msg.timestamp}
            </span>
          </div>
        ))}
        {isLoading && (
          <div className="flex items-center gap-space-xs p-space-sm bg-surface-container-low rounded-xl w-fit text-on-surface-variant">
            <span className="material-symbols-outlined text-[18px] text-secondary animate-spin">progress_activity</span>
            <span className="text-label-md">Doctor Copilot is reasoning through case evidence...</span>
          </div>
        )}
      </div>

      {/* Input Box */}
      <div className="p-space-md bg-surface-container-low border-t border-outline-variant/30">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-space-xs"
        >
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={listening ? 'Listening… speak your question' : 'Ask a question about this patient case or candidate diseases...'}
            disabled={isLoading}
            className="flex-1 px-space-md py-space-sm rounded-xl bg-surface-container-lowest border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary disabled:opacity-50"
          />
          <button
            type="button"
            onClick={toggleListening}
            disabled={isLoading}
            aria-label={listening ? 'Stop dictation' : 'Start voice input'}
            title={SpeechRecognitionCtor ? (listening ? 'Stop dictation' : 'Dictate your question') : 'Voice input is not supported in this browser'}
            className={`px-space-sm py-space-sm rounded-xl border border-outline-variant flex items-center ${listening ? 'bg-error text-on-error animate-pulse' : 'bg-surface-container-lowest text-primary'} disabled:opacity-50`}
          >
            <span className="material-symbols-outlined text-[20px]">{listening ? 'mic' : 'mic_none'}</span>
          </button>
          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="px-space-md py-space-sm rounded-xl bg-secondary text-on-secondary font-label-md font-bold hover:bg-secondary/90 transition-colors disabled:opacity-50 flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
            <span className="hidden sm:inline">Ask Copilot</span>
          </button>
        </form>
        <div className="mt-space-2xs flex flex-wrap items-center gap-space-sm text-[11px] text-on-surface-variant">
          <label className="inline-flex items-center gap-1"><input type="checkbox" checked={autoSend} onChange={(e) => setAutoSend(e.target.checked)} /> Send automatically after dictation</label>
          {speechSupported && (
            <label className="inline-flex items-center gap-1"><input type="checkbox" checked={readAloud} onChange={(e) => { setReadAloud(e.target.checked); if (!e.target.checked) stopSpeaking(); }} /> Read answers aloud</label>
          )}
          <span>Dictation uses your browser's speech service (Chrome/Edge may send audio to the browser vendor). Text reaches this app only when you press Ask.</span>
        </div>
        {voiceMsg && <p className="mt-1 text-[12px] text-error">{voiceMsg}</p>}
      </div>
    </div>
  );
}
