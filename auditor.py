"""
Módulo de auditoria: orquestra as chamadas ao GitHub e monta o relatório.
"""

from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Tuple

from github_client import GitHubClient
from sci import calculate_sci, get_profile, sci_color, get_insights


def _day_range(target: date) -> Tuple[datetime, datetime]:
    """Retorna (00:00:00 UTC, 23:59:59 UTC) para uma data."""
    return (
        datetime(target.year, target.month, target.day, 0, 0, 0, tzinfo=timezone.utc),
        datetime(target.year, target.month, target.day, 23, 59, 59, tzinfo=timezone.utc),
    )


def get_audit_date(
    reference_date: Optional[date] = None,
) -> Tuple[datetime, datetime]:
    """
    Retorna o intervalo do dia útil anterior a `reference_date`.
    Segunda → sexta (3 dias antes). Demais dias → imediatamente anterior.
    """
    if reference_date is None:
        reference_date = datetime.now(tz=timezone.utc).date()

    if reference_date.weekday() == 0:       # Segunda-feira
        target = reference_date - timedelta(days=3)
    else:
        target = reference_date - timedelta(days=1)

    return _day_range(target)


def get_weekly_range(
    reference_date: Optional[date] = None,
) -> Tuple[datetime, datetime]:
    """
    Retorna o intervalo dos últimos 5 dias úteis (seg–sex) antes de `reference_date`.
    Útil para análise da semana completa sem distorções de um único dia.
    """
    if reference_date is None:
        reference_date = datetime.now(tz=timezone.utc).date()

    business_days: List[date] = []
    cursor = reference_date - timedelta(days=1)
    while len(business_days) < 5:
        if cursor.weekday() < 5:            # seg(0) a sex(4)
            business_days.append(cursor)
        cursor -= timedelta(days=1)

    week_start = business_days[-1]          # dia mais antigo
    week_end   = business_days[0]           # dia mais recente

    return _day_range(week_start)[0], _day_range(week_end)[1]


def audit_users(
    users: List[str],
    token: str,
    org: Optional[str],
    reference_date: Optional[date] = None,
    count_files: bool = True,
    weekly: bool = False,
) -> Tuple[List[Dict], datetime, datetime]:
    """
    Para cada usuário, coleta métricas de atividade GitHub e calcula:
      - Commits, PRs, Reviews, Comentários de Review
      - Arquivos alterados, Additions, Deletions
      - SCI (Score de Colaboração e Impacto)
      - Perfil de comportamento (emoji + label)
      - Insights / alertas individuais

    Retorna: (lista_de_resultados, date_start, date_end)
    """
    client = GitHubClient(token)

    # Mais páginas na Events API quando o período é semanal
    events_max_pages = 20 if weekly else 10

    if weekly:
        date_start, date_end = get_weekly_range(reference_date)
    else:
        date_start, date_end = get_audit_date(reference_date)

    results: List[Dict] = []

    for username in users:
        row: Dict = {
            "usuario":            username,
            "commits":            0,
            "prs":                0,
            "reviews":            0,
            "comments":           0,
            "arquivos_alterados": 0,
            "additions":          0,
            "deletions":          0,
            "sci":                0.0,
            "sci_level":          "red",
            "profile_emoji":      "❓",
            "profile_tag":        "—",
            "insights":           [],
            "data":               date_start.strftime("%d/%m/%Y"),
            "data_range": (
                f"{date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}"
            ),
            "is_mvp":             False,
            "erro":               None,
        }

        try:
            # ── Commits ──────────────────────────────────────────────────────
            commits = client.get_commits_for_user(
                username, date_start, date_end, org
            )
            row["commits"] = len(commits)

            # ── Arquivos / Additions / Deletions ─────────────────────────────
            if count_files and commits:
                files, adds, dels = client.get_commit_stats(commits)
                row["arquivos_alterados"] = files
                row["additions"]          = adds
                row["deletions"]          = dels

            # ── Pull Requests ─────────────────────────────────────────────────
            prs = client.get_prs_for_user(username, date_start, date_end, org)
            row["prs"] = len(prs)

            # ── Reviews ───────────────────────────────────────────────────────
            row["reviews"] = client.get_reviews_count(
                username, date_start, date_end, org
            )

            # ── Comentários de Review ─────────────────────────────────────────
            row["comments"] = client.get_review_comments_count(
                username, date_start, date_end, org,
                max_pages=events_max_pages,
            )

            # ── SCI ───────────────────────────────────────────────────────────
            row["sci"] = calculate_sci(
                row["commits"], row["prs"], row["reviews"],
                row["comments"], row["arquivos_alterados"],
            )
            row["sci_level"] = sci_color(row["sci"])

            # ── Perfil ────────────────────────────────────────────────────────
            emoji, tag = get_profile(
                row["commits"], row["prs"], row["reviews"], row["arquivos_alterados"]
            )
            row["profile_emoji"] = emoji
            row["profile_tag"]   = tag

            # ── Insights ──────────────────────────────────────────────────────
            row["insights"] = get_insights(
                row["sci"], row["prs"], row["reviews"], row["arquivos_alterados"]
            )

        except Exception as exc:
            row["erro"] = str(exc)

        results.append(row)

    # ── MVP: dev com maior SCI (ignorando erros) ──────────────────────────────
    valid = [r for r in results if not r.get("erro")]
    if valid:
        mvp = max(valid, key=lambda r: r["sci"])
        if mvp["sci"] > 0:
            mvp["is_mvp"] = True

    return results, date_start, date_end
