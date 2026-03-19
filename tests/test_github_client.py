"""
Testes para github_client.py — cliente da API GitHub.
Usa mocks de requests.Session para evitar chamadas de rede reais.
"""

import time
import warnings
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from github_client import GitHubClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """GitHubClient com sessão mockada."""
    with patch("github_client.requests.Session") as mock_session_class:
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        c = GitHubClient("test_token")
        c._session_mock = mock_session   # atalho para acesso nos testes
        yield c


def _make_response(status=200, json_data=None, headers=None):
    """Cria uma resposta HTTP mockada."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data or {}
    resp.headers = headers or {}
    if status >= 400:
        import requests
        resp.raise_for_status.side_effect = requests.HTTPError(
            response=resp, request=MagicMock()
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# ── _get (retry / rate limit) ─────────────────────────────────────────────────

class TestGet:
    def test_200_retorna_json(self, client):
        client._session_mock.get.return_value = _make_response(200, {"key": "val"})
        result = client._get("https://api.github.com/test")
        assert result == {"key": "val"}

    def test_429_faz_retry_e_retorna_na_segunda_tentativa(self, client):
        resp_429 = _make_response(429, headers={"Retry-After": "0"})
        resp_200 = _make_response(200, {"ok": True})
        client._session_mock.get.side_effect = [resp_429, resp_200]

        with patch("github_client.time.sleep") as mock_sleep:
            result = client._get("https://example.com")

        assert result == {"ok": True}
        mock_sleep.assert_called_once_with(0)

    def test_429_retry_after_header_e_usado(self, client):
        resp_429 = _make_response(429, headers={"Retry-After": "5"})
        resp_200 = _make_response(200, {})
        client._session_mock.get.side_effect = [resp_429, resp_200]

        with patch("github_client.time.sleep") as mock_sleep:
            client._get("https://example.com")

        mock_sleep.assert_called_once_with(5)

    def test_403_rate_limit_espera_e_reativa(self, client):
        future_reset = int(time.time()) + 2
        resp_403 = _make_response(
            403,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(future_reset),
            }
        )
        resp_200 = _make_response(200, {"data": 1})
        client._session_mock.get.side_effect = [resp_403, resp_200]

        with patch("github_client.time.sleep") as mock_sleep:
            result = client._get("https://example.com")

        assert result == {"data": 1}
        assert mock_sleep.call_count == 1
        wait_time = mock_sleep.call_args[0][0]
        assert wait_time >= 1  # pelo menos 1 segundo de espera

    def test_403_sem_rate_limit_levanta_imediatamente(self, client):
        resp_403 = _make_response(403, headers={})
        client._session_mock.get.return_value = resp_403

        import requests
        with pytest.raises(requests.HTTPError):
            client._get("https://example.com")

        # Deve levantar sem tentar fazer retry (apenas 1 chamada)
        assert client._session_mock.get.call_count == 1

    def test_tres_429_consecutivos_levanta_http_error(self, client):
        resp_429 = _make_response(429, headers={"Retry-After": "0"})
        client._session_mock.get.return_value = resp_429

        import requests
        with patch("github_client.time.sleep"):
            with pytest.raises(requests.HTTPError):
                client._get("https://example.com")

        assert client._session_mock.get.call_count == 3


# ── get_commits_for_user ──────────────────────────────────────────────────────

class TestGetCommitsForUser:
    def _setup_single_page(self, client, items, total_count=None):
        if total_count is None:
            total_count = len(items)
        client._session_mock.get.return_value = _make_response(
            200, {"items": items, "total_count": total_count}
        )

    def test_resultado_vazio(self, client):
        self._setup_single_page(client, [])
        result = client.get_commits_for_user(
            "user",
            datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
        )
        assert result == []

    def test_pagina_unica(self, client):
        items = [{"sha": f"abc{i}"} for i in range(5)]
        self._setup_single_page(client, items)
        result = client.get_commits_for_user(
            "user",
            datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
        )
        assert len(result) == 5

    def test_paginacao_multiplas_paginas(self, client):
        page1 = [{"sha": f"a{i}"} for i in range(100)]
        page2 = [{"sha": f"b{i}"} for i in range(50)]
        client._session_mock.get.side_effect = [
            _make_response(200, {"items": page1, "total_count": 150}),
            _make_response(200, {"items": page2, "total_count": 150}),
        ]
        result = client.get_commits_for_user(
            "user",
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 14, tzinfo=timezone.utc),
        )
        assert len(result) == 150
        assert client._session_mock.get.call_count == 2

    def test_limite_1000_emite_warning(self, client):
        # Simula 11 páginas com 100 itens cada (total_count=1200 > 1000)
        page = [{"sha": f"x{i}"} for i in range(100)]
        client._session_mock.get.return_value = _make_response(
            200, {"items": page, "total_count": 1200}
        )
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = client.get_commits_for_user(
                "user",
                datetime(2025, 3, 1, tzinfo=timezone.utc),
                datetime(2025, 3, 31, tzinfo=timezone.utc),
            )
        assert len(result) == 1000
        assert any(issubclass(warning.category, RuntimeWarning) for warning in w)

    def test_query_inclui_org(self, client):
        client._session_mock.get.return_value = _make_response(200, {"items": [], "total_count": 0})
        client.get_commits_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc), orgs=["MyOrg"]
        )
        call_params = client._session_mock.get.call_args[1].get("params") or \
                      client._session_mock.get.call_args[0][1]
        assert "org:MyOrg" in call_params["q"]

    def test_query_sem_org(self, client):
        client._session_mock.get.return_value = _make_response(200, {"items": [], "total_count": 0})
        client.get_commits_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc), orgs=None
        )
        call_params = client._session_mock.get.call_args[1].get("params") or \
                      client._session_mock.get.call_args[0][1]
        assert "org:" not in call_params["q"]

    def test_multiplas_orgs_deduplica_por_sha(self, client):
        # OrgA retorna commits a0, a1; OrgB retorna a1 (duplicado) + b0
        org_a = [{"sha": "a0"}, {"sha": "a1"}]
        org_b = [{"sha": "a1"}, {"sha": "b0"}]
        client._session_mock.get.side_effect = [
            _make_response(200, {"items": org_a, "total_count": 2}),
            _make_response(200, {"items": org_b, "total_count": 2}),
        ]
        result = client.get_commits_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
            orgs=["OrgA", "OrgB"],
        )
        shas = {c["sha"] for c in result}
        assert shas == {"a0", "a1", "b0"}   # 3 únicos, não 4
        assert client._session_mock.get.call_count == 2  # 1 busca por org


# ── get_commit_stats ──────────────────────────────────────────────────────────

class TestGetCommitStats:
    def test_lista_vazia(self, client):
        files, adds, dels = client.get_commit_stats([])
        assert (files, adds, dels) == (0, 0, 0)

    def test_commit_unico(self, client):
        client._session_mock.get.return_value = _make_response(200, {
            "stats": {"additions": 10, "deletions": 5},
            "files": [{"filename": "a.py"}, {"filename": "b.py"}],
        })
        files, adds, dels = client.get_commit_stats([{"url": "https://api.github.com/repos/x/y/commits/abc"}])
        assert files == 2
        assert adds == 10
        assert dels == 5

    def test_deduplicacao_de_arquivos(self, client):
        # Dois commits alterando o mesmo arquivo → conta 1 único
        detail = {
            "stats": {"additions": 3, "deletions": 1},
            "files": [{"filename": "shared.py"}],
        }
        client._session_mock.get.return_value = _make_response(200, detail)
        commits = [{"url": "u1"}, {"url": "u2"}]
        files, adds, dels = client.get_commit_stats(commits)
        assert files == 1   # deduplica
        assert adds == 6    # soma dos dois
        assert dels == 2

    def test_commit_sem_url_e_ignorado(self, client):
        files, adds, dels = client.get_commit_stats([{"sha": "abc"}])  # sem 'url'
        assert (files, adds, dels) == (0, 0, 0)
        client._session_mock.get.assert_not_called()

    def test_erro_no_detalhe_e_ignorado(self, client):
        import requests
        client._session_mock.get.return_value = _make_response(404)
        files, adds, dels = client.get_commit_stats([{"url": "https://bad.url"}])
        assert (files, adds, dels) == (0, 0, 0)


# ── get_prs_for_user ──────────────────────────────────────────────────────────

class TestGetPrsForUser:
    def test_query_usa_is_pr(self, client):
        client._session_mock.get.return_value = _make_response(200, {"items": [], "total_count": 0})
        client.get_prs_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc)
        )
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "is:pr" in params["q"]
        assert "created:" in params["q"]

    def test_resultado_com_prs(self, client):
        items = [{"number": i, "id": i} for i in range(3)]
        client._session_mock.get.return_value = _make_response(200, {"items": items, "total_count": 3})
        result = client.get_prs_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc)
        )
        assert len(result) == 3

    def test_multiplas_orgs_deduplica_por_id(self, client):
        # OrgA e OrgB retornam o mesmo PR (id=99)
        pr_shared = {"id": 99, "number": 1}
        pr_unique = {"id": 100, "number": 2}
        client._session_mock.get.side_effect = [
            _make_response(200, {"items": [pr_shared], "total_count": 1}),
            _make_response(200, {"items": [pr_shared, pr_unique], "total_count": 2}),
        ]
        result = client.get_prs_for_user(
            "dev", datetime(2025, 3, 14, tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
            orgs=["OrgA", "OrgB"],
        )
        ids = {pr["id"] for pr in result}
        assert ids == {99, 100}   # 2 únicos, não 3


# ── get_reviews_for_user (Search API: reviewed-by:) ───────────────────────────

class TestGetReviewsForUser:
    @pytest.fixture
    def dates(self):
        return (
            datetime(2025, 3, 14, 0,  0,  0,  tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
        )

    def _setup(self, client, items, total_count=None):
        if total_count is None:
            total_count = len(items)
        client._session_mock.get.return_value = _make_response(
            200, {"items": items, "total_count": total_count}
        )

    def test_sem_orgs_retorna_contagem(self, client, dates):
        self._setup(client, [{"id": 1}, {"id": 2}, {"id": 3}])
        count = client.get_reviews_for_user("dev", *dates)
        assert count == 3

    def test_resultado_vazio(self, client, dates):
        self._setup(client, [])
        assert client.get_reviews_for_user("dev", *dates) == 0

    def test_query_contem_reviewed_by(self, client, dates):
        self._setup(client, [])
        client.get_reviews_for_user("dev", *dates)
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "reviewed-by:dev" in params["q"]
        assert "is:pr" in params["q"]

    def test_org_unica_inclui_org_na_query(self, client, dates):
        self._setup(client, [])
        client.get_reviews_for_user("dev", *dates, orgs=["MyOrg"])
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "org:MyOrg" in params["q"]

    def test_sem_orgs_nao_inclui_org_na_query(self, client, dates):
        self._setup(client, [])
        client.get_reviews_for_user("dev", *dates, orgs=None)
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "org:" not in params["q"]

    def test_multiplas_orgs_deduplica_por_id(self, client, dates):
        pr_shared = {"id": 99}
        pr_unique  = {"id": 100}
        client._session_mock.get.side_effect = [
            _make_response(200, {"items": [pr_shared], "total_count": 1}),
            _make_response(200, {"items": [pr_shared, pr_unique], "total_count": 2}),
        ]
        count = client.get_reviews_for_user("dev", *dates, orgs=["OrgA", "OrgB"])
        assert count == 2   # 99 e 100 — o duplicado 99 conta só uma vez

    def test_multiplas_orgs_faz_busca_por_org(self, client, dates):
        client._session_mock.get.return_value = _make_response(200, {"items": [], "total_count": 0})
        client.get_reviews_for_user("dev", *dates, orgs=["OrgA", "OrgB"])
        assert client._session_mock.get.call_count == 2  # 1 chamada por org


# ── get_pr_comments_for_user (Search API: commenter:) ─────────────────────────

class TestGetPrCommentsForUser:
    @pytest.fixture
    def dates(self):
        return (
            datetime(2025, 3, 14, 0,  0,  0,  tzinfo=timezone.utc),
            datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
        )

    def _setup(self, client, items, total_count=None):
        if total_count is None:
            total_count = len(items)
        client._session_mock.get.return_value = _make_response(
            200, {"items": items, "total_count": total_count}
        )

    def test_sem_orgs_retorna_contagem(self, client, dates):
        self._setup(client, [{"id": 1}, {"id": 2}])
        assert client.get_pr_comments_for_user("dev", *dates) == 2

    def test_resultado_vazio(self, client, dates):
        self._setup(client, [])
        assert client.get_pr_comments_for_user("dev", *dates) == 0

    def test_query_contem_commenter_e_exclui_author(self, client, dates):
        self._setup(client, [])
        client.get_pr_comments_for_user("dev", *dates)
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "commenter:dev" in params["q"]
        assert "-author:dev" in params["q"]
        assert "is:pr" in params["q"]

    def test_org_unica_inclui_org_na_query(self, client, dates):
        self._setup(client, [])
        client.get_pr_comments_for_user("dev", *dates, orgs=["MyOrg"])
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "org:MyOrg" in params["q"]

    def test_sem_orgs_nao_inclui_org_na_query(self, client, dates):
        self._setup(client, [])
        client.get_pr_comments_for_user("dev", *dates, orgs=None)
        params = client._session_mock.get.call_args[1].get("params") or \
                 client._session_mock.get.call_args[0][1]
        assert "org:" not in params["q"]

    def test_multiplas_orgs_deduplica_por_id(self, client, dates):
        pr_shared = {"id": 77}
        pr_unique  = {"id": 88}
        client._session_mock.get.side_effect = [
            _make_response(200, {"items": [pr_shared, pr_unique], "total_count": 2}),
            _make_response(200, {"items": [pr_shared], "total_count": 1}),
        ]
        count = client.get_pr_comments_for_user("dev", *dates, orgs=["OrgA", "OrgB"])
        assert count == 2   # 77 e 88 — 77 aparece em ambas as orgs

    def test_multiplas_orgs_faz_busca_por_org(self, client, dates):
        client._session_mock.get.return_value = _make_response(200, {"items": [], "total_count": 0})
        client.get_pr_comments_for_user("dev", *dates, orgs=["OrgA", "OrgB"])
        assert client._session_mock.get.call_count == 2
