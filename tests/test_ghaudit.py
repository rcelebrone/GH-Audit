"""
Testes para ghaudit.py — CLI, parsing de argumentos, rendering e exportação.
"""

import csv
import io
import sys
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import ghaudit
from ghaudit import (
    parse_args, export_csv, render_table_plain, render_table_rich,
    _setup_logging, _build_rich_table, _print_summary_panel,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_result(
    usuario="dev",
    commits=3,
    prs=1,
    reviews=2,
    comments=1,
    arquivos_alterados=5,
    additions=20,
    deletions=10,
    sci=23.0,
    sci_level="yellow",
    profile_emoji="⚡",
    profile_tag="Ativo",
    insights=None,
    is_mvp=False,
    erro=None,
):
    return {
        "usuario": usuario,
        "commits": commits,
        "prs": prs,
        "reviews": reviews,
        "comments": comments,
        "arquivos_alterados": arquivos_alterados,
        "additions": additions,
        "deletions": deletions,
        "sci": sci,
        "sci_level": sci_level,
        "profile_emoji": profile_emoji,
        "profile_tag": profile_tag,
        "insights": insights or [],
        "is_mvp": is_mvp,
        "data_range": "14/03/2025 → 14/03/2025",
        "erro": erro,
    }


# ── parse_args ────────────────────────────────────────────────────────────────

class TestParseArgs:
    def test_defaults(self):
        args = _parse("")
        assert args.date_from is None
        assert args.date_to is None
        assert args.weekly is False
        assert args.month is False
        assert args.users is None
        assert args.orgs is None
        assert args.csv is None
        assert args.no_files is False
        assert args.token is None
        assert args.verbose is False
        assert args.debug is False
        assert args.force is False
        assert args.db is None

    def test_flag_weekly(self):
        args = _parse("--weekly")
        assert args.weekly is True
        assert args.month is False

    def test_flag_month(self):
        args = _parse("--month")
        assert args.month is True
        assert args.weekly is False

    def test_monthly_e_weekly_sao_mutuamente_exclusivos(self):
        with pytest.raises(SystemExit):
            _parse("--weekly --month")

    def test_flag_m_e_shorthand_de_month(self):
        args = _parse("-m")
        assert args.month is True

    def test_flag_w_e_shorthand_de_weekly(self):
        args = _parse("-w")
        assert args.weekly is True

    def test_from_e_to(self):
        args = _parse("--from 2025-03-01 --to 2025-03-18")
        assert args.date_from == "2025-03-01"
        assert args.date_to   == "2025-03-18"

    def test_force(self):
        args = _parse("--force")
        assert args.force is True

    def test_force_shorthand_f(self):
        args = _parse("-f")
        assert args.force is True

    def test_db(self):
        args = _parse("--db /tmp/custom.db")
        assert args.db == "/tmp/custom.db"

    def test_verbose(self):
        args = _parse("--verbose")
        assert args.verbose is True

    def test_verbose_shorthand_v(self):
        args = _parse("-v")
        assert args.verbose is True

    def test_debug(self):
        args = _parse("--debug")
        assert args.debug is True

    def test_max_workers_default(self):
        args = _parse("")
        assert args.max_workers == 5

    def test_max_workers_custom(self):
        args = _parse("--max-workers 2")
        assert args.max_workers == 2

    def test_users(self):
        args = _parse("--users user1 user2 user3")
        assert args.users == ["user1", "user2", "user3"]

    def test_orgs_unica(self):
        args = _parse("--orgs MyOrg")
        assert args.orgs == ["MyOrg"]

    def test_orgs_multiplas(self):
        args = _parse("--orgs OrgA OrgB OrgC")
        assert args.orgs == ["OrgA", "OrgB", "OrgC"]

    def test_orgs_shorthand_o(self):
        args = _parse("-o OrgA OrgB")
        assert args.orgs == ["OrgA", "OrgB"]

    def test_csv(self):
        args = _parse("--csv report.csv")
        assert args.csv == "report.csv"

    def test_no_files(self):
        args = _parse("--no-files")
        assert args.no_files is True

    def test_token(self):
        args = _parse("--token ghp_abc123")
        assert args.token == "ghp_abc123"

    def test_typo_mounth_nao_existe(self):
        with pytest.raises(SystemExit):
            _parse("--mounth")


def _parse(args_str: str):
    """Helper: faz parse de uma string de argumentos como se fossem sys.argv."""
    args = args_str.split() if args_str else []
    with patch("sys.argv", ["ghaudit"] + args):
        return parse_args()


# ── export_csv ────────────────────────────────────────────────────────────────

class TestExportCsv:
    def test_cria_arquivo_com_headers_corretos(self, tmp_path):
        filepath = str(tmp_path / "out.csv")
        results = [_make_result()]
        export_csv(results, filepath)

        with open(filepath, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        expected = [
            "usuario", "commits", "prs", "reviews", "comments",
            "arquivos_alterados", "additions", "deletions",
            "sci", "profile_tag", "data_range", "erro",
        ]
        assert headers == expected

    def test_dados_exportados_corretamente(self, tmp_path):
        filepath = str(tmp_path / "out.csv")
        r = _make_result(usuario="dev1", commits=5, sci=30.0)
        export_csv([r], filepath)

        with open(filepath, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 1
        assert rows[0]["usuario"] == "dev1"
        assert rows[0]["commits"] == "5"
        assert rows[0]["sci"] == "30.0"

    def test_campos_extras_no_dict_sao_ignorados(self, tmp_path):
        filepath = str(tmp_path / "out.csv")
        r = _make_result()
        r["campo_extra"] = "valor"  # não deve causar erro
        export_csv([r], filepath)  # extrasaction="ignore"

    def test_multiplos_usuarios(self, tmp_path):
        filepath = str(tmp_path / "out.csv")
        results = [_make_result(usuario=f"dev{i}") for i in range(5)]
        export_csv(results, filepath)

        with open(filepath, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        assert len(rows) == 5

    def test_encoding_utf8(self, tmp_path):
        filepath = str(tmp_path / "out.csv")
        r = _make_result(usuario="dev-ação")
        export_csv([r], filepath)

        with open(filepath, encoding="utf-8") as f:
            content = f.read()

        assert "dev-ação" in content


# ── render_table_plain ────────────────────────────────────────────────────────

class TestRenderTablePlain:
    def test_nao_levanta_excecao(self, capsys):
        results = [_make_result(), _make_result(usuario="dev2", is_mvp=True)]
        render_table_plain(results, "14/03/2025 (Sexta)", count_files=True)
        out = capsys.readouterr().out
        assert "ghaudit" in out

    def test_mvp_exibe_coroa(self, capsys):
        results = [_make_result(is_mvp=True)]
        render_table_plain(results, "14/03/2025", count_files=True)
        out = capsys.readouterr().out
        assert "👑" in out

    def test_sem_mvp_sem_coroa(self, capsys):
        results = [_make_result(is_mvp=False)]
        render_table_plain(results, "14/03/2025", count_files=True)
        out = capsys.readouterr().out
        assert "👑 MVP" not in out

    def test_no_files_exibe_traco(self, capsys):
        results = [_make_result()]
        render_table_plain(results, "14/03/2025", count_files=False)
        out = capsys.readouterr().out
        assert "—" in out


# ── render_table_rich ─────────────────────────────────────────────────────────

class TestRenderTableRich:
    def test_nao_levanta_excecao(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result(), _make_result(usuario="dev2", is_mvp=True)]
        render_table_rich(results, "14/03/2025 (Sexta)", count_files=True)

    def test_no_files_não_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result()]
        render_table_rich(results, "14/03/2025", count_files=False)

    def test_erro_exibido_em_insights(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result(erro="Timeout connecting to API")]
        # Não deve levantar exceção
        render_table_rich(results, "14/03/2025", count_files=True)


# ── main() — integração com mocks ────────────────────────────────────────────

class TestMain:
    _DATE_START = datetime(2025, 3, 14, 0, 0, 0, tzinfo=timezone.utc)
    _DATE_END   = datetime(2025, 3, 14, 23, 59, 59, tzinfo=timezone.utc)

    def _run(self, argv, audit_return=None):
        """Executa main() com argv e audit_users mockado."""
        if audit_return is None:
            audit_return = ([_make_result()], self._DATE_START, self._DATE_END)

        with patch("sys.argv", ["ghaudit"] + argv), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users", return_value=audit_return):
            ghaudit.main()

    def test_execucao_normal(self):
        self._run([])  # não deve levantar

    def _patch_common(self, argv, **kw):
        """Contexto base com todos os patches padrão (exceto argv e o que o caller quer)."""
        defaults = dict(
            GITHUB_TOKEN="tok",
            GITHUB_USERS=["dev1"],
            GITHUB_ORGS=[],
            GITHUB_SQUADS={},
        )
        defaults.update(kw)
        return [
            patch("sys.argv", ["ghaudit"] + argv),
            patch("ghaudit.GITHUB_TOKEN",  defaults["GITHUB_TOKEN"]),
            patch("ghaudit.GITHUB_USERS",  defaults["GITHUB_USERS"]),
            patch("ghaudit.GITHUB_ORGS",   defaults["GITHUB_ORGS"]),
            patch("ghaudit.GITHUB_SQUADS", defaults["GITHUB_SQUADS"]),
            patch("ghaudit.AuditCache"),
        ]

    def test_sem_token_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", ""), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_sem_users_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_data_invalida_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit", "--from", "nao-e-uma-data", "--to", "2025-01-31"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_audit_users_excecao_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users", side_effect=Exception("boom")):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_modo_weekly_passa_weekly_true(self):
        with patch("sys.argv", ["ghaudit", "--weekly"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("weekly") is True

    def test_modo_month_passa_monthly_true(self):
        with patch("sys.argv", ["ghaudit", "--month"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("monthly") is True

    def test_exporta_csv_quando_flag_passada(self, tmp_path):
        import os
        filepath = str(tmp_path / "out.csv")
        with patch("sys.argv", ["ghaudit", "--csv", filepath]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)):
            ghaudit.main()
        assert os.path.exists(filepath)

    def test_token_cli_sobrescreve_config(self):
        with patch("sys.argv", ["ghaudit", "--token", "cli_token"]), \
             patch("ghaudit.GITHUB_TOKEN", "config_token"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("token") == "cli_token"

    def test_orgs_cli_sobrescreve_config(self):
        with patch("sys.argv", ["ghaudit", "--orgs", "OrgA", "OrgB"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", ["OrgConfig"]), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("orgs") == ["OrgA", "OrgB"]

    def test_orgs_config_usadas_quando_sem_flag(self):
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", ["OrgFromEnv"]), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("orgs") == ["OrgFromEnv"]

    def test_from_to_passa_date_range(self):
        with patch("sys.argv", ["ghaudit", "--from", "2025-03-01", "--to", "2025-03-18"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        dr = mock_audit.call_args[1].get("date_range")
        assert dr is not None
        start, end = dr
        assert start.strftime("%Y-%m-%d") == "2025-03-01"
        assert end.strftime("%Y-%m-%d")   == "2025-03-18"

    def test_from_sem_to_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit", "--from", "2025-03-01"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_from_posterior_a_to_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit", "--from", "2025-03-18", "--to", "2025-03-01"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_from_to_com_weekly_chama_sys_exit(self):
        with patch("sys.argv", ["ghaudit", "--from", "2025-03-01", "--to", "2025-03-18", "--weekly"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_SQUADS", {}):
            with pytest.raises(SystemExit) as exc:
                ghaudit.main()
            assert exc.value.code == 1

    def test_force_passa_force_true(self):
        with patch("sys.argv", ["ghaudit", "--force"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("force") is True

    def test_db_customiza_caminho_do_cache(self, tmp_path):
        db_path = str(tmp_path / "custom.db")
        with patch("sys.argv", ["ghaudit", "--db", db_path]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache") as MockCache, \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)):
            ghaudit.main()
        MockCache.assert_called_once()
        called_path = str(MockCache.call_args[0][0])
        assert called_path == db_path

    def test_squads_usam_usuarios_das_squads(self):
        squads = {"BACKEND": ["alice", "bob"]}
        results = [_make_result("alice"), _make_result("bob")]
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", []), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", squads), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=(results, self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        called_users = mock_audit.call_args[1].get("users")
        assert set(called_users) == {"alice", "bob"}

    def test_users_cli_sobrescreve_squads(self):
        squads = {"BACKEND": ["alice", "bob"]}
        with patch("sys.argv", ["ghaudit", "--users", "carol"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", []), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", squads), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result("carol")], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        called_users = mock_audit.call_args[1].get("users")
        assert called_users == ["carol"]

    def test_max_workers_passa_para_audit_users(self):
        with patch("sys.argv", ["ghaudit", "--max-workers", "2"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("max_workers") == 2

    def test_max_workers_default_e_5(self):
        with patch("sys.argv", ["ghaudit"]), \
             patch("ghaudit.GITHUB_TOKEN", "tok"), \
             patch("ghaudit.GITHUB_USERS", ["dev1"]), \
             patch("ghaudit.GITHUB_ORGS", []), \
             patch("ghaudit.GITHUB_SQUADS", {}), \
             patch("ghaudit.AuditCache"), \
             patch("ghaudit.audit_users",
                   return_value=([_make_result()], self._DATE_START, self._DATE_END)) as mock_audit:
            ghaudit.main()
        assert mock_audit.call_args[1].get("max_workers") == 5


# ── config.py — leitura de variáveis de ambiente ──────────────────────────────

class TestConfig:
    """
    load_dotenv() é neutralizado em todos os testes desta classe via patch,
    garantindo que os valores venham apenas do os.environ controlado pelo teste.
    """

    def _reload(self, monkeypatch):
        """Recarrega config com load_dotenv desativado."""
        import importlib, config
        with patch("dotenv.load_dotenv"):
            importlib.reload(config)
        return config

    def test_github_token_lido_da_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok_from_env")
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_TOKEN == "tok_from_env"

    def test_github_token_vazio_sem_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_TOKEN == ""

    def test_github_users_lido_da_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERS", "user1,user2, user3")
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_USERS == ["user1", "user2", "user3"]

    def test_github_users_vazio_sem_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_USERS", raising=False)
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_USERS == []

    def test_github_orgs_lido_da_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_ORGS", "OrgA,OrgB")
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_ORGS == ["OrgA", "OrgB"]

    def test_github_orgs_vazio_sem_env(self, monkeypatch):
        monkeypatch.delenv("GITHUB_ORGS", raising=False)
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_ORGS == []

    def test_parse_list_ignora_espacos_em_branco(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERS", " dev1 , , dev2 , ")
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_USERS == ["dev1", "dev2"]

    # ── squads ────────────────────────────────────────────────────────────────

    def test_squad_simples_lido_da_env(self, monkeypatch):
        monkeypatch.setenv("SQUAD_BACKEND", "alice,bob")
        monkeypatch.delenv("SQUAD_FRONTEND", raising=False)
        monkeypatch.delenv("SQUAD_MOBILE",   raising=False)
        cfg = self._reload(monkeypatch)
        assert "BACKEND" in cfg.GITHUB_SQUADS
        assert cfg.GITHUB_SQUADS["BACKEND"] == ["alice", "bob"]

    def test_multiplas_squads_lidas(self, monkeypatch):
        monkeypatch.setenv("SQUAD_BACKEND",  "alice,bob")
        monkeypatch.setenv("SQUAD_FRONTEND", "carol,dave")
        monkeypatch.delenv("SQUAD_MOBILE", raising=False)
        cfg = self._reload(monkeypatch)
        assert "BACKEND"  in cfg.GITHUB_SQUADS
        assert "FRONTEND" in cfg.GITHUB_SQUADS

    def test_squad_com_espacos_removidos(self, monkeypatch):
        monkeypatch.setenv("SQUAD_BACKEND", " alice , bob , ")
        monkeypatch.delenv("SQUAD_FRONTEND", raising=False)
        monkeypatch.delenv("SQUAD_MOBILE",   raising=False)
        cfg = self._reload(monkeypatch)
        assert cfg.GITHUB_SQUADS["BACKEND"] == ["alice", "bob"]

    def test_squad_vazia_ignorada(self, monkeypatch):
        monkeypatch.setenv("SQUAD_BACKEND", "")
        monkeypatch.delenv("SQUAD_FRONTEND", raising=False)
        monkeypatch.delenv("SQUAD_MOBILE",   raising=False)
        cfg = self._reload(monkeypatch)
        assert "BACKEND" not in cfg.GITHUB_SQUADS

    def test_sem_squads_retorna_dict_vazio(self, monkeypatch):
        monkeypatch.delenv("SQUAD_BACKEND",  raising=False)
        monkeypatch.delenv("SQUAD_FRONTEND", raising=False)
        monkeypatch.delenv("SQUAD_MOBILE",   raising=False)
        cfg = self._reload(monkeypatch)
        # Verifica que nenhum nome de squad inesperado apareceu
        squad_keys = [k for k in cfg.GITHUB_SQUADS if k in ("BACKEND", "FRONTEND", "MOBILE")]
        assert squad_keys == []

    def test_squad_ordenada_alfabeticamente(self, monkeypatch):
        monkeypatch.setenv("SQUAD_ZETA",    "z1")
        monkeypatch.setenv("SQUAD_ALPHA",   "a1")
        monkeypatch.setenv("SQUAD_BACKEND", "b1")
        cfg = self._reload(monkeypatch)
        names = [k for k in cfg.GITHUB_SQUADS if k in ("ZETA", "ALPHA", "BACKEND")]
        assert names == sorted(names)


# ── _setup_logging ────────────────────────────────────────────────────────────

class TestSetupLogging:
    def test_padrao_nao_levanta(self):
        _setup_logging(debug=False, verbose=False)

    def test_verbose_nao_levanta(self):
        _setup_logging(debug=False, verbose=True)

    def test_debug_nao_levanta(self):
        _setup_logging(debug=True, verbose=False)


# ── _build_rich_table ─────────────────────────────────────────────────────────

class TestBuildRichTable:
    def test_retorna_table_com_numero_correto_de_linhas(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        rows = [_make_result(), _make_result(usuario="dev2")]
        table = _build_rich_table(rows, count_files=True, table_title="Test")
        assert table.row_count == 2

    def test_squad_mvp_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        rows = [_make_result(usuario="mvp"), _make_result(usuario="other")]
        table = _build_rich_table(rows, count_files=True, table_title="T", squad_mvp_user="mvp")
        assert table.row_count == 2

    def test_global_mvp_nao_recebe_trofeu_de_squad(self):
        """MVP global (👑) nunca deve ser marcado como MVP de squad (🏆) também."""
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        # is_mvp=True → não é is_squad_m, pois a condição é `not row.get("is_mvp")`
        rows = [_make_result(usuario="top", is_mvp=True)]
        # squad_mvp_user=top, mas is_mvp=True → is_squad_m deve ser False
        table = _build_rich_table(rows, count_files=True, table_title="T", squad_mvp_user="top")
        assert table.row_count == 1

    def test_no_files_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        rows = [_make_result()]
        table = _build_rich_table(rows, count_files=False, table_title="T")
        assert table.row_count == 1


# ── _print_summary_panel ──────────────────────────────────────────────────────

class TestPrintSummaryPanel:
    def test_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result(), _make_result(usuario="dev2", is_mvp=True)]
        _print_summary_panel(results, cache_hits=0)

    def test_com_cache_hits_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result()]
        _print_summary_panel(results, cache_hits=1)

    def test_com_erros_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result(erro="timeout")]
        _print_summary_panel(results, cache_hits=0)


# ── render_table_rich com squads ──────────────────────────────────────────────

class TestRenderTableRichSquads:
    def test_com_squads_nao_levanta(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result("alice"), _make_result("bob"), _make_result("carol")]
        squads = {"BACKEND": ["alice", "bob"]}
        render_table_rich(results, "Título", count_files=True, squads=squads)

    def test_usuarios_sem_squad_agrupados_em_outros(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result("alice"), _make_result("external")]
        squads = {"BACKEND": ["alice"]}
        # "external" não pertence a nenhuma squad → aparece em "Outros"
        render_table_rich(results, "Título", count_files=True, squads=squads)

    def test_squad_com_todos_na_squad_sem_outros(self):
        if not ghaudit.HAS_RICH:
            pytest.skip("Rich não instalado")
        results = [_make_result("alice"), _make_result("bob")]
        squads = {"BACKEND": ["alice", "bob"]}
        render_table_rich(results, "Título", count_files=True, squads=squads)


# ── render_table_plain com squads ─────────────────────────────────────────────

class TestRenderTablePlainSquads:
    def test_squad_label_aparece_no_output(self, capsys):
        results = [_make_result("alice"), _make_result("bob")]
        squads = {"BACKEND": ["alice", "bob"]}
        render_table_plain(results, "Título", count_files=True, squads=squads)
        out = capsys.readouterr().out
        assert "BACKEND" in out

    def test_outros_label_quando_ha_usuarios_sem_squad(self, capsys):
        results = [_make_result("alice"), _make_result("external")]
        squads = {"BACKEND": ["alice"]}
        render_table_plain(results, "Título", count_files=True, squads=squads)
        out = capsys.readouterr().out
        assert "Outros" in out

    def test_sem_squads_nao_exibe_label_de_squad(self, capsys):
        results = [_make_result()]
        render_table_plain(results, "Título", count_files=True, squads=None)
        out = capsys.readouterr().out
        assert "Squad:" not in out
