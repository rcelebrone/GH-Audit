"""
Módulo de auditoria: orquestra as chamadas ao GitHub e monta o relatório.
"""

import concurrent.futures
import json
import logging
from datetime import datetime, timedelta, timezone, date
from typing import Callable, Dict, List, Optional, Tuple

from cache import AuditCache, _make_key
from github_client import GitHubClient
from sci import calculate_sci, get_profile, sci_color, get_insights

log = logging.getLogger(__name__)


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
    """
    if reference_date is None:
        reference_date = datetime.now(tz=timezone.utc).date()

    business_days: List[date] = []
    cursor = reference_date - timedelta(days=1)
    while len(business_days) < 5:
        if cursor.weekday() < 5:
            business_days.append(cursor)
        cursor -= timedelta(days=1)

    return _day_range(business_days[-1])[0], _day_range(business_days[0])[1]


def get_monthly_range(
    reference_date: Optional[date] = None,
) -> Tuple[datetime, datetime]:
    """
    Retorna o intervalo dos últimos 30 dias úteis antes de `reference_date`.
    Útil para análise mensal de produtividade sem distorções de feriados.
    """
    if reference_date is None:
        reference_date = datetime.now(tz=timezone.utc).date()

    business_days: List[date] = []
    cursor = reference_date - timedelta(days=1)
    while len(business_days) < 30:
        if cursor.weekday() < 5:
            business_days.append(cursor)
        cursor -= timedelta(days=1)

    return _day_range(business_days[-1])[0], _day_range(business_days[0])[1]


def _make_empty_row(
    username: str,
    date_start: datetime,
    date_end: datetime,
    error: str = "",
) -> Dict:
    """Cria um dict de resultado com todos os campos zerados."""
    return {
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
        "from_cache":         False,
        "erro":               error or None,
    }


def _audit_single_user(
    username: str,
    token: str,
    date_start: datetime,
    date_end: datetime,
    orgs: List[str],
    count_files: bool,
    cache: Optional[AuditCache] = None,
    force: bool = False,
) -> Dict:
    """Worker: coleta e calcula métricas para um único usuário."""

    # ── Cache: verificar resultado existente ──────────────────────────────────
    cache_key = _make_key(
        username,
        date_start.isoformat(),
        date_end.isoformat(),
        json.dumps(sorted(orgs)),
        count_files,
    )
    if cache and not force:
        cached = cache.get(cache_key)
        if cached:
            cached["from_cache"] = True
            log.info("▶ %s — resultado do cache (%s → %s)",
                     username,
                     date_start.strftime("%Y-%m-%d"),
                     date_end.strftime("%Y-%m-%d"))
            return cached

    log.info("▶ auditando %s | %s → %s | orgs=%s",
             username,
             date_start.strftime("%Y-%m-%d"),
             date_end.strftime("%Y-%m-%d"),
             orgs or "*")

    row = _make_empty_row(username, date_start, date_end)

    try:
        client = GitHubClient(token)

        # ── Commits ──────────────────────────────────────────────────────────
        commits = client.get_commits_for_user(username, date_start, date_end, orgs)
        row["commits"] = len(commits)
        log.info("  commits=%d", row["commits"])

        # ── Arquivos / Additions / Deletions ─────────────────────────────────
        if count_files and commits:
            files, adds, dels = client.get_commit_stats(commits)
            row["arquivos_alterados"] = files
            row["additions"]          = adds
            row["deletions"]          = dels
            log.info("  arquivos=%d  +%d/-%d", files, adds, dels)
        elif not count_files:
            log.debug("  contagem de arquivos desativada (--no-files)")

        # ── Pull Requests ─────────────────────────────────────────────────────
        prs = client.get_prs_for_user(username, date_start, date_end, orgs)
        row["prs"] = len(prs)
        log.info("  prs=%d", row["prs"])

        # ── Reviews (Search API: reviewed-by:) ───────────────────────────────
        reviews = client.get_reviews_for_user(username, date_start, date_end, orgs)
        row["reviews"] = reviews
        log.info("  reviews=%d", reviews)

        # ── Comentários em PRs alheios (Search API: commenter:) ───────────────
        comments = client.get_pr_comments_for_user(username, date_start, date_end, orgs)
        row["comments"] = comments
        log.info("  comments=%d", comments)

        # ── SCI ───────────────────────────────────────────────────────────────
        row["sci"] = calculate_sci(
            row["commits"], row["prs"], row["reviews"],
            row["comments"], row["arquivos_alterados"],
        )
        row["sci_level"] = sci_color(row["sci"])
        log.info("  SCI=%.1f (%s)", row["sci"], row["sci_level"])

        # ── Perfil ────────────────────────────────────────────────────────────
        emoji, tag = get_profile(
            row["commits"], row["prs"], row["reviews"], row["arquivos_alterados"]
        )
        row["profile_emoji"] = emoji
        row["profile_tag"]   = tag

        # ── Insights ──────────────────────────────────────────────────────────
        row["insights"] = get_insights(
            row["sci"], row["prs"], row["reviews"], row["arquivos_alterados"]
        )

        log.info("✓ %s concluído — SCI=%.1f  perfil=%s  insights=%s",
                 username, row["sci"], tag, row["insights"] or "—")

        # ── Persistir no cache (apenas resultados válidos) ────────────────────
        if cache:
            cache.put(cache_key, row)

    except Exception as exc:
        log.error("✗ %s falhou: %s", username, exc, exc_info=True)
        row["erro"] = str(exc)

    return row


def audit_users(
    users: List[str],
    token: str,
    orgs: Optional[List[str]] = None,
    count_files: bool = True,
    weekly: bool = False,
    monthly: bool = False,
    date_range: Optional[Tuple[datetime, datetime]] = None,
    max_workers: int = 5,
    cache: Optional[AuditCache] = None,
    force: bool = False,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[List[Dict], datetime, datetime]:
    """
    Audita os usuários em paralelo e retorna (lista_de_resultados, date_start, date_end).

    `orgs`: lista de organizações para filtrar (vazio = todas as orgs).

    Prioridade do range de datas:
      date_range — range explícito (--from/--to)
      monthly    — últimos 30 dias úteis
      weekly     — últimos 5 dias úteis
      (nenhum)   — último dia útil
    """
    orgs = orgs or []
    if date_range is not None:
        date_start, date_end = date_range
    elif monthly:
        date_start, date_end = get_monthly_range()
    elif weekly:
        date_start, date_end = get_weekly_range()
    else:
        date_start, date_end = get_audit_date()

    workers = min(max_workers, len(users)) if users else 1

    # Submete todos os usuários em paralelo preservando a ordem original
    results_map: Dict[str, Dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_user = {
            executor.submit(
                _audit_single_user,
                username, token, date_start, date_end,
                orgs, count_files,
                cache, force,
            ): username
            for username in users
        }
        for future in concurrent.futures.as_completed(future_to_user):
            username = future_to_user[future]
            try:
                results_map[username] = future.result()
            except Exception as exc:
                results_map[username] = _make_empty_row(
                    username, date_start, date_end, str(exc)
                )
            if progress_callback:
                progress_callback(username)

    # Reordena conforme a lista original de usuários
    results = [results_map[u] for u in users]

    # ── MVP: dev com maior SCI (ignorando erros) ──────────────────────────────
    valid = [r for r in results if not r.get("erro")]
    if valid:
        mvp = max(valid, key=lambda r: r["sci"])
        if mvp["sci"] > 0:
            mvp["is_mvp"] = True

    return results, date_start, date_end
