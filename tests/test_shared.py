"""
Tests for the shared `discover()` logic (pools/_shared.py) and each pool's
link-matching predicate — the HTML-scraping half of a parser, which the
fixture-based test_<pool>.py files don't exercise (those only cover parse()).
"""
from pools._shared import find_latest_document_link
from pools.delfin import _matches as delfin_matches
from pools.foka import _matches as foka_matches
from pools.inflancka import _matches as inflancka_matches
from pools.potocka import _matches as potocka_matches


def _link(href: str, text: str) -> str:
    return f'<a href="{href}">{text}</a>'


def _page(*links: str) -> str:
    return "<html><body>" + "\n".join(links) + "</body></html>"


class TestFindLatestDocumentLink:
    def test_picks_latest_dated_candidate(self):
        html = _page(
            _link("/a.pdf", "Grafik torów 01.09.2026"),
            _link("/b.pdf", "Grafik torów 15.09.2026"),
            _link("/c.pdf", "Grafik torów 08.09.2026"),
        )
        result = find_latest_document_link(html, lambda t: "grafik" in t)
        assert result.endswith("/b.pdf")

    def test_ignores_non_matching_links(self):
        html = _page(
            _link("/regulamin.pdf", "Regulamin pływalni"),
            _link("/grafik.pdf", "Grafik torów 01.09.2026"),
        )
        result = find_latest_document_link(html, lambda t: "grafik" in t)
        assert result.endswith("/grafik.pdf")

    def test_ignores_non_document_links(self):
        html = _page(
            _link("/grafik", "Grafik torów 01.09.2026"),  # no matching extension
            _link("/grafik.pdf", "Grafik torów 01.09.2026"),
        )
        result = find_latest_document_link(html, lambda t: "grafik" in t)
        assert result.endswith("/grafik.pdf")

    def test_falls_back_to_first_match_without_date(self):
        html = _page(
            _link("/grafik.pdf", "Aktualny grafik torów"),
        )
        result = find_latest_document_link(html, lambda t: "grafik" in t)
        assert result.endswith("/grafik.pdf")

    def test_returns_none_when_nothing_matches(self):
        html = _page(_link("/regulamin.pdf", "Regulamin pływalni"))
        result = find_latest_document_link(html, lambda t: "grafik" in t)
        assert result is None

    def test_returns_none_for_empty_page(self):
        assert find_latest_document_link("<html><body></body></html>", lambda t: True) is None

    def test_resolves_relative_urls(self):
        html = _page(_link("/documents/grafik.pdf", "Grafik torów"))
        result = find_latest_document_link(html, lambda t: "grafik" in t, base_url="https://sport.um.warszawa.pl")
        assert result == "https://sport.um.warszawa.pl/documents/grafik.pdf"

    def test_respects_custom_extensions(self):
        html = _page(
            _link("/grafik.xlsx", "Grafik torów"),
            _link("/regulamin.pdf", "Grafik torów"),  # matches text but wrong extension
        )
        result = find_latest_document_link(html, lambda t: "grafik" in t, extensions=(".xlsx",))
        assert result.endswith("/grafik.xlsx")


class TestDelfinMatches:
    def test_matches_grafik_torow(self):
        assert delfin_matches("grafik wolnych torów 15.09.2026")

    def test_matches_wolnych_torow(self):
        assert delfin_matches("liczba wolnych torów")

    def test_rejects_brodzik(self):
        assert not delfin_matches("grafik zajęć na brodziku i torze")

    def test_rejects_unrelated_pdf(self):
        assert not delfin_matches("regulamin pływalni")


class TestFokaMatches:
    def test_matches_rezerwacja(self):
        assert foka_matches("rezerwacja torów wrzesień")

    def test_matches_wykaz(self):
        assert foka_matches("wykaz wolnych torów")

    def test_rejects_unrelated_pdf(self):
        assert not foka_matches("regulamin pływalni")


class TestInflanckaMatches:
    def test_matches_plywalni(self):
        assert inflancka_matches("harmonogram pływalni wrzesień")

    def test_matches_harmonogram_tor(self):
        assert inflancka_matches("harmonogram torów")

    def test_rejects_unrelated_pdf(self):
        assert not inflancka_matches("regulamin zjeżdżalni")


class TestPotockaMatches:
    def test_matches_grafik_plywalni(self):
        assert potocka_matches("grafik pływalni potocka")

    def test_matches_grafik_tor(self):
        assert potocka_matches("grafik torów 15.09.2026")

    def test_rejects_grafik_without_pool_or_lane(self):
        assert not potocka_matches("grafik zajęć fitness")

    def test_rejects_unrelated_pdf(self):
        assert not potocka_matches("badania wody wrzesień")
