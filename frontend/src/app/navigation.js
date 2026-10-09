// Single source of truth for internal navigation: sidebar groups, breadcrumbs and page titles all read from here.
// Every entry points at a route or an in-page section that exists. Items with `hash` deep-link into a section of a larger page
// (the Digital Twin hosts phenotype verification, genomic evidence and the evidence network).

export const NAV_GROUPS = [
  {
    id: 'workspace',
    label: 'Workspace',
    items: [
      { id: 'dashboard', path: '/dashboard', icon: 'clinical_notes', label: 'Diagnostic Workspace',
        description: 'Case intake, phenotype extraction and ranked candidates' },
      { id: 'differential', path: '/differential', icon: 'balance', label: 'Differential Diagnosis',
        description: 'Compare the ranked candidates side by side' },
    ],
  },
  {
    id: 'nlp',
    label: 'Clinical NLP',
    items: [
      { id: 'scribe', path: '/clinical-scribe', icon: 'edit_note', label: 'Clinical Scribe',
        description: 'Structure a note, dictate by voice, send to diagnosis' },
      { id: 'verification', path: '/digital-twin', hash: '#twin-phenotypes', icon: 'fact_check', label: 'Phenotype Verification',
        description: 'Review, verify or reject extracted findings' },
      { id: 'copilot', path: '/copilot', icon: 'forum', label: 'AI Doctor Copilot',
        description: 'Grounded questions about the active case' },
    ],
  },
  {
    id: 'evidence',
    label: 'Evidence & Genomics',
    items: [
      { id: 'literature', path: '/evidence', icon: 'menu_book', label: 'Evidence & Literature',
        description: 'Disease evidence profile and PubMed search' },
      { id: 'genomic', path: '/digital-twin', hash: '#twin-genomic', icon: 'genetics', label: 'Genomic Evidence',
        description: 'ClinVar, gnomAD and population comparison' },
      { id: 'network', path: '/digital-twin', hash: '#twin-network', icon: 'hub', label: 'Evidence Network',
        description: 'Findings, HPO terms, candidates and genes' },
    ],
  },
  {
    id: 'simulation',
    label: 'Simulation',
    items: [
      { id: 'twin', path: '/digital-twin', icon: 'accessibility_new', label: 'Clinical Digital Twin',
        description: '3D anatomical view of the case' },
      { id: 'counterfactual', path: '/counterfactual', icon: 'science', label: 'Counterfactual Lab',
        description: 'Add or remove phenotypes and re-rank' },
    ],
  },
  {
    id: 'documents',
    label: 'Documents',
    items: [
      { id: 'reports', path: '/reports', icon: 'description', label: 'Clinical Reports',
        description: 'Generate, review and export case reports' },
      { id: 'cases', path: '/cases', icon: 'folder_open', label: 'Saved Cases',
        description: 'Your stored cases and their history' },
    ],
  },
];

export const NAV_ITEMS = NAV_GROUPS.flatMap((g) => g.items.map((i) => ({ ...i, group: g.label, groupId: g.id })));

// The item matching the current location: an exact path + hash match wins, otherwise the plain (hash-less) item for the path.
export function activeItem(pathname, hash = '') {
  const onPath = NAV_ITEMS.filter((i) => i.path === pathname);
  return onPath.find((i) => i.hash && i.hash === hash) || onPath.find((i) => !i.hash) || null;
}

export function itemHref(item) {
  return item.path + (item.hash || '');
}
