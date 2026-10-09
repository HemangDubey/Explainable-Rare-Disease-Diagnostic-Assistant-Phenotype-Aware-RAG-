import React, { useState, useEffect } from 'react';
import { createScribeDraft, updateScribeDraft } from '../api/client';

const SAMPLE_CLINICAL_NOTE = "Patient presents with hypotonia, short stature, developmental delay and recurrent seizures.";
const ORDER = ['presenting_concerns', 'history_of_present_illness', 'reported_symptoms_and_phenotypes', 'relevant_medical_history',
  'family_history', 'examination_findings', 'investigations_and_results', 'known_diagnoses', 'missing_or_unverified_information', 'clinician_review_notes'];
const READ_ONLY = ['missing_or_unverified_information', 'clinician_review_notes'];

function Badge({ children, tone = 'neutral' }) {
  const cls = tone === 'warn' ? 'bg-error-container text-on-error-container'
    : tone === 'info' ? 'bg-secondary-fixed/60 text-on-secondary-fixed'
      : 'bg-surface-container text-on-surface-variant';
  return <span className={`px-space-xs py-0.5 rounded text-[10px] font-bold ${cls}`}>{children}</span>;
}

export default function ClinicalScribeView({ onSendToDiagnosis }) {
  const [inputText, setInputText] = useState(SAMPLE_CLINICAL_NOTE);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [onlyVerified, setOnlyVerified] = useState(true);   // default: only phenotypes the clinician has marked verified are sent to diagnosis

  // unsaved-edit warning on tab close / reload
  useEffect(() => {
    const h = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', h);
    return () => window.removeEventListener('beforeunload', h);
  }, [dirty]);

  const handleGenerate = async () => {
    if (!inputText.trim()) return;
    if (dirty && !window.confirm('You have unsaved edits to the current draft. Discard them and generate a new draft?')) return;
    setIsLoading(true);
    setError(null);
    setSaveMsg(null);
    try {
      const data = await createScribeDraft({ clinical_text: inputText });
      setDraft(data);
      setDirty(false);
    } catch (err) {
      setError(err.message || 'Failed to generate the draft');
    } finally {
      setIsLoading(false);
    }
  };

  const patchStatement = (id, patch) => {
    setDraft((d) => ({
      ...d,
      statements: d.statements.map((s) => (s.id === id ? { ...s, ...patch } : s)),
      sections: Object.fromEntries(Object.entries(d.sections).map(([k, sec]) => [k, { ...sec, items: sec.items.map((s) => (s.id === id ? { ...s, ...patch } : s)) }]))
    }));
    setDirty(true);
  };
  const patchPheno = (id, patch) => {
    setDraft((d) => ({ ...d, phenotypes: d.phenotypes.map((p) => (p.id === id ? { ...p, ...patch } : p)) }));
    setDirty(true);
  };

  const handleSave = async (reviewState) => {
    if (!draft) return;
    setIsSaving(true);
    setSaveMsg(null);
    try {
      if (!draft.saved) {
        // not persisted yet (e.g. the earlier save failed): create a fresh saved draft from the same note is NOT done silently
        throw new Error('This draft is not saved on the server, so edits cannot be persisted. Regenerate the draft to try saving again.');
      }
      const upd = await updateScribeDraft({
        draft_id: draft.draft_id,
        update: {
          statements: draft.statements.filter((s) => s.origin !== 'system').map((s) => ({ id: s.id, text: s.text, verified: s.verified, removed: s.removed })),
          phenotypes: draft.phenotypes.map((p) => ({ id: p.id, verified: p.verified, status: p.status === 'relative_finding' ? undefined : p.status })),
          clinician_notes: draft.clinician_notes || '',
          review_state: reviewState || undefined
        }
      });
      setDraft(upd);
      setDirty(false);
      setSaveMsg({ ok: true, text: 'Saved. The draft remains a draft — it is not signed or approved.' });
    } catch (err) {
      setSaveMsg({ ok: false, text: `NOT SAVED: ${err.message}` });
    } finally {
      setIsSaving(false);
    }
  };

  const presentPatient = draft ? draft.phenotypes.filter((p) => p.status === 'present' && p.subject === 'patient'
    && !draft.statements.find((s) => s.id === p.statement_id)?.removed) : [];
  const livePositive = onlyVerified ? presentPatient.filter((p) => p.verified) : presentPatient;
  const diagnosisText = livePositive.length ? `Patient presents with ${[...new Set(livePositive.map((p) => p.mention))].join(', ')}.` : '';

  const handleContinue = () => {
    if (!diagnosisText) return;
    if (dirty && !window.confirm('Your edits are not saved. Continue to diagnosis with the current (unsaved) phenotype selection?')) return;
    onSendToDiagnosis && onSendToDiagnosis(diagnosisText, draft.draft_id);
  };

  return (
    <div className="flex flex-col gap-space-xl">
      {/* Input Card */}
      <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
        <div className="flex items-center justify-between mb-space-xs">
          <label className="font-title-sm text-primary font-bold flex items-center gap-space-2xs">
            <span className="material-symbols-outlined text-secondary text-[20px]">edit_note</span>
            Clinical note (this patient only):
          </label>
          <button
            onClick={() => setInputText(SAMPLE_CLINICAL_NOTE)}
            className="text-[12px] px-space-xs py-0.5 rounded bg-surface-container hover:bg-surface-container-high text-primary font-semibold transition-colors"
          >
            Load Sample Narrative
          </button>
        </div>
        <textarea
          rows={4}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Enter the clinician's observations. Only what is written here appears in the draft."
          className="w-full p-space-md rounded-xl bg-surface border border-outline-variant text-body-md text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary leading-relaxed"
        />
        <div className="flex items-center justify-between mt-space-md pt-space-xs border-t border-outline-variant/20">
          <span className="text-label-sm text-on-surface-variant">
            Statements are copied verbatim from your note; nothing is added. Uses the existing NER and HPO normaliser.
          </span>
          <button
            onClick={handleGenerate}
            disabled={isLoading || !inputText.trim()}
            className="inline-flex items-center gap-space-xs px-space-lg py-space-sm rounded-xl bg-primary text-on-primary font-label-lg font-bold hover:bg-primary/90 transition-all shadow-md disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[20px]">{isLoading ? 'progress_activity' : 'fact_check'}</span>
            <span>{isLoading ? 'Structuring…' : 'Generate Draft'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-space-md rounded-xl bg-error-container text-on-error-container font-label-md">{error}</div>
      )}

      {!draft && !error && !isLoading && (
        <div className="p-space-3xl text-center text-on-surface-variant bg-surface-container-lowest rounded-2xl border border-outline-variant/30">
          <span className="material-symbols-outlined text-[56px] text-secondary mb-space-xs">description</span>
          <h3 className="font-title-lg text-primary font-bold">No draft yet</h3>
          <p className="font-body-md mt-1 max-w-md mx-auto">Enter a clinical note and generate a structured draft for clinician review.</p>
        </div>
      )}

      {draft && (
        <div className="flex flex-col gap-space-lg">
          {/* Status bar */}
          <div className="flex flex-wrap items-center justify-between gap-space-xs p-space-md rounded-2xl bg-surface-container-lowest border border-outline-variant/30">
            <div className="flex flex-wrap items-center gap-space-xs">
              <span className="px-space-sm py-1 rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-bold text-label-md">{draft.status}</span>
              <Badge tone={draft.saved ? 'info' : 'warn'}>{draft.saved ? `SAVED · ${draft.draft_id}` : 'NOT SAVED'}</Badge>
              {dirty && <Badge tone="warn">UNSAVED EDITS</Badge>}
              <Badge>structured by deterministic rules · no language model used</Badge>
            </div>
            <div className="flex gap-space-xs">
              <button onClick={() => handleSave()} disabled={isSaving || !dirty || !draft.saved}
                className="px-space-md py-space-xs rounded-xl bg-primary text-on-primary font-label-md font-bold disabled:opacity-50">
                {isSaving ? 'Saving…' : 'Save edits'}
              </button>
              <button onClick={() => handleSave('reviewed')} disabled={isSaving || !draft.saved}
                className="px-space-md py-space-xs rounded-xl bg-surface-container text-primary font-label-md font-bold disabled:opacity-50"
                title="Marks the draft as clinician-reviewed. It is still a draft and is never signed or approved automatically.">
                Mark as reviewed
              </button>
            </div>
          </div>
          {!draft.saved && (
            <div className="p-space-sm rounded-xl bg-error-container text-on-error-container text-body-sm">
              {draft.persistence?.message || 'This draft was not saved on the server.'} Edits made here cannot be persisted.
            </div>
          )}
          {saveMsg && (
            <div className={`p-space-sm rounded-xl text-body-sm ${saveMsg.ok ? 'bg-secondary-fixed/40 text-on-secondary-fixed' : 'bg-error-container text-on-error-container'}`}>{saveMsg.text}</div>
          )}
          {draft.input_check?.quality_gate && draft.input_check.quality_gate !== 'VALID_CLINICAL' && (
            <div className="p-space-sm rounded-xl bg-surface-container text-body-sm text-on-surface-variant">Input quality check: {draft.input_check.quality_gate}.</div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
            {/* Sections */}
            <div className="lg:col-span-8 flex flex-col gap-space-md">
              {ORDER.map((key) => {
                const sec = draft.sections[key];
                if (!sec) return null;
                const editable = !READ_ONLY.includes(key);
                const items = sec.items.filter((s) => !s.removed);
                return (
                  <div key={key} className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
                    <div className="flex items-center justify-between mb-space-xs">
                      <h4 className="font-title-sm text-primary font-bold">{sec.title}</h4>
                      <Badge tone={items.length ? 'info' : 'neutral'}>{items.length ? `${items.length} item(s)` : 'not provided'}</Badge>
                    </div>
                    {items.length === 0 ? (
                      <p className="text-body-sm text-on-surface-variant italic">Not provided in the input. This does not mean it is absent.</p>
                    ) : (
                      <ul className="flex flex-col gap-space-xs">
                        {items.map((s) => (
                          <li key={s.id} className="p-space-xs rounded-lg bg-surface-container-low border border-outline-variant/20">
                            {editable ? (
                              <textarea rows={2} value={s.text} onChange={(e) => patchStatement(s.id, { text: e.target.value })}
                                className="w-full p-space-xs rounded-md bg-surface border border-outline-variant text-body-sm text-on-surface" />
                            ) : (
                              <p className="text-body-sm text-on-surface">{s.text}</p>
                            )}
                            <div className="flex flex-wrap items-center gap-space-2xs mt-space-2xs">
                              <span className="font-code-metric text-[10px] text-on-surface-variant">{s.id}{s.source.start >= 0 ? ` · chars ${s.source.start}–${s.source.end}` : ` · ${s.source.input.replace('_', ' ')}`}</span>
                              {s.origin === 'clinician_edit' && <Badge tone="info">edited</Badge>}
                              {s.origin === 'clinician_supplied' && <Badge tone="info">clinician-entered</Badge>}
                              {s.subject === 'relative' && <Badge tone="warn">relative: {s.relationship}</Badge>}
                              {s.contains_negation_cue && <Badge tone="warn">negation cue</Badge>}
                              {s.contains_uncertainty_cue && <Badge tone="warn">uncertain</Badge>}
                              {s.pending && <Badge tone="warn">pending</Badge>}
                              {s.reporting !== 'unspecified' && <Badge>{s.reporting}</Badge>}
                              {s.temporal.map((t) => <Badge key={t} tone="info">timing: {t}</Badge>)}
                              {editable && s.origin !== 'system' && (
                                <>
                                  <label className="inline-flex items-center gap-1 text-[11px] text-on-surface-variant">
                                    <input type="checkbox" checked={!!s.verified} onChange={(e) => patchStatement(s.id, { verified: e.target.checked })} /> verified
                                  </label>
                                  <button className="text-[11px] text-error font-semibold" onClick={() => patchStatement(s.id, { removed: true })}>remove</button>
                                </>
                              )}
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
              <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
                <h4 className="font-title-sm text-primary font-bold mb-space-xs">Clinician notes (free text)</h4>
                <textarea rows={3} value={draft.clinician_notes || ''} maxLength={5000}
                  onChange={(e) => { setDraft({ ...draft, clinician_notes: e.target.value }); setDirty(true); }}
                  className="w-full p-space-xs rounded-md bg-surface border border-outline-variant text-body-sm" placeholder="Your own review comments…" />
              </div>
            </div>

            {/* Right column */}
            <div className="lg:col-span-4 flex flex-col gap-space-lg">
              <div className="bg-surface-container-lowest rounded-2xl p-space-lg shadow-sm border border-outline-variant/30">
                <h4 className="font-label-md text-primary font-bold mb-space-xs flex items-center gap-space-3xs">
                  <span className="material-symbols-outlined text-[16px] text-secondary">schema</span>
                  Phenotypes ({draft.phenotypes.length})
                </h4>
                {draft.phenotypes.length === 0 && <p className="text-body-sm text-on-surface-variant">No phenotype mentions were found in the input.</p>}
                <div className="flex flex-col gap-space-xs">
                  {draft.phenotypes.map((p) => (
                    <div key={p.id} className="p-space-xs rounded-lg bg-surface-container-low border border-outline-variant/20 text-body-sm">
                      <div className="flex items-center justify-between gap-space-xs">
                        <span className="font-bold text-on-surface">{p.mention}</span>
                        {p.status === 'relative_finding' ? <Badge tone="warn">relative: {p.relationship}</Badge> : (
                          <select value={p.status} onChange={(e) => patchPheno(p.id, { status: e.target.value })}
                            className="text-[11px] rounded bg-surface border border-outline-variant">
                            <option value="present">present</option><option value="negated">negated</option><option value="uncertain">uncertain</option>
                          </select>
                        )}
                      </div>
                      <div className="font-code-metric text-[10px] text-on-surface-variant mt-1">
                        {p.hpo_id ? `${p.hpo_id} · ${p.hpo_name} · ${p.normalization_status}` : `no HPO term (${p.normalization_status})`}
                      </div>
                      {!p.hpo_id && p.candidates?.length > 0 && (
                        <div className="text-[10px] text-on-surface-variant">suggestions: {p.candidates.map((c) => c.name || c.term || c.hpo_id).join(', ')}</div>
                      )}
                      <label className="inline-flex items-center gap-1 text-[11px] text-on-surface-variant mt-1">
                        <input type="checkbox" checked={!!p.verified} onChange={(e) => patchPheno(p.id, { verified: e.target.checked })} /> verified
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-primary text-on-primary rounded-2xl p-space-lg shadow-md flex flex-col justify-between">
                <div>
                  <h4 className="font-title-md font-bold mb-space-2xs text-on-primary">Send to diagnostic analysis</h4>
                  <p className="font-body-sm text-slate-300 mb-space-xs">
                    Only phenotypes marked <b>present</b> for the patient{onlyVerified ? <> <b>and verified</b></> : ''} are sent. Negated, uncertain and relatives' findings are excluded
                    ({livePositive.length} sent; {draft.phenotypes.filter((p) => p.status === 'negated').length} negated, {draft.phenotypes.filter((p) => p.status === 'uncertain').length} uncertain,
                    {' '}{draft.phenotypes.filter((p) => p.status === 'relative_finding').length} relative excluded).
                  </p>
                  <label className="flex items-center gap-1 text-label-sm text-slate-200 mb-space-2xs">
                    <input type="checkbox" checked={onlyVerified} onChange={(e) => setOnlyVerified(e.target.checked)} /> Send only clinician-verified phenotypes
                  </label>
                  <p className="font-code-metric text-label-sm text-slate-200 mb-space-md">
                    {diagnosisText || (onlyVerified && presentPatient.length ? `${presentPatient.length} present phenotype(s) are not verified yet. Tick “verified” on each, or untick the option above to send them unverified.` : 'No present phenotype to send.')}
                  </p>
                </div>
                <button onClick={handleContinue} disabled={!diagnosisText}
                  className="w-full py-space-sm px-space-md rounded-xl bg-secondary hover:bg-secondary/90 text-on-secondary font-label-lg font-bold transition-all shadow-md flex items-center justify-center gap-space-xs disabled:opacity-50">
                  <span>Continue to Diagnostic Analysis</span>
                  <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>
          <div className="p-space-sm rounded-xl bg-surface-container text-on-surface-variant text-label-sm flex items-center gap-space-xs border border-outline-variant/20">
            <span className="material-symbols-outlined text-secondary text-[18px]">info</span>
            <span>{draft.disclaimer}</span>
          </div>
        </div>
      )}
    </div>
  );
}
