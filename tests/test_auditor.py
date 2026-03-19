"""
Testes para auditor.py — lógica de datas e orquestração da auditoria.
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from auditor import (
    get_audit_date,
    get_weekly_range,
    get_monthly_range,
    audit_users,
)


# ── get_audit_date ────────────────────────────────────────────────────────────

class TestGetAuditDate:
    def test_segunda_retorna_sexta(self):
        # Segunda 17/03/2025 → Sexta 14/03/2025
        monday = date(2025, 3, 17)
        start, end = get_audit_date(monday)
        assert start.date() == date(2025, 3, 14)
        assert end.date() == date(2025, 3, 14)

    def test_terca_retorna_segunda(self):
        tuesday = date(2025, 3, 18)
        start, end = get_audit_date(tuesday)
        assert start.date() == date(2025, 3, 17)

    def test_quarta_retorna_terca(self):
        wednesday = date(2025, 3, 19)
        start, end = get_audit_date(wednesday)
        assert start.date() == date(2025, 3, 18)

    def test_sabado_retorna_sexta(self):
        saturday = date(2025, 3, 15)
        start, end = get_audit_date(saturday)
        assert start.date() == date(2025, 3, 14)

    def test_domingo_retorna_sabado(self):
        sunday = date(2025, 3, 16)
        start, end = get_audit_date(sunday)
        assert start.date() == date(2025, 3, 15)

    def test_range_e_um_dia_completo(self):
        ref = date(2025, 3, 18)
        start, end = get_audit_date(ref)
        assert start.hour == 0 and start.minute == 0 and start.second == 0
        assert end.hour == 23 and end.minute == 59 and end.second == 59

    def test_timezone_utc(self):
        ref = date(2025, 3, 18)
        start, end = get_audit_date(ref)
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_reference_none_usa_hoje(self):
        today = datetime.now(tz=timezone.utc).date()
        start, _ = get_audit_date(None)
        # Apenas valida que não lança exceção e retorna datas consistentes
        assert start.date() < today


# ── get_weekly_range ──────────────────────────────────────────────────────────

class TestGetWeeklyRange:
    def test_retorna_5_dias_uteis(self):
        # Referência: quarta 19/03/2025
        # cursor: ter 18 (1), seg 17 (2), sex 14 (3), qui 13 (4), qua 12 (5)
        ref = date(2025, 3, 19)  # Quarta
        start, end = get_weekly_range(ref)
        assert start.date() == date(2025, 3, 12)  # qua mais antiga
        assert end.date() == date(2025, 3, 18)    # ter mais recente

    def test_nao_inclui_fins_de_semana(self):
        ref = date(2025, 3, 17)  # Segunda
        start, end = get_weekly_range(ref)
        # deve cobrir dom 16 → pula → sex 14, qui 13, qua 12, ter 11, seg 10
        assert start.date().weekday() < 5  # seg–sex
        assert end.date().weekday() < 5

    def test_start_antes_de_end(self):
        ref = date(2025, 3, 21)  # Sexta
        start, end = get_weekly_range(ref)
        assert start < end

    def test_timezone_utc(self):
        ref = date(2025, 3, 21)
        start, end = get_weekly_range(ref)
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_range_diario_completo(self):
        ref = date(2025, 3, 21)
        start, end = get_weekly_range(ref)
        assert start.hour == 0 and start.minute == 0
        assert end.hour == 23 and end.minute == 59 and end.second == 59


# ── get_monthly_range ─────────────────────────────────────────────────────────

class TestGetMonthlyRange:
    def test_retorna_30_dias_uteis(self):
        ref = date(2025, 3, 19)
        start, end = get_monthly_range(ref)
        # Contar dias úteis entre start e end
        business_days = 0
        cursor = start.date()
        while cursor <= end.date():
            if cursor.weekday() < 5:
                business_days += 1
            cursor += __import__('datetime').timedelta(days=1)
        assert business_days == 30

    def test_start_antes_de_end(self):
        ref = date(2025, 3, 19)
        start, end = get_monthly_range(ref)
        assert start < end

    def test_sem_fins_de_semana_nas_extremidades(self):
        ref = date(2025, 3, 19)
        start, end = get_monthly_range(ref)
        assert start.date().weekday() < 5  # início é dia útil
        assert end.date().weekday() < 5    # fim é dia útil

    def test_timezone_utc(self):
        ref = date(2025, 3, 19)
        start, end = get_monthly_range(ref)
        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_cobre_mais_que_weekly(self):
        ref = date(2025, 3, 19)
        w_start, _ = get_weekly_range(ref)
        m_start, _ = get_monthly_range(ref)
        assert m_start < w_start  # mensal começa muito antes


# ── audit_users ───────────────────────────────────────────────────────────────

def _build_mock_client(
    commits=None,
    prs=None,
    reviews=0,
    comments=0,
    files=0,
    adds=0,
    dels=0,
):
    """Cria um mock de GitHubClient com valores padrão."""
    commits = commits if commits is not None else []
    prs = prs if prs is not None else []

    mock = MagicMock()
    mock.get_commits_for_user.return_value = commits
    mock.get_prs_for_user.return_value = prs
    mock.get_reviews_for_user.return_value = reviews
    mock.get_pr_comments_for_user.return_value = comments
    mock.get_commit_stats.return_value = (files, adds, dels)
    return mock


@patch("auditor.GitHubClient")
class TestAuditUsers:
    def test_usuario_normal(self, MockClient):
        mock = _build_mock_client(
            commits=[{}] * 3,   # 3 commits
            prs=[{}] * 1,       # 1 PR
            reviews=2,
            comments=1,
            files=5,
        )
        MockClient.return_value = mock

        results, _, _ = audit_users(
            users=["dev1"], token="tok", orgs=None, count_files=False
        )

        assert len(results) == 1
        r = results[0]
        assert r["usuario"] == "dev1"
        assert r["commits"] == 3
        assert r["prs"] == 1
        assert r["reviews"] == 2
        assert r["comments"] == 1
        assert r["erro"] is None
        assert r["sci"] > 0

    def test_mvp_e_o_de_maior_sci(self, MockClient):
        call_count = 0

        def side_effect(token):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _build_mock_client(commits=[{}] * 10, prs=[{}] * 2, reviews=5, comments=3)
            return _build_mock_client(commits=[{}] * 1)

        MockClient.side_effect = side_effect

        results, _, _ = audit_users(
            users=["top_dev", "low_dev"], token="tok", orgs=None, count_files=False
        )

        mvps = [r for r in results if r.get("is_mvp")]
        assert len(mvps) == 1
        assert mvps[0]["usuario"] == "top_dev"

    def test_sem_mvp_quando_sci_zero(self, MockClient):
        MockClient.return_value = _build_mock_client()  # tudo zero

        results, _, _ = audit_users(users=["idle"], token="tok", orgs=None, count_files=False)

        assert not results[0].get("is_mvp")

    def test_erro_nao_afeta_outros_usuarios(self, MockClient):
        good_mock = _build_mock_client(commits=[{}] * 3, prs=[{}])
        bad_mock = MagicMock()
        bad_mock.get_commits_for_user.side_effect = Exception("API error")
        bad_mock.get_prs_for_user.return_value = []
        bad_mock.get_reviews_for_user.return_value = 0
        bad_mock.get_pr_comments_for_user.return_value = 0
        bad_mock.get_commit_stats.return_value = (0, 0, 0)

        MockClient.side_effect = [good_mock, bad_mock]

        results, _, _ = audit_users(
            users=["ok_user", "fail_user"], token="tok", orgs=None, count_files=False
        )

        ok  = next(r for r in results if r["usuario"] == "ok_user")
        bad = next(r for r in results if r["usuario"] == "fail_user")
        assert ok["erro"] is None
        assert bad["erro"] is not None

    def test_ordem_original_preservada(self, MockClient):
        MockClient.return_value = _build_mock_client()

        users = ["user_c", "user_a", "user_b"]
        results, _, _ = audit_users(users=users, token="tok", orgs=None, count_files=False)

        assert [r["usuario"] for r in results] == users

    def test_modo_weekly_usa_get_weekly_range(self, MockClient):
        MockClient.return_value = _build_mock_client()

        with patch("auditor.get_weekly_range") as mock_weekly, \
             patch("auditor.get_audit_date") as mock_daily:
            mock_weekly.return_value = (
                datetime(2025, 3, 10, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
            )
            audit_users(users=["u"], token="tok", orgs=None, weekly=True)

        mock_weekly.assert_called_once()
        mock_daily.assert_not_called()

    def test_modo_monthly_usa_get_monthly_range(self, MockClient):
        MockClient.return_value = _build_mock_client()

        with patch("auditor.get_monthly_range") as mock_monthly, \
             patch("auditor.get_audit_date") as mock_daily:
            mock_monthly.return_value = (
                datetime(2025, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
                datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc),
            )
            audit_users(users=["u"], token="tok", orgs=None, monthly=True)

        mock_monthly.assert_called_once()
        mock_daily.assert_not_called()

    def test_count_files_false_nao_chama_get_commit_stats(self, MockClient):
        mock = _build_mock_client(commits=[{}, {}])
        MockClient.return_value = mock

        audit_users(users=["u"], token="tok", orgs=None, count_files=False)

        mock.get_commit_stats.assert_not_called()

    def test_count_files_true_chama_get_commit_stats(self, MockClient):
        mock = _build_mock_client(commits=[{}, {}])
        MockClient.return_value = mock

        audit_users(users=["u"], token="tok", orgs=None, count_files=True)

        mock.get_commit_stats.assert_called_once()

    def test_date_range_explicito_ignora_weekly_monthly(self, MockClient):
        MockClient.return_value = _build_mock_client()

        explicit_start = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        explicit_end   = datetime(2025, 1, 31, 23, 59, 59, tzinfo=timezone.utc)

        with patch("auditor.get_weekly_range") as mock_weekly, \
             patch("auditor.get_monthly_range") as mock_monthly, \
             patch("auditor.get_audit_date") as mock_daily:
            results, start, end = audit_users(
                users=["u"], token="tok", orgs=None,
                date_range=(explicit_start, explicit_end),
                weekly=True,   # ignorado quando date_range é fornecido
                monthly=True,  # ignorado quando date_range é fornecido
            )

        mock_weekly.assert_not_called()
        mock_monthly.assert_not_called()
        mock_daily.assert_not_called()
        assert start == explicit_start
        assert end == explicit_end

    def test_cache_hit_retorna_from_cache_true(self, MockClient):
        cached_data = {
            "usuario": "alice",
            "commits": 5, "prs": 2, "reviews": 3, "comments": 1,
            "arquivos_alterados": 10, "additions": 100, "deletions": 50,
            "sci": 50.0, "sci_level": "green",
            "profile_emoji": "🔨", "profile_tag": "Construtor",
            "insights": [], "is_mvp": False, "from_cache": False,
            "erro": None, "data": "14/03/2025",
            "data_range": "14/03/2025 → 14/03/2025",
        }
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data

        results, _, _ = audit_users(
            users=["alice"], token="tok", orgs=None,
            count_files=False, cache=mock_cache, force=False,
        )

        assert results[0]["from_cache"] is True
        # GitHubClient nunca foi instanciado (cache hit)
        MockClient.assert_not_called()

    def test_force_ignora_cache_e_chama_api(self, MockClient):
        mock = _build_mock_client(commits=[{}])
        MockClient.return_value = mock

        mock_cache = MagicMock()
        mock_cache.get.return_value = {"sci": 999.0}  # deve ser ignorado

        audit_users(
            users=["alice"], token="tok", orgs=None,
            count_files=False, cache=mock_cache, force=True,
        )

        # cache.get nunca deve ser consultado quando force=True
        mock_cache.get.assert_not_called()
        mock.get_commits_for_user.assert_called()

    def test_progress_callback_chamado_para_cada_usuario(self, MockClient):
        MockClient.return_value = _build_mock_client()

        called = []
        audit_users(
            users=["dev1", "dev2", "dev3"], token="tok", orgs=None,
            count_files=False, progress_callback=lambda u: called.append(u),
        )

        assert sorted(called) == ["dev1", "dev2", "dev3"]

    def test_cache_put_chamado_apos_sucesso(self, MockClient):
        MockClient.return_value = _build_mock_client(commits=[{}])
        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # cache miss

        audit_users(
            users=["alice"], token="tok", orgs=None,
            count_files=False, cache=mock_cache, force=False,
        )

        mock_cache.put.assert_called_once()
