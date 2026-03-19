"""
Cliente para a API do GitHub.
Responsável por buscar commits, PRs, reviews e comentários de cada usuário.
"""

import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    def _get(self, url: str, params: Optional[Dict] = None) -> Union[Dict, List]:
        """Faz uma requisição GET e retorna o JSON."""
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Commits ────────────────────────────────────────────────────────────────

    def get_commits_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str] = None,
    ) -> List[Dict]:
        """Busca commits do usuário via Search API."""
        query = (
            f"author:{username} "
            f"committer-date:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        url = f"{self.BASE_URL}/search/commits"
        params: Dict = {
            "q": query,
            "sort": "committer-date",
            "order": "desc",
            "per_page": 100,
        }

        commits: List[Dict] = []
        page = 1
        while True:
            params["page"] = page
            data = self._get(url, params)
            items = data.get("items", [])
            commits.extend(items)
            if len(items) < 100 or len(commits) >= data.get("total_count", 0):
                break
            page += 1

        return commits

    def get_commit_stats(
        self,
        commits: List[Dict],
    ) -> Tuple[int, int, int]:
        """
        Percorre os detalhes de cada commit e retorna:
            (arquivos_únicos_alterados, total_additions, total_deletions)
        """
        changed_files: set = set()
        additions = 0
        deletions = 0

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
            except Exception:
                pass

        return len(changed_files), additions, deletions

    # ── Pull Requests ──────────────────────────────────────────────────────────

    def get_prs_for_user(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str] = None,
    ) -> List[Dict]:
        """Busca PRs criados pelo usuário via Search API."""
        query = (
            f"is:pr author:{username} "
            f"created:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        url = f"{self.BASE_URL}/search/issues"
        params: Dict = {
            "q": query,
            "sort": "created",
            "order": "desc",
            "per_page": 100,
        }

        prs: List[Dict] = []
        page = 1
        while True:
            params["page"] = page
            data = self._get(url, params)
            items = data.get("items", [])
            prs.extend(items)
            if len(items) < 100 or len(prs) >= data.get("total_count", 0):
                break
            page += 1

        return prs

    # ── Reviews ────────────────────────────────────────────────────────────────

    def get_reviews_count(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str] = None,
    ) -> int:
        """Conta PRs revisados pelo usuário no período (via Search API)."""
        query = (
            f"is:pr reviewed-by:{username} "
            f"updated:{date_start.strftime('%Y-%m-%d')}"
            f"..{date_end.strftime('%Y-%m-%d')}"
        )
        if org:
            query += f" org:{org}"

        url = f"{self.BASE_URL}/search/issues"
        data = self._get(url, {"q": query, "per_page": 1})
        return data.get("total_count", 0)

    # ── Comentários de Review (Events API) ────────────────────────────────────

    def get_review_comments_count(
        self,
        username: str,
        date_start: datetime,
        date_end: datetime,
        org: Optional[str] = None,
        max_pages: int = 10,
    ) -> int:
        """
        Conta comentários de review feitos pelo usuário no período.

        Usa a Events API (máx. 30 eventos/página × max_pages páginas).
        Contabiliza:
          - PullRequestReviewCommentEvent  → +1 por evento
          - PullRequestReviewEvent com corpo não-vazio → +1 por review
        """
        url = f"{self.BASE_URL}/users/{username}/events"
        count = 0

        for page in range(1, max_pages + 1):
            try:
                events = self._get(url, {"page": page, "per_page": 30})
            except Exception:
                break

            if not events:
                break

            stop_early = False
            for event in events:
                # Parsear data do evento
                try:
                    created_at = datetime.fromisoformat(
                        event["created_at"].replace("Z", "+00:00")
                    )
                except Exception:
                    continue

                # Eventos são retornados em ordem decrescente; parar se passamos do range
                if created_at < date_start:
                    stop_early = True
                    break

                if created_at > date_end:
                    continue

                # Filtro de organização
                if org:
                    event_org = (event.get("org") or {}).get("login", "")
                    repo_name = (event.get("repo") or {}).get("name", "")
                    if event_org != org and not repo_name.startswith(f"{org}/"):
                        continue

                etype = event.get("type", "")
                if etype == "PullRequestReviewCommentEvent":
                    count += 1
                elif etype == "PullRequestReviewEvent":
                    body = (
                        (event.get("payload") or {})
                        .get("review", {})
                        .get("body") or ""
                    )
                    if body.strip():
                        count += 1

            if stop_early or len(events) < 30:
                break

        return count
