"""
Fixtures compartilhadas entre todos os módulos de teste.
"""

import pytest
from datetime import datetime, timezone


@pytest.fixture
def date_start() -> datetime:
    """Sexta-feira 2025-03-14 00:00 UTC."""
    return datetime(2025, 3, 14, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def date_end() -> datetime:
    """Sexta-feira 2025-03-14 23:59:59 UTC."""
    return datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clear_github_token_env(monkeypatch):
    """
    Remove GITHUB_TOKEN do ambiente durante todos os testes para garantir
    que nenhum teste acidentalmente use um token real.
    """
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
