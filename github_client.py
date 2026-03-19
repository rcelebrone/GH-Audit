"""
Cliente para a API do GitHub.
Responsável por buscar commits, PRs, reviews e comentários de cada usuário.
"""

import logging
import time
import warnings
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

log = logging.getLogger(__name__)


class GitHubClient:
    BASE_URL = "https://api.github.com"
    SEARCH_API_MAX = 1000  # GitHub Search API limita resultados a 1000 itens

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, url: str, params: Optional[Dict] = None) -> Union[Dict, List]:
        """GET com retry automático para rate limit (403/429)."""
        last_resp = None
        for attempt in range(1, 4):
            log.debug("GET %s params=%s (tentativa %d/3)", url, params, attempt)
            resp = self.session.get(url, params=params)
            last_resp = resp
            log.debug("← %d  RateLimit-Remaining=%s",
                      resp.status_code,
                      resp.headers.get("X-RateLimit-Remaining", "?"))

            # Rate limit secundário (burst/concorrência)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                log.warning("Rate limit secundário (429) — aguardando %ds", retry_after)
                time.sleep(retry_after)
                continue

            # Rate limit primário (quota esgotada) ou outro 403
            if resp.status_code == 403:
                remaining = resp.headers.get("X-RateLimit-Remaining", "1")
                reset_ts  = resp.headers.get("X-RateLimit-Reset")
                if remaining == "0" and reset_ts:
                    wait = max(1, int(reset_ts) - int(time.time())) + 1
                    log.warning("Rate limit primário (403) — aguardando %ds", wait)
                    time.sleep(wait)
                    continue
                log.error("403 Forbidden (não é rate limit): %s", resp.text[:200])
                resp.raise_for_status()

            resp.raise_for_status()
            return resp.json()

        last_resp.raise_for_status()
        return last_resp.json()  # nunca alcançado

    def _paginate_search(self, url: str, params: Dict) -> Tuple[List[Dict], int]:
        """
        Itera páginas da Search API respeitando o limite de 1000 resultados.
        Retorna (items, total_count_reportado_pela_api).
        """
        items: List[Dict] = []
        page = 1
        total_count = 0

        while True:
            params["page"] = page
            data = self._get(url, params)
            batch = data.get("items", [])
            total_count = data.get("total_count", 0)
            items.extend(batch)

            log.debug("  página %d → %d itens (total_count=%d, acumulado=%d)",
                      page, len(batch), total_count, len(items))

            if len(items) >= self.SEARCH_API_MAX:
                if total_count > self.SEARCH_API_MAX:
                    warnings.warn(
                        f"Search API: total_count={total_count} excede o limite de "
                        f"{self.SEARCH_API_MAX} resultados retornáveis. "
                        "Dados podem estar incompletos.",
                        RuntimeWarning,
                        stacklevel=3,
                    )
                break

            if len(batch) < 100 or len(items) >= total_count:
                break

            page += 1

        return items, total_count

    # ── Commits ────────────────────────────────────────────────────────────────

    def _search_commits_for_org(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str],
    ) -> List[Dict]:
        """Busca commits do usuário para uma org específica (ou todas, se org=None)."""
        query = (
            f"author:{username} "
            f"author-date:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        log.debug("[commits] query: %s", query)
        params: Dict = {
            "q":        query,
            "sort":     "committer-date",
            "order":    "desc",
            "per_page": 100,
        }
        items, total = self._paginate_search(f"{self.BASE_URL}/search/commits", params)
        log.info("[commits] %s | org=%s → %d/%d resultados",
                 username, org or "*", len(items), total)
        return items

    def get_commits_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        orgs: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Busca commits do usuário via Search API.

        Se `orgs` contiver múltiplas organizações, executa uma busca por org
        e deduplica os resultados pelo SHA do commit.
        """
        if not orgs:
            return self._search_commits_for_org(username, date_start, date_end, None)

        seen: Dict[str, Dict] = {}
        for org in orgs:
            for commit in self._search_commits_for_org(username, date_start, date_end, org):
                sha = commit.get("sha") or commit.get("url", "")
                seen[sha] = commit
        log.info("[commits] %s | total deduplic. = %d", username, len(seen))
        return list(seen.values())

    def get_commit_stats(self, commits: List[Dict]) -> Tuple[int, int, int]:
        """
        Percorre os detalhes de cada commit e retorna:
            (arquivos_únicos_alterados, total_additions, total_deletions)
        """
        changed_files: set = set()
        additions = 0
        deletions = 0

        log.debug("[commit_stats] buscando detalhes de %d commit(s)", len(commits))
        for commit in commits:
            url = commit.get("url")
            if not url:
                continue
            try:
                detail = self._get(url)
                stats = detail.get("stats", {})
                additions += stats.get("additions", 0)
                deletions += stats.get("deletions", 0)
                for f in detail.get("files", []):
                    changed_files.add(f["filename"])
            except Exception as exc:
                log.warning("[commit_stats] erro ao buscar %s: %s", url, exc)

        log.debug("[commit_stats] arquivos=%d, +%d, -%d",
                  len(changed_files), additions, deletions)
        return len(changed_files), additions, deletions

    # ── Pull Requests ──────────────────────────────────────────────────────────

    def _search_prs_for_org(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str],
    ) -> List[Dict]:
        """Busca PRs criados pelo usuário para uma org específica."""
        query = (
            f"is:pr author:{username} "
            f"created:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        log.debug("[prs] query: %s", query)
        params: Dict = {
            "q":        query,
            "sort":     "created",
            "order":    "desc",
            "per_page": 100,
        }
        items, total = self._paginate_search(f"{self.BASE_URL}/search/issues", params)
        log.info("[prs] %s | org=%s → %d/%d resultados",
                 username, org or "*", len(items), total)
        return items

    def get_prs_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        orgs: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Busca PRs criados pelo usuário via Search API.

        Se `orgs` contiver múltiplas organizações, executa uma busca por org
        e deduplica pelo número do PR + repositório.
        """
        if not orgs:
            return self._search_prs_for_org(username, date_start, date_end, None)

        seen: Dict[str, Dict] = {}
        for org in orgs:
            for pr in self._search_prs_for_org(username, date_start, date_end, org):
                key = str(pr.get("id") or pr.get("url", ""))
                seen[key] = pr
        log.info("[prs] %s | total deduplic. = %d", username, len(seen))
        return list(seen.values())

    # ── Reviews (Search API: reviewed-by:) ────────────────────────────────────

    def _search_reviews_for_org(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str],
    ) -> List[Dict]:
        """
        Busca PRs revisados pelo usuário em uma org via Search API.

        Usa `reviewed-by:` + `updated:` como janela de tempo: se um PR recebeu
        uma revisão no período, o campo `updated_at` do PR avança para aquela data.
        """
        query = (
            f"is:pr reviewed-by:{username} "
            f"updated:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        log.debug("[reviews] query: %s", query)
        params: Dict = {
            "q":        query,
            "sort":     "updated",
            "order":    "desc",
            "per_page": 100,
        }
        items, total = self._paginate_search(f"{self.BASE_URL}/search/issues", params)
        log.info("[reviews] %s | org=%s → %d/%d resultados",
                 username, org or "*", len(items), total)
        return items

    def get_reviews_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        orgs: Optional[List[str]] = None,
    ) -> int:
        """
        Conta PRs revisados pelo usuário (reviewed-by: Search API).

        Retorna o número de PRs distintos revisados no período.
        """
        if not orgs:
            return len(self._search_reviews_for_org(username, date_start, date_end, None))

        seen: Dict[str, Dict] = {}
        for org in orgs:
            for pr in self._search_reviews_for_org(username, date_start, date_end, org):
                seen[str(pr.get("id") or pr.get("url", ""))] = pr
        log.info("[reviews] %s | total deduplic. = %d", username, len(seen))
        return len(seen)

    # ── Comentários em PRs (Search API: commenter:) ────────────────────────────

    def _search_pr_comments_for_org(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str],
    ) -> List[Dict]:
        """
        Busca PRs alheios em que o usuário comentou.

        Exclui PRs de autoria do próprio usuário (`-author:`) para medir
        engajamento com o trabalho dos colegas, não respostas ao próprio PR.
        """
        query = (
            f"is:pr commenter:{username} -author:{username} "
            f"updated:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        log.debug("[comments] query: %s", query)
        params: Dict = {
            "q":        query,
            "sort":     "updated",
            "order":    "desc",
            "per_page": 100,
        }
        items, total = self._paginate_search(f"{self.BASE_URL}/search/issues", params)
        log.info("[comments] %s | org=%s → %d/%d resultados",
                 username, org or "*", len(items), total)
        return items

    def get_pr_comments_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        orgs: Optional[List[str]] = None,
    ) -> int:
        """
        Conta PRs alheios em que o usuário comentou no período.

        Retorna o número de PRs distintos comentados (excluindo os de autoria própria).
        """
        if not orgs:
            return len(self._search_pr_comments_for_org(username, date_start, date_end, None))

        seen: Dict[str, Dict] = {}
        for org in orgs:
            for pr in self._search_pr_comments_for_org(username, date_start, date_end, org):
                seen[str(pr.get("id") or pr.get("url", ""))] = pr
        log.info("[comments] %s | total deduplic. = %d", username, len(seen))
        return len(seen)
