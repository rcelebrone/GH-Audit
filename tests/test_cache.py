"""
Testes para cache.py — AuditCache SQLite thread-safe.
"""

import threading
import pytest
from pathlib import Path

from cache import AuditCache, _make_key


# ── _make_key ─────────────────────────────────────────────────────────────────

class TestMakeKey:
    def test_formato_pipe_separado(self):
        key = _make_key("user1", "2025-03-14T00:00:00+00:00", "2025-03-14T23:59:59+00:00", '["OrgA"]', True)
        assert key == 'user1|2025-03-14T00:00:00+00:00|2025-03-14T23:59:59+00:00|["OrgA"]|1'

    def test_count_files_false_gera_0(self):
        key = _make_key("user", "s", "e", "[]", False)
        assert key.endswith("|0")

    def test_count_files_true_gera_1(self):
        key = _make_key("user", "s", "e", "[]", True)
        assert key.endswith("|1")

    def test_usuarios_diferentes_geram_chaves_diferentes(self):
        k1 = _make_key("alice", "2025-01-01", "2025-01-31", "[]", True)
        k2 = _make_key("bob",   "2025-01-01", "2025-01-31", "[]", True)
        assert k1 != k2

    def test_orgs_diferentes_geram_chaves_diferentes(self):
        k1 = _make_key("u", "s", "e", '["OrgA"]', True)
        k2 = _make_key("u", "s", "e", '["OrgB"]', True)
        assert k1 != k2

    def test_datas_diferentes_geram_chaves_diferentes(self):
        k1 = _make_key("u", "2025-01-01", "2025-01-31", "[]", True)
        k2 = _make_key("u", "2025-02-01", "2025-02-28", "[]", True)
        assert k1 != k2


# ── AuditCache ────────────────────────────────────────────────────────────────

class TestAuditCache:
    @pytest.fixture
    def cache(self, tmp_path):
        """Cache com banco em diretório temporário para não poluir ~/.ghaudit."""
        db_path = tmp_path / "test_cache.db"
        c = AuditCache(db_path)
        yield c
        c.close()

    # ── get/put básicos ───────────────────────────────────────────────────────

    def test_miss_em_cache_vazio(self, cache):
        assert cache.get("chave_inexistente") is None

    def test_put_e_get_retornam_mesmo_valor(self, cache):
        data = {"usuario": "alice", "commits": 5, "sci": 20.0}
        cache.put("k1", data)
        assert cache.get("k1") == data

    def test_put_atualiza_chave_existente(self, cache):
        cache.put("k1", {"sci": 10.0})
        cache.put("k1", {"sci": 99.0})
        assert cache.get("k1")["sci"] == 99.0

    def test_miss_apos_chave_diferente(self, cache):
        cache.put("k1", {"val": 1})
        assert cache.get("k2") is None

    def test_multiplas_chaves_independentes(self, cache):
        cache.put("k1", {"a": 1})
        cache.put("k2", {"b": 2})
        assert cache.get("k1") == {"a": 1}
        assert cache.get("k2") == {"b": 2}

    # ── list_entries ──────────────────────────────────────────────────────────

    def test_list_entries_em_cache_vazio(self, cache):
        assert cache.list_entries() == []

    def test_list_entries_retorna_todas_as_chaves(self, cache):
        cache.put("k1", {"a": 1})
        cache.put("k2", {"b": 2})
        entries = cache.list_entries()
        keys = [e["key"] for e in entries]
        assert "k1" in keys
        assert "k2" in keys
        assert len(entries) == 2

    def test_list_entries_contem_created_at(self, cache):
        cache.put("k1", {"x": 1})
        entries = cache.list_entries()
        assert "created_at" in entries[0]

    # ── persistência ──────────────────────────────────────────────────────────

    def test_persiste_dados_complexos(self, cache):
        data = {
            "usuario": "dev",
            "commits": 3,
            "prs": 1,
            "reviews": 2,
            "comments": 1,
            "arquivos_alterados": 5,
            "additions": 100,
            "deletions": 50,
            "sci": 42.5,
            "sci_level": "green",
            "profile_emoji": "🔨",
            "profile_tag": "Construtor",
            "insights": ["🔥 Alta Entrega"],
            "is_mvp": False,
            "from_cache": False,
            "erro": None,
            "data": "14/03/2025",
            "data_range": "14/03/2025 → 14/03/2025",
        }
        cache.put("full_key", data)
        assert cache.get("full_key") == data

    def test_persiste_entre_instancias(self, tmp_path):
        """Dados gravados numa instância são recuperados por outra com o mesmo arquivo."""
        db_path = tmp_path / "shared.db"
        c1 = AuditCache(db_path)
        c1.put("k", {"val": 42})
        c1.close()

        c2 = AuditCache(db_path)
        assert c2.get("k") == {"val": 42}
        c2.close()

    def test_cria_diretorio_pai_se_necessario(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / "cache.db"
        c = AuditCache(nested)
        c.put("k", {"v": 1})
        assert nested.exists()
        c.close()

    # ── caminho customizado ───────────────────────────────────────────────────

    def test_caminho_customizado_usado(self, tmp_path):
        custom_path = tmp_path / "custom.db"
        c = AuditCache(custom_path)
        c.put("k", {"val": 1})
        assert c.get("k") == {"val": 1}
        assert custom_path.exists()
        c.close()

    # ── thread safety ─────────────────────────────────────────────────────────

    def test_writes_concorrentes_sem_corrupcao(self, cache):
        """20 threads escrevendo simultaneamente; nenhuma deve corromper o banco."""
        errors = []

        def writer(i):
            try:
                cache.put(f"key_{i}", {"index": i})
                result = cache.get(f"key_{i}")
                assert result == {"index": i}
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Erros nas threads: {errors}"
        assert len(cache.list_entries()) == 20

    def test_reads_concorrentes_nao_bloqueiam(self, cache):
        """Múltiplas leituras simultâneas são atômicas e retornam valor correto."""
        cache.put("shared_key", {"data": "value"})
        results = []
        errors = []

        def reader():
            try:
                results.append(cache.get("shared_key"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert all(r == {"data": "value"} for r in results)
