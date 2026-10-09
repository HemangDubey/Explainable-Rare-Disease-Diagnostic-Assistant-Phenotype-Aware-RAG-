"""Deterministic clinical-note structurer (Phase 5R).

Every statement in the draft is a VERBATIM span of the clinician's input (with character offsets), so nothing can be invented.
Negation / uncertainty / temporal / relationship attributes are detected with transparent rules and attached to the statement or
mention; they never change the wording. Anything that is not mentioned is reported as `not_provided`, never as absent.
No language model is involved in the facts (see `generated_by`). All rules are heuristics: a clinician must review the draft.
"""
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.scribe.draft_schema import (DRAFT_STATUS_LABEL, SECTION_TITLES, Draft, DraftPhenotype, DraftSection, DraftStatement,
                                     SourceSpan, SECTION_ORDER)

# --- rules ------------------------------------------------------------------------------------------------------------
_SCOPE_BREAK = re.compile(r"[.;:\n]|\b(?:but|however|although|though|except|while|whereas)\b", re.I)
_NEG_PRE = re.compile(r"\b(?:no|denies|denied|denying|without|never|negative\s+for|absence\s+of|free\s+of|"
                      r"no\s+evidence\s+of|no\s+history\s+of|does\s+not\s+have|do(?:es)?n't\s+have|did\s+not\s+have|has\s+not\s+had|"
                      r"not\s+(?:have|had|show|shown|exhibit|report|reported))\b", re.I)
_NEG_POST = re.compile(r"^\W*(?:(?:is|was|are|were|has\s+been|have\s+been)\s+)?(?:not\s+(?:present|observed|seen|noted|reported)|absent|"
                       r"negative|denied|ruled\s+out|excluded)\b", re.I)
_UNC = re.compile(r"\b(?:possible|possibly|probable|probably|suspected|suspicion\s+of|suspect|likely|query|\?|may\s+have|might\s+have|"
                  r"could\s+be|appears?\s+to|\?\s*|questionable|cannot\s+exclude|unclear|uncertain|r/o|rule\s+out|differential)\b|\?", re.I)
_PENDING = re.compile(r"\b(?:pending|awaited|awaiting|to\s+be\s+(?:assessed|confirmed|done|evaluated)|under\s+(?:investigation|evaluation)|"
                      r"not\s+yet\s+(?:assessed|done|confirmed))\b", re.I)
_TEMPORAL = re.compile(
    r"\b(?:(?:began|begun|started|starting|onset|first\s+noticed|noticed|appeared|developed|since|from|at)\s+(?:around|about|approximately|at|age|aged|"
    r"the\s+age\s+of|birth|infancy|childhood|early|\d)[^.;,]*"
    r"|(?:around|about|approximately)\s+(?:age|aged)\s+\w+"
    r"|(?:at|since|from)\s+(?:birth|infancy|childhood)"
    r"|(?:for|over|during)\s+(?:the\s+(?:past|last)\s+)?(?:\d+|one|two|three|four|five|six|several|few)\s+(?:day|week|month|year)s?"
    r"|\d+\s+(?:day|week|month|year)s?\s+(?:ago|old|duration)"
    r"|age\s+(?:of\s+)?(?:\d+|\w+)\s*(?:years?|months?|weeks?|days?)?"
    r"|\bsince\s+\w+"
    r"|(?:recurrent|episodic|intermittent|daily|weekly|monthly|frequent|occasional|progressive|worsening|improving|static)\b[^.;,]*"
    r"|(?:mild|moderate|severe|profound)\b)", re.I)
_REL = re.compile(r"\b(mother|father|sibling|brother|sister|uncle|aunt|aunty|grandmother|grandfather|grandparents?|cousin|parents?|"
                  r"maternal|paternal|twin|son|daughter|family\s+history|relatives?)\b", re.I)
_REPORTER = re.compile(r"\b(?:mother|father|parents?|family|caregiver|patient|guardian|teacher)\s+(?:reports?|reported|states?|stated|says?|said|notes?|noted|"
                       r"noticed|describes?|described|denies|denied|observed|is\s+worried|are\s+worried|is\s+concerned|are\s+concerned)\b", re.I)
_PRESENT = re.compile(r"\b(?:presents?|presenting|presented|complain\w*|referred\s+(?:for|with)|chief\s+complaint|c/o|concern(?:s|ed)?\s+(?:about|regarding|with)|"
                      r"brought\s+(?:in\s+)?(?:for|with|because))\b", re.I)
_EXAM = re.compile(r"\b(?:on\s+exam(?:ination)?|exam(?:ination)?\s+(?:shows?|reveals?|findings?|was)|o/e|examined|observed\s+(?:on|to)|"
                   r"height|weight|head\s+circumference|bmi|blood\s+pressure|bp|heart\s+rate|tone\s+(?:is|was)|reflexes|gait\s+(?:is|was)|"
                   r"clinically\s+observed|auscultation|palpation)\b", re.I)
_INV = re.compile(r"\b(?:mri|ct\s+scan|ct\b|eeg|ecg|ekg|emg|karyotype|exome|genome|sequencing|gene\s+panel|panel|genetic\s+test\w*|lab(?:oratory)?|"
                  r"blood\s+(?:test|work|count)|serum|urine|biopsy|x-?ray|ultrasound|echo(?:cardiogram)?|investigations?|results?|"
                  r"screen(?:ing)?|assay|culture|microarray|cma)\b", re.I)
_DX = re.compile(r"\b(?:diagnosed\s+with|known\s+(?:case\s+of)?|diagnosis\s+of|confirmed\s+(?:case\s+of|diagnosis)|"
                 r"established\s+diagnosis|has\s+a\s+diagnosis|carries\s+(?:a\s+)?diagnosis|syndrome\s+was\s+diagnosed)\b", re.I)
_HIST = re.compile(r"\b(?:history\s+of|previous(?:ly)?|past\s+medical|surgery|surgical|operated|medications?|taking|treated\s+with|"
                   r"born|birth|premature|preterm|term|pregnancy|antenatal|neonatal|delivery|immuni[sz]ation|allerg\w+|admitted|hospitali[sz]ed)\b", re.I)
_PROGRESSION = re.compile(r"\b(?:began|started|onset|since|progress\w*|worsen\w*|episodes?|gradual\w*|noticed|first\s+noticed|over\s+the)\b", re.I)


def split_statements(text: str) -> List[Dict[str, Any]]:
    """Sentence-level spans (verbatim). Splits on . ; newline, and on '?' only when followed by space+capital."""
    out, start = [], 0
    for m in re.finditer(r"[.;\n]+(?=\s|$)", text):
        seg = text[start:m.start()]
        if seg.strip():
            ls = start + (len(seg) - len(seg.lstrip()))
            out.append({"start": ls, "end": start + len(seg.rstrip()), "text": seg.strip()})
        start = m.end()
    tail = text[start:]
    if tail.strip():
        ls = start + (len(tail) - len(tail.lstrip()))
        out.append({"start": ls, "end": start + len(tail.rstrip()), "text": tail.strip()})
    return out


def _clause_before(text: str, pos: int) -> str:
    """Text before `pos` back to the nearest scope break (commas do NOT break scope: 'no seizures, ataxia or hypotonia')."""
    seg = text[:pos]
    last = 0
    for m in _SCOPE_BREAK.finditer(seg):
        last = m.end()
    return seg[last:]


def mention_flags(statement_text: str, start: int, end: int) -> Dict[str, bool]:
    """Negation / uncertainty / pending for one mention, from the clause before it and a short window after it."""
    before = _clause_before(statement_text, start)
    after = statement_text[end:end + 40]
    neg = bool(_NEG_PRE.search(before + " " + statement_text[start:end])) or bool(_NEG_POST.search(after))
    # a negation cue followed by the mention across an intervening *positive* cue is not trusted, but we err towards flagging
    unc = bool(_UNC.search(before)) or bool(re.match(r"^\W*\?", after))
    pend = bool(_PENDING.search(statement_text))
    return {"negated": neg, "uncertain": unc, "pending": pend}


def find_temporal(statement_text: str) -> List[str]:
    out = []
    for m in _TEMPORAL.finditer(statement_text):
        t = m.group(0).strip(" ,")
        if t and t not in out and len(t) > 2:
            out.append(t)
    return out


def _temporal_near(text: str, phrases: List[str], start: int, end: int) -> List[str]:
    """Temporal phrases that overlap the mention or start within 40 characters after it (never broadcast to unrelated mentions)."""
    out = []
    for ph in phrases:
        i = text.find(ph)
        if i >= 0 and (i < end and i + len(ph) > start or 0 <= i - end <= 40):
            out.append(ph)
    return out


def _subject(text: str) -> Dict[str, Optional[str]]:
    """Whose finding is this? 'Mother reports the child has X' -> patient (reported by mother); 'Mother has X' -> mother."""
    rel = _REL.search(text)
    rep = _REPORTER.search(text)
    reporter = "observed" if re.search(r"\b(?:on\s+exam|observed|examined|o/e|noted\s+on)\b", text, re.I) else ("reported" if rep else "unspecified")
    if rel and not rep:
        return {"subject": "relative", "relationship": rel.group(1).lower(), "reporting": reporter}
    if rel and rep and re.search(r"family\s+history|\b(?:brother|sister|sibling|uncle|aunt|cousin|grand\w+)\b", text, re.I):
        # e.g. 'Mother reports family history of epilepsy' -> relative finding reported by mother
        return {"subject": "relative", "relationship": rel.group(1).lower(), "reporting": reporter}
    return {"subject": "patient", "relationship": None, "reporting": reporter}


def sections_for(text: str, subject: Dict[str, Optional[str]], has_mentions: bool) -> List[str]:
    """Cue-based, multi-assignment. Statements that match nothing go to review notes as 'unclassified'."""
    s: List[str] = []
    rel = subject["subject"] == "relative"
    if rel:
        s.append("family_history")
    if not rel and _PRESENT.search(text):
        s.append("presenting_concerns")
    if not rel and _EXAM.search(text):
        s.append("examination_findings")
    if _INV.search(text):
        s.append("investigations_and_results")
    if not rel and _DX.search(text):
        s.append("known_diagnoses")
    if not rel and _HIST.search(text):
        s.append("relevant_medical_history")
    if not rel and (find_temporal(text) or _PROGRESSION.search(text)) and has_mentions:
        s.append("history_of_present_illness")
    if not rel and has_mentions and "examination_findings" not in s:
        s.append("reported_symptoms_and_phenotypes")
    return s


Extractor = Callable[[str], List[Dict[str, Any]]]
"""extractor(statement_text) -> [{mention, start, end, hpo_id|None, hpo_term|None, mapping_status, mapping_score, candidates?}]"""


class NoteStructurer:
    def __init__(self, extractor: Optional[Extractor] = None):
        self.extractor = extractor

    def _extract(self, text: str, seg: Dict[str, Any]) -> List[Dict[str, Any]]:
        """The NER is sensitive to the sentence-final period (it can miss a mention with or without it), so the statement is extracted
        both ways and the mentions are merged by span (longest span wins)."""
        variants = [seg["text"]]
        if seg["end"] < len(text) and text[seg["end"]] in ".;":
            variants.append(text[seg["start"]:seg["end"] + 1])
        merged: List[Dict[str, Any]] = []
        for v in variants:
            for m in self.extractor(v) or []:
                clash = next((x for x in merged if m["start"] < x["end"] and x["start"] < m["end"]), None)
                if clash is None:
                    merged.append(m)
                elif (m["end"] - m["start"]) > (clash["end"] - clash["start"]):
                    merged[merged.index(clash)] = m
        return sorted(merged, key=lambda x: x["start"])

    def structure(self, text: str, supplied_phenotypes: Optional[List[str]] = None, input_status: Optional[Dict[str, Any]] = None) -> Draft:
        text = text or ""
        stmts: List[DraftStatement] = []
        phenos: List[DraftPhenotype] = []
        review_notes: List[str] = []
        sections: Dict[str, List[str]] = {k: [] for k in SECTION_ORDER}
        unclassified: List[str] = []
        extractor_error: Optional[str] = None

        for i, seg in enumerate(split_statements(text), 1):
            sid = f"S{i}"
            subj = _subject(seg["text"])
            mentions: List[Dict[str, Any]] = []
            if self.extractor is not None:
                try:
                    # the NER is sensitive to the sentence-final period, so pass the statement with its original terminator
                    mentions = self._extract(text, seg)
                except Exception as e:  # extractor failure must not lose the statement
                    extractor_error = type(e).__name__
                    mentions = []
            # statement-level flags: any cue anywhere in the statement (conservative marker for the reviewer)
            st_unc = bool(_UNC.search(seg["text"]))
            st_pend = bool(_PENDING.search(seg["text"]))
            st_neg_cue = bool(_NEG_PRE.search(seg["text"]) or re.search(r"\b(?:absent|ruled\s+out)\b", seg["text"], re.I))
            temporal = find_temporal(seg["text"])
            st = DraftStatement(id=sid, text=seg["text"], source=SourceSpan(start=seg["start"], end=seg["end"]),
                                subject=subj["subject"], relationship=subj["relationship"], reporting=subj["reporting"],
                                contains_negation_cue=st_neg_cue, contains_uncertainty_cue=st_unc, pending=st_pend, temporal=temporal)
            for j, m in enumerate(mentions, 1):
                fl = mention_flags(seg["text"], m["start"], m["end"])
                if subj["subject"] == "relative":
                    status = "relative_finding"
                else:
                    status = "negated" if fl["negated"] else ("uncertain" if (fl["uncertain"] or fl["pending"]) else "present")
                phenos.append(DraftPhenotype(
                    id=f"{sid}-P{j}", statement_id=sid, mention=seg["text"][m["start"]:m["end"]], status=status,
                    subject=subj["subject"], relationship=subj["relationship"],
                    hpo_id=m.get("hpo_id"), hpo_name=m.get("hpo_term"), normalization_status=m.get("mapping_status", "not_attempted"),
                    mapping_score=m.get("mapping_score"), candidates=(m.get("candidates") or m.get("suggestions") or [])[:3],
                    source=SourceSpan(start=seg["start"] + m["start"], end=seg["start"] + m["end"]),
                    temporal=_temporal_near(seg["text"], temporal, m["start"], m["end"])))
            st.n_mentions = len(mentions)
            stmts.append(st)
            secs = sections_for(seg["text"], subj, bool(mentions))
            if not secs:
                unclassified.append(sid)
            for sec in secs:
                sections[sec].append(sid)

        # clinician-supplied structured phenotype list: kept as clinician-entered, never mixed with note facts
        for k, name in enumerate(supplied_phenotypes or [], 1):
            name = (name or "").strip()
            if not name:
                continue
            sid = f"U{k}"
            stmts.append(DraftStatement(id=sid, text=name, source=SourceSpan(start=-1, end=-1, input="clinician_phenotype_list"),
                                        subject="patient", reporting="unspecified", origin="clinician_supplied"))
            sections["reported_symptoms_and_phenotypes"].append(sid)
            ex = None
            if self.extractor is not None:
                try:
                    ex = self.extractor(name)
                except Exception:
                    ex = None
            m = (ex or [{}])[0] if ex else {}
            phenos.append(DraftPhenotype(id=f"{sid}-P1", statement_id=sid, mention=name, status="present", subject="patient",
                                         hpo_id=m.get("hpo_id"), hpo_name=m.get("hpo_term"),
                                         normalization_status=m.get("mapping_status", "not_attempted"), mapping_score=m.get("mapping_score"),
                                         candidates=(m.get("candidates") or m.get("suggestions") or [])[:3],
                                         source=SourceSpan(start=-1, end=-1, input="clinician_phenotype_list")))

        by_id = {s.id: s for s in stmts}
        secs_out: Dict[str, DraftSection] = {}
        for key in SECTION_ORDER:
            if key in ("missing_or_unverified_information", "clinician_review_notes"):
                continue
            ids = sections[key]
            secs_out[key] = DraftSection(title=SECTION_TITLES[key], status="provided" if ids else "not_provided",
                                         items=[by_id[i] for i in ids])

        missing: List[str] = []
        for key in SECTION_ORDER:
            if key in secs_out and secs_out[key].status == "not_provided":
                missing.append(f"{SECTION_TITLES[key]}: not provided in the input (this does not mean it is absent)")
        for st in stmts:
            if st.contains_uncertainty_cue or st.pending:
                missing.append(f"{st.id}: marked uncertain or pending in the source — unverified (\"{st.text}\")")
        for p in phenos:
            if p.status != "relative_finding" and p.normalization_status in ("unmatched", "ambiguous", "non_phenotype", "not_attempted"):
                missing.append(f"{p.id}: \"{p.mention}\" is not mapped to a single HPO term ({p.normalization_status})")
        secs_out["missing_or_unverified_information"] = DraftSection(title=SECTION_TITLES["missing_or_unverified_information"],
                                                                      status="provided" if missing else "not_provided",
                                                                      items=[DraftStatement(id=f"M{i}", text=t, source=SourceSpan(start=-1, end=-1, input="system"),
                                                                                            origin="system") for i, t in enumerate(missing, 1)])
        if unclassified:
            review_notes.append("Statements not assigned to any section (kept verbatim; please place or remove): " + ", ".join(unclassified))
        if any(s.contains_negation_cue for s in stmts):
            review_notes.append("Negation cues were detected. Negated findings are listed as 'negated' and excluded from the phenotype set sent to diagnosis; verify the scope of each negation.")
        if extractor_error:
            review_notes.append(f"Phenotype extraction failed for some statements ({extractor_error}); phenotypes may be incomplete.")
        if self.extractor is None:
            review_notes.append("No phenotype extractor was available; phenotypes were not normalised to HPO.")
        review_notes.append("Rule-based structuring: negation, uncertainty and timing rules are heuristic. A clinician must review every statement.")
        secs_out["clinician_review_notes"] = DraftSection(
            title=SECTION_TITLES["clinician_review_notes"], status="provided",
            items=[DraftStatement(id=f"N{i}", text=t, source=SourceSpan(start=-1, end=-1, input="system"), origin="system")
                   for i, t in enumerate(review_notes, 1)])

        diag_terms = [p.mention for p in phenos if p.status == "present" and p.subject == "patient"]
        excluded = {"negated": sum(p.status == "negated" for p in phenos), "uncertain": sum(p.status == "uncertain" for p in phenos),
                    "relative_finding": sum(p.status == "relative_finding" for p in phenos)}
        return Draft(
            draft_id=uuid.uuid4().hex[:12], status=DRAFT_STATUS_LABEL, created_at=datetime.now(timezone.utc).isoformat(),
            generated_by="deterministic_structurer", provider={"structuring": "deterministic rules", "language_model": "not_used",
                                                              "note": "facts are verbatim spans of the input; no model writes clinical content"},
            source_text=text, statements=stmts, sections=secs_out, phenotypes=phenos,
            diagnosis_input=("Patient presents with " + ", ".join(dict.fromkeys(diag_terms)) + ".") if diag_terms else "",
            diagnosis_input_excluded=excluded, input_check=input_status or {})
