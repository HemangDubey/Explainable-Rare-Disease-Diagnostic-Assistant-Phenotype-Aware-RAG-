"""Unified workspace shell (internal app UI): navigation integrity, reachability, accessibility hooks, design-system rules and the
untouched landing page. Static checks over the frontend source (the app is also exercised in the browser walkthrough)."""
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

SRC = Path("frontend/src")
LANDING_SHA256 = "d3e9fbfb01791a94af5a2c92eb1a4fa9f81e22f72cae8b79280aaa20b1951b36"   # public/landing.html before the redesign
INTERNAL = ["app/AppShell.jsx", "app/Sidebar.jsx", "app/TopBar.jsx", "app/ui.jsx", "app/WorkspaceContext.jsx", "app/navigation.js",
            "pages/DashboardPage.jsx", "pages/DifferentialPage.jsx", "pages/ClinicalScribePage.jsx", "pages/CopilotPage.jsx",
            "pages/EvidencePage.jsx", "pages/CounterfactualPage.jsx", "pages/ReportsPage.jsx", "pages/CasesPage.jsx",
            "pages/DigitalTwinPage.jsx", "components/EvidenceExplorerView.jsx", "components/ReportGeneratorView.jsx"]
# pictographic emoji (incl. sparkles); typographic check marks / crosses used as data or close glyphs are allowed
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF☀-⛿✨]")


def read(rel):
    return (SRC / rel).read_text(encoding="utf-8")


def nav_items():
    """Parse path/hash pairs out of navigation.js (plain JS object literals)."""
    src = read("app/navigation.js")
    return [(m.group(2), m.group(4)) for m in re.finditer(r"id: '([\w-]+)', path: '([^']+)'(, hash: '(#[\w-]+)')?", src)]


class TestNavigation(unittest.TestCase):
    def test_every_nav_target_exists(self):
        app = read("App.jsx")
        routes = set(re.findall(r'<Route path="(/[^"]*)"', app))
        twin = read("pages/DigitalTwinPage.jsx")
        items = nav_items()
        self.assertGreaterEqual(len(items), 12)
        for path, hsh in items:
            self.assertIn(path, routes, f"nav link to missing route {path}")
            if hsh:
                self.assertIn(f'id="{hsh[1:]}"', twin, f"nav hash {hsh} has no section on the page")

    def test_every_route_reachable_from_nav(self):
        routes = set(re.findall(r'<Route path="(/[^"]*)"', read("App.jsx")))
        nav_paths = {p for p, _ in nav_items()}
        self.assertEqual(routes - nav_paths, set(), "routes not reachable from the sidebar")
        for legacy in ("/dashboard", "/clinical-scribe", "/counterfactual", "/digital-twin"):   # existing URLs keep working
            self.assertIn(legacy, routes)

    def test_routes_are_protected_and_share_the_case(self):
        app = read("App.jsx")
        self.assertRegex(app, r"<Protected>\s*<WorkspaceProvider>\s*<AppShell />")
        self.assertIn("Session expired", app)
        self.assertIn('<Route path="*" element={<Navigate to="/dashboard" replace />}', app)
        for page in ("DifferentialPage", "EvidencePage", "ReportsPage"):
            self.assertIn("NeedsCase", read(f"pages/{page}.jsx"))          # honest empty state, never sample results


class TestShellBehaviour(unittest.TestCase):
    def test_sidebar(self):
        sb = read("app/Sidebar.jsx")
        for needle in ('aria-current', 'aria-expanded', 'role="tooltip"', "'Escape'", 'aria-modal="true"', 'Close navigation',
                       'Collapse sidebar', 'Expand sidebar', 'focus-visible:ring', "w-16", "w-64"):
            self.assertIn(needle, sb, needle)

    def test_shell(self):
        sh = read("app/AppShell.jsx")
        self.assertIn("rd_sidebar_collapsed", sh)                       # non-sensitive UI preference only
        self.assertIn("useEffect(() => { setMobileOpen(false); }, [pathname, hash]);", sh)   # drawer closes after navigation
        self.assertIn("lg:pl-16", sh)
        self.assertIn("Skip to content", sh)
        self.assertNotRegex(sh, r"localStorage\.setItem\((?!PREF)")       # nothing else is stored

    def test_topbar(self):
        tb = read("app/TopBar.jsx")
        for needle in ('aria-label="Breadcrumb"', "Log out", "logout", 'aria-haspopup="menu"', "backendStatus"):
            self.assertIn(needle, tb, needle)

    def test_workspace_state_not_persisted(self):
        ctx = read("app/WorkspaceContext.jsx")
        self.assertNotIn("localStorage", ctx)
        self.assertNotIn("sessionStorage", ctx)
        self.assertIn("diagnoseCase", ctx)
        self.assertIn("reasonCase", ctx)


class TestDesignSystem(unittest.TestCase):
    def test_no_emoji_or_gradient_decoration(self):
        for rel in INTERNAL:
            src = read(rel)
            self.assertIsNone(EMOJI.search(src), f"{rel} contains an emoji")
            self.assertNotIn("bg-gradient-to", src, rel)

    def test_tokens_and_components_defined(self):
        tw = Path("frontend/tailwind.config.js").read_text(encoding="utf-8")
        for t in ('"ink"', '"ocean"', '"line"', '"success"', '"warn"', '"danger"'):
            self.assertIn(t, tw)
        css = read("styles/index.css")
        for c in (".ui-card", ".ui-btn-primary", ".ui-alert-error", ".ui-chip-success", ".ui-tab-active", ".ui-spinner"):
            self.assertIn(c, css)

    def test_no_dark_mode(self):
        for rel in INTERNAL:
            self.assertNotIn("dark:", read(rel), rel)

    def test_landing_page_unchanged(self):
        data = Path("frontend/public/landing.html").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), LANDING_SHA256)


if __name__ == "__main__":
    unittest.main()
