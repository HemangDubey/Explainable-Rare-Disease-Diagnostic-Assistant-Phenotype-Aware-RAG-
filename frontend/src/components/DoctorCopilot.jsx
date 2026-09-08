import React, { useState } from 'react';

const SUGGESTED_QUESTIONS = [
  "Why was this disease candidate prioritized first?",
  "Which patient phenotypes match the leading candidate?",
  "What evidence is contributed by Indian population priors?",
  "What important distinguishing phenotype is missing?",
  "What genetic and confirmatory molecular tests are indicated?"
];

export default function DoctorCopilot({ onAsk, isLoading, currentCase }) {
  const [query, setQuery] = useState('');
  const [conversation, setConversation] = useState([
    {
      role: 'assistant',
      text: "Hello, I am your Explainable AI Doctor Copilot. I can synthesize phenotype alignment, knowledge-base retrieval, and Indian population priors for this patient's case. How can I assist with your clinical evaluation?",
      evidence: [],
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }
  ]);

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
        followUp: response.recommended_follow_up,
        confidence: response.confidence || 'Moderate',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setConversation((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setConversation((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Copilot error: ${err.message}. Please verify the backend is running.`,
          error: true,
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
              <p className="font-body-md whitespace-pre-wrap leading-relaxed">{msg.text}</p>

              {/* Evidence Points */}
              {msg.evidence && msg.evidence.length > 0 && (
                <div className="mt-space-xs pt-space-xs border-t border-outline-variant/20 text-body-sm">
                  <span className="font-bold text-primary block text-label-sm mb-1">
                    Referenced Evidence:
                  </span>
                  <ul className="list-disc list-inside space-y-0.5 text-on-surface-variant">
                    {msg.evidence.map((ev, i) => (
                      <li key={i}>{ev}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Follow-up / Recommendation */}
              {msg.followUp && (
                <div className="mt-space-xs p-space-xs rounded bg-surface-container text-label-sm text-primary flex items-start gap-1">
                  <span className="material-symbols-outlined text-[16px] text-secondary">biotech</span>
                  <span><strong>Next Clinical Step:</strong> {msg.followUp}</span>
                </div>
              )}
            </div>
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
            placeholder="Ask a question about this patient case or candidate diseases..."
            disabled={isLoading}
            className="flex-1 px-space-md py-space-sm rounded-xl bg-surface-container-lowest border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="px-space-md py-space-sm rounded-xl bg-secondary text-on-secondary font-label-md font-bold hover:bg-secondary/90 transition-colors disabled:opacity-50 flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[18px]">send</span>
            <span className="hidden sm:inline">Ask Copilot</span>
          </button>
        </form>
      </div>
    </div>
  );
}
