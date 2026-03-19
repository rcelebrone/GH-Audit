"""
Testes para sci.py — cálculo do SCI, cores, perfis e insights.
Módulo puro sem I/O, 100% testável sem mocks.
"""

import pytest
from sci import calculate_sci, get_profile, sci_color, get_insights


# ── calculate_sci ─────────────────────────────────────────────────────────────

class TestCalculateSci:
    def test_all_zero(self):
        assert calculate_sci(0, 0, 0, 0, 0) == 0.0

    def test_only_prs(self):
        # 1 PR × 10 pts
        assert calculate_sci(0, 1, 0, 0, 0) == 10.0

    def test_only_commits(self):
        # 5 commits × 2 pts
        assert calculate_sci(5, 0, 0, 0, 0) == 10.0

    def test_only_reviews(self):
        # 3 reviews × 8 pts
        assert calculate_sci(0, 0, 3, 0, 0) == 24.0

    def test_only_comments(self):
        # 4 comentários × 3 pts
        assert calculate_sci(0, 0, 0, 4, 0) == 12.0

    def test_files_below_cap(self):
        # 10 arquivos × 0.5 = 5.0 (abaixo do cap de 15)
        assert calculate_sci(0, 0, 0, 0, 10) == 5.0

    def test_files_at_cap(self):
        # 30 arquivos × 0.5 = 15.0 (exato no cap)
        assert calculate_sci(0, 0, 0, 0, 30) == 15.0

    def test_files_above_cap(self):
        # 100 arquivos → limitado a 15.0
        assert calculate_sci(0, 0, 0, 0, 100) == 15.0

    def test_combined(self):
        # PR=1(10) + commits=3(6) + reviews=2(16) + comments=1(3) + files=10(5) = 40.0
        assert calculate_sci(3, 1, 2, 1, 10) == 40.0

    def test_returns_float(self):
        assert isinstance(calculate_sci(1, 1, 1, 1, 1), float)

    def test_file_cap_boundary_29(self):
        # 29 arquivos × 0.5 = 14.5 (abaixo do cap)
        assert calculate_sci(0, 0, 0, 0, 29) == 14.5

    def test_high_activity(self):
        # Cenário de alta entrega: 5 PRs + 20 commits + 10 reviews + 15 comments + 50 files
        expected = (5 * 10) + (20 * 2) + (10 * 8) + (15 * 3) + 15.0
        assert calculate_sci(20, 5, 10, 15, 50) == expected


# ── sci_color ─────────────────────────────────────────────────────────────────

class TestSciColor:
    def test_green_at_25(self):
        assert sci_color(25.0) == "green"

    def test_green_above_25(self):
        assert sci_color(100.0) == "green"

    def test_yellow_at_24_9(self):
        assert sci_color(24.9) == "yellow"

    def test_yellow_at_10(self):
        # Fronteira inferior do amarelo
        assert sci_color(10.0) == "yellow"

    def test_red_at_9_9(self):
        assert sci_color(9.9) == "red"

    def test_red_at_zero(self):
        assert sci_color(0.0) == "red"

    def test_green_exactly_25(self):
        # 25 é verde (>= 25)
        assert sci_color(25.0) == "green"

    def test_yellow_exactly_10(self):
        # 10 é amarelo (>= 10 e < 25)
        assert sci_color(10.0) == "yellow"


# ── get_profile ───────────────────────────────────────────────────────────────

class TestGetProfile:
    def test_no_activity(self):
        emoji, tag = get_profile(0, 0, 0, 0)
        assert emoji == "😶"
        assert tag == "Bloqueado"

    def test_refatorador(self):
        # files > 20 e prs == 1
        emoji, tag = get_profile(commits=0, prs=1, reviews=0, files=21)
        assert emoji == "🔧"
        assert tag == "Refatorador"

    def test_refatorador_exact_boundary(self):
        # files == 20 NÃO é refatorador (precisa ser > 20)
        emoji, _ = get_profile(commits=0, prs=1, reviews=0, files=20)
        assert emoji != "🔧"

    def test_revisor(self):
        # reviews > 3 e commits < 2
        emoji, tag = get_profile(commits=1, prs=0, reviews=4, files=0)
        assert emoji == "🔎"
        assert tag == "O Revisor"

    def test_revisor_boundary_commits_2(self):
        # commits == 2 NÃO é revisor (precisa ser < 2)
        emoji, _ = get_profile(commits=2, prs=0, reviews=4, files=0)
        assert emoji != "🔎"

    def test_construtor_por_commits(self):
        # commits > 5
        emoji, tag = get_profile(commits=6, prs=0, reviews=0, files=0)
        assert emoji == "🔨"
        assert tag == "Construtor"

    def test_construtor_por_prs(self):
        # prs >= 2
        emoji, tag = get_profile(commits=1, prs=2, reviews=0, files=0)
        assert emoji == "🔨"
        assert tag == "Construtor"

    def test_colaborativo(self):
        # prs >= 1 e reviews >= 2
        emoji, tag = get_profile(commits=3, prs=1, reviews=2, files=5)
        assert emoji == "🤝"
        assert tag == "Colaborativo"

    def test_ativo(self):
        # Qualquer atividade que não encaixe nos perfis anteriores
        emoji, tag = get_profile(commits=1, prs=0, reviews=0, files=5)
        assert emoji == "⚡"
        assert tag == "Ativo"

    def test_prioridade_refatorador_sobre_revisor(self):
        # files=25, prs=1 → Refatorador tem prioridade sobre O Revisor
        emoji, _ = get_profile(commits=0, prs=1, reviews=5, files=25)
        assert emoji == "🔧"

    def test_prioridade_revisor_sobre_construtor(self):
        # reviews=4, commits=1 → O Revisor tem prioridade sobre Construtor
        # (commits=1 < 2, prs=0 < 2, então não é Construtor)
        emoji, _ = get_profile(commits=1, prs=0, reviews=4, files=0)
        assert emoji == "🔎"

    def test_construtor_prioridade_sobre_colaborativo(self):
        # prs=2, reviews=3 → Construtor (prs >= 2) antes de Colaborativo
        emoji, _ = get_profile(commits=0, prs=2, reviews=3, files=0)
        assert emoji == "🔨"


# ── get_insights ──────────────────────────────────────────────────────────────

class TestGetInsights:
    def test_sem_insights(self):
        assert get_insights(20.0, 1, 1, 10) == []

    def test_alta_entrega(self):
        insights = get_insights(31.0, 0, 0, 0)
        assert "🔥 Alta Entrega" in insights

    def test_alta_entrega_boundary_30(self):
        # sci == 30 NÃO gera Alta Entrega (precisa ser > 30)
        insights = get_insights(30.0, 0, 0, 0)
        assert "🔥 Alta Entrega" not in insights

    def test_gargalo_review(self):
        # prs > 0 e reviews == 0
        insights = get_insights(10.0, 1, 0, 10)
        assert "🚨 Gargalo de Review" in insights

    def test_sem_gargalo_sem_prs(self):
        insights = get_insights(10.0, 0, 0, 10)
        assert "🚨 Gargalo de Review" not in insights

    def test_sem_gargalo_com_reviews(self):
        insights = get_insights(10.0, 1, 1, 10)
        assert "🚨 Gargalo de Review" not in insights

    def test_pr_gigante(self):
        insights = get_insights(0.0, 0, 0, 51)
        assert "📦 PR Gigante (risco)" in insights

    def test_pr_gigante_boundary_50(self):
        # files == 50 NÃO gera PR Gigante (precisa ser > 50)
        insights = get_insights(0.0, 0, 0, 50)
        assert "📦 PR Gigante (risco)" not in insights

    def test_todos_os_insights(self):
        insights = get_insights(35.0, 1, 0, 60)
        assert "🔥 Alta Entrega" in insights
        assert "🚨 Gargalo de Review" in insights
        assert "📦 PR Gigante (risco)" in insights
        assert len(insights) == 3
