"""The assistant's links must open real pages.

The first allow-list pointed at /wallet, /portfolio, /account, /family and /broker: routes the
SPA never had, so every one of those link cards landed on the 404 page. These tests read the
SPA source itself, so a renamed route or tab fails here instead of in front of an investor:
  * every allow-listed path is a route declared in src/App.tsx;
  * every ``?tab=`` value is a tab the target page opens from the URL;
  * developer profiles are linkable, including a developer whose slug is not Latin;
  * links the model types by hand (markdown or bare, one or more segments) are recognised
    against the same allow-list.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.core.errors import AppError
from app.services.assistant import guard

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP_TSX = ROOT / "src" / "App.tsx"
DASHBOARD_TSX = ROOT / "src" / "pages" / "InvestorDashboard.tsx"
SETTINGS_TSX = ROOT / "src" / "pages" / "AccountSettings.tsx"


def _spa_routes() -> list[re.Pattern]:
    paths = re.findall(r'path="([^"]+)"', APP_TSX.read_text(encoding="utf-8"))
    return [re.compile("^" + re.sub(r":[A-Za-z]+", r"[^/]+", p) + "$") for p in paths if p != "*"]


def _tabs(source: pathlib.Path, const: str) -> set[str]:
    m = re.search(const + r"\s*=\s*\[([^\]]*)\]", source.read_text(encoding="utf-8"))
    assert m, f"{const} not found in {source.name}"
    return set(re.findall(r'"([a-z-]+)"', m.group(1)))


TAB_SOURCES = {
    "/dashboard": (DASHBOARD_TSX, "validTabs"),
    "/settings": (SETTINGS_TSX, "SETTINGS_TABS"),
}


@pytest.mark.parametrize("route_id", sorted(guard.DEEP_LINKS))
def test_every_deep_link_opens_a_real_page(route_id):
    pattern, _label = guard.DEEP_LINKS[route_id]
    path, _, query = pattern.replace("{slug}", "sample-slug").partition("?")
    assert any(r.match(path) for r in _spa_routes()), f"{route_id}: {path} is not an SPA route"
    if query:
        key, _, tab = query.partition("=")
        assert key == "tab", f"{route_id}: only ?tab= is supported"
        assert path in TAB_SOURCES, f"{route_id}: {path} does not read ?tab="
        source, const = TAB_SOURCES[path]
        assert tab in _tabs(source, const), f"{route_id}: {path} has no tab {tab!r}"


def test_legacy_dead_routes_are_gone():
    dead = {"/wallet", "/portfolio", "/account", "/family", "/broker"}
    live = {p.split("?")[0] for p, _ in guard.DEEP_LINKS.values()}
    assert not dead & live


def test_developer_profile_links_including_non_latin_names():
    assert guard.make_link("developer", "elite-gate-properties") == {
        "route_id": "developer",
        "path": "/developers/elite-gate-properties",
        "label": "Open the developer's profile",
    }
    assert guard.make_link("developer", "إعمار-العقارية")["path"] == "/developers/إعمار-العقارية"
    for bad in ("../admin", "a/b", "", None, "-x", "x y"):
        with pytest.raises(AppError):
            guard.make_link("developer", bad)
    # property slugs stay strictly Latin
    with pytest.raises(AppError):
        guard.make_link("property", "إعمار")


def test_hand_typed_links_resolve_against_the_allow_list():
    text, flags, links = guard.postprocess_output(
        "See [the developer](/developers/elite-gate-properties), your [tickets](/support/tickets), "
        "old [wallet](/wallet), and /settings?tab=security or /dashboard?tab=verification."
    )
    assert "unknown_route_removed" in flags and "(/wallet)" not in text
    assert [(link["route_id"], link["path"]) for link in links] == [
        ("developer", "/developers/elite-gate-properties"),
        ("tickets", "/support/tickets"),
        ("security", "/settings?tab=security"),
        ("verification_center", "/dashboard?tab=verification"),
    ]
