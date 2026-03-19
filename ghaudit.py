#!/usr/bin/env python3
"""
ghaudit — GitHub Activity Auditor

CLI para auditar a atividade diária, semanal ou mensal de desenvolvedores
dentro de uma organização do GitHub.

Uso:
    python3 ghaudit.py [OPÇÕES]

Exemplos:
    # Auditoria diária padrão (dia anterior)
    python3 ghaudit.py

    # Auditoria semanal (últimos 5 dias úteis)
    python3 ghaudit.py --weekly

    # Auditoria mensal (últimos 30 dias úteis)
    python3 ghaudit.py --month

    # Auditar uma data específica
    python3 ghaudit.py --date 2025-03-14

    # Passar usuários diretamente
    python3 ghaudit.py --users rcelebrone user1 user2

    # Exportar para CSV
    python3 ghaudit.py --csv relatorio.csv

    # Sem contagem de arquivos (mais rápido)
    python3 ghaudit.py --no-files
"""

import argparse
import csv
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

# Rich para output colorido no terminal
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import (
        Progress, SpinnerColumn, BarColumn,
        TextColumn, MofNCompleteColumn, TimeElapsedColumn,
    )
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from cache import AuditCache, DEFAULT_DB_PATH
from config import GITHUB_TOKEN, GITHUB_USERS, GITHUB_ORGS, GITHUB_SQUADS
from auditor import audit_users

console = Console() if HAS_RICH else None

# ── Helpers de display ────────────────────────────────────────────────────────

WEEKDAYS_PT = {
    "Monday":    "Segunda",
    "Tuesday":   "Terça",
    "Wednesday": "Quarta",
    "Thursday":  "Quinta",
    "Friday":    "Sexta",
    "Saturday":  "Sábado",
    "Sunday":    "Domingo",
}


def _lines_str_rich(adds: int, dels: int, count_files: bool) -> str:
    if not count_files:
        return "[dim]—[/dim]"
    return f"[green]+{adds}[/green] [red]-{dels}[/red]"


def _sci_rich(sci: float, level: str) -> str:
    return f"[{level} bold]{sci:.1f}[/{level} bold]"


def _username_rich(username: str, is_mvp: bool, is_squad_mvp: bool = False) -> str:
    if is_mvp:
        return f"[bold gold1]👑 {username}[/bold gold1]"
    if is_squad_mvp:
        return f"[bold yellow]🏆 {username}[/bold yellow]"
    return f"[white]{username}[/white]"


def _build_rich_table(
    rows: List[Dict],
    count_files: bool,
    table_title: str,
    squad_mvp_user: str = "",
) -> "Table":
    """Cria e preenche uma Rich Table para um grupo de resultados."""
    table = Table(
        title=table_title,
        box=box.ROUNDED,
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )
    table.add_column("Usuário",                        min_width=16)
    table.add_column("Commits",    justify="center",   width=9)
    table.add_column("PRs",        justify="center",   width=5)
    table.add_column("Reviews",    justify="center",   width=9)
    table.add_column("Coments.",   justify="center",   width=10)
    table.add_column("Arquivos",   justify="center",   width=9)
    table.add_column("+Adds/-Dels",justify="center",   width=14)
    table.add_column("SCI",        justify="center",   width=8)
    table.add_column("Perfil",                         min_width=18)
    table.add_column("Insights",                       min_width=22)

    for row in rows:
        erro        = row.get("erro") or ""
        is_squad_m  = (row["usuario"] == squad_mvp_user and not row.get("is_mvp"))
        name_str    = _username_rich(row["usuario"], row.get("is_mvp", False), is_squad_m)
        sci_str     = _sci_rich(row["sci"], row["sci_level"])
        profile_str = f"{row['profile_emoji']} {row['profile_tag']}"
        insights_list = row.get("insights", [])
        insights_str = (
            f"[red dim]{erro[:45]}[/red dim]" if erro
            else ("  ".join(insights_list) if insights_list else "[dim]—[/dim]")
        )
        lines_str = _lines_str_rich(row["additions"], row["deletions"], count_files)
        table.add_row(
            name_str,
            str(row["commits"]),
            str(row["prs"]),
            str(row["reviews"]),
            str(row["comments"]),
            str(row["arquivos_alterados"]) if count_files else "[dim]—[/dim]",
            lines_str,
            sci_str,
            profile_str,
            insights_str,
        )
    return table


def _print_summary_panel(results: List[Dict], cache_hits: int) -> None:
    total  = len(results)
    errors = sum(1 for r in results if r.get("erro"))
    high   = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "green")
    medium = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "yellow")
    low    = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "red")
    mvp_row  = next((r for r in results if r.get("is_mvp")), None)
    mvp_line = (
        f"   [bold gold1]👑 MVP: {mvp_row['usuario']} (SCI {mvp_row['sci']:.1f})[/bold gold1]"
        if mvp_row else ""
    )
    cache_line = f"   [dim]💾 Cache: {cache_hits}/{total}[/dim]" if cache_hits > 0 else ""
    console.print(Panel(
        f"[bold]Total:[/bold] {total}   "
        f"[green bold]Alta: {high}[/green bold]   "
        f"[yellow]Normal: {medium}[/yellow]   "
        f"[red]Baixa: {low}[/red]   "
        f"[red dim]Erros: {errors}[/red dim]"
        f"{mvp_line}{cache_line}",
        title="[bold]Resumo Geral",
        border_style="cyan",
    ))


# ── Render Rich ───────────────────────────────────────────────────────────────

def render_table_rich(
    results: List[Dict],
    title: str,
    count_files: bool,
    cache_hits: int = 0,
    squads: Optional[Dict[str, List[str]]] = None,
) -> None:
    """Exibe a tabela com Rich. Com squads, imprime uma tabela por squad."""
    console.print()
    console.print(f"[bold cyan]📊 ghaudit — {title}[/bold cyan]")

    legend = (
        "  [green]●[/green] SCI ≥ 25 Alta Produtividade   "
        "[yellow]●[/yellow] SCI 10-24 Normal   "
        "[red]●[/red] SCI < 10 Baixa Atividade"
    )

    if not squads:
        table = _build_rich_table(results, count_files, "")
        console.print(table)
        console.print(legend)
        console.print()
        _print_summary_panel(results, cache_hits)
        console.print()
        return

    # ── Modo squad: uma tabela por squad ──────────────────────────────────────
    result_by_user = {r["usuario"]: r for r in results}
    assigned: set = set()

    for squad_name, squad_users in squads.items():
        squad_rows = [result_by_user[u] for u in squad_users if u in result_by_user]
        if not squad_rows:
            continue
        assigned.update(r["usuario"] for r in squad_rows)

        # MVP da squad: maior SCI sem erro
        valid = [r for r in squad_rows if not r.get("erro")]
        squad_mvp_user = ""
        if valid:
            best = max(valid, key=lambda r: r["sci"])
            if best["sci"] > 0 and not best.get("is_mvp"):
                squad_mvp_user = best["usuario"]

        high  = sum(1 for r in squad_rows if not r.get("erro") and r["sci_level"] == "green")
        total = len(squad_rows)
        table_title = (
            f"[bold]{squad_name}[/bold]  "
            f"[dim]{total} dev{'s' if total > 1 else ''}  •  "
            f"{high}/{total} alta produtividade[/dim]"
        )
        table = _build_rich_table(
            squad_rows, count_files, table_title,
            squad_mvp_user=squad_mvp_user,
        )
        console.print(table)

    # Usuários sem squad
    others = [r for r in results if r["usuario"] not in assigned]
    if others:
        table = _build_rich_table(others, count_files, "[dim]Outros[/dim]")
        console.print(table)

    console.print(legend)
    console.print()
    _print_summary_panel(results, cache_hits)
    console.print()


# ── Render plain (fallback sem Rich) ─────────────────────────────────────────

def _print_plain_rows(rows: List[Dict], count_files: bool, widths: List[int]) -> None:
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(sep)
    for row in rows:
        crown = "👑 " if row.get("is_mvp") else ""
        vals = [
            f"{crown}{row['usuario']}"[:widths[0]],
            str(row["commits"]),
            str(row["prs"]),
            str(row["reviews"]),
            str(row["comments"]),
            str(row["arquivos_alterados"]) if count_files else "—",
            f"{row['sci']:.1f}",
            f"{row['profile_emoji']} {row['profile_tag']}"[:widths[7]],
        ]
        print("|" + "|".join(f" {v:<{widths[i]}} " for i, v in enumerate(vals)) + "|")
    print(sep)


def render_table_plain(
    results: List[Dict],
    title: str,
    count_files: bool,
    squads: Optional[Dict[str, List[str]]] = None,
) -> None:
    """Exibe a tabela em texto puro (sem Rich)."""
    headers = ["Usuário", "Cmts", "PRs", "Revs", "Comnts", "Arqs", "SCI", "Perfil"]
    widths  = [    18,     5,     4,     5,      6,       5,     7,      20  ]
    sep     = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr     = "|" + "|".join(f" {h:<{widths[i]}} " for i, h in enumerate(headers)) + "|"

    print(f"\n{'='*70}")
    print(f"  ghaudit — {title}")
    print(f"{'='*70}")
    print(sep)
    print(hdr)

    if squads:
        result_by_user = {r["usuario"]: r for r in results}
        assigned: set = set()
        for squad_name, squad_users in squads.items():
            squad_rows = [result_by_user[u] for u in squad_users if u in result_by_user]
            if not squad_rows:
                continue
            assigned.update(r["usuario"] for r in squad_rows)
            label = f"── Squad: {squad_name} "
            print(f"|{label:<{sum(widths) + len(widths)*3 - 1}}|")
            _print_plain_rows(squad_rows, count_files, widths)
            print(sep)
            print(hdr)
        others = [r for r in results if r["usuario"] not in assigned]
        if others:
            label = "── Outros "
            print(f"|{label:<{sum(widths) + len(widths)*3 - 1}}|")
            _print_plain_rows(others, count_files, widths)
    else:
        _print_plain_rows(results, count_files, widths)

    mvp_row = next((r for r in results if r.get("is_mvp")), None)
    if mvp_row:
        print(f"\n👑 MVP: {mvp_row['usuario']} (SCI {mvp_row['sci']:.1f})")
    print()


# ── Export CSV ────────────────────────────────────────────────────────────────

def export_csv(results: List[Dict], filepath: str) -> None:
    """Exporta os resultados para um arquivo CSV."""
    fieldnames = [
        "usuario", "commits", "prs", "reviews", "comments",
        "arquivos_alterados", "additions", "deletions",
        "sci", "profile_tag", "data_range", "erro",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ghaudit",
        description="Audita a atividade diária, semanal ou mensal de devs no GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--from", dest="date_from",
        type=str, default=None, metavar="YYYY-MM-DD",
        help="Início do range de datas (inclusivo). Requer --to.",
    )
    parser.add_argument(
        "--to", dest="date_to",
        type=str, default=None, metavar="YYYY-MM-DD",
        help="Fim do range de datas (inclusivo). Requer --from.",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--weekly", "-w",
        action="store_true", default=False,
        help="Audita os últimos 5 dias úteis (visão semanal de produtividade).",
    )
    mode_group.add_argument(
        "--month", "-m",
        action="store_true", default=False,
        help="Audita os últimos 30 dias úteis (visão mensal de produtividade).",
    )

    parser.add_argument(
        "--users", "-u",
        nargs="+", default=None, metavar="USUARIO",
        help="Lista de usuários. Sobrescreve GITHUB_USERS do config.py.",
    )
    parser.add_argument(
        "--orgs", "-o",
        nargs="+", default=None, metavar="ORG",
        help="Organizações GitHub (uma ou mais). Sobrescreve GITHUB_ORGS do config.py.",
    )
    parser.add_argument(
        "--csv",
        type=str, default=None, metavar="ARQUIVO.csv",
        help="Exporta o resultado para um arquivo CSV.",
    )
    parser.add_argument(
        "--no-files",
        action="store_true", default=False,
        help="Não busca detalhes de arquivos/additions/deletions (mais rápido).",
    )
    parser.add_argument(
        "--token", "-t",
        type=str, default=None, metavar="TOKEN",
        help="Token do GitHub. Sobrescreve GITHUB_TOKEN do config.py.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true", default=False,
        help="Exibe logs de INFO/WARNING durante a execução.",
    )
    parser.add_argument(
        "--debug",
        action="store_true", default=False,
        help="Exibe logs DEBUG detalhados (queries, contagens, rate limit). Implica --verbose.",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true", default=False,
        help="Ignora o cache e re-busca os dados do GitHub. Atualiza o cache ao final.",
    )
    parser.add_argument(
        "--db",
        type=str, default=None, metavar="CAMINHO",
        help=f"Caminho do banco SQLite de cache. Padrão: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--max-workers",
        type=int, default=5, metavar="N",
        help="Máximo de usuários processados em paralelo (padrão: 5). "
             "Reduza para evitar rate limit ao usar --force com muitos usuários.",
    )

    return parser.parse_args()


def _setup_logging(debug: bool, verbose: bool) -> None:
    """
    Três níveis de verbosidade:
      padrão  → CRITICAL  (silencioso; apenas a progress bar é exibida)
      verbose → INFO      (mostra progresso por usuário)
      debug   → DEBUG     (queries, paginação, rate limit)
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.CRITICAL  # silencia tudo

    if HAS_RICH:
        logging.basicConfig(
            level=level,
            format="%(name)s — %(message)s",
            datefmt="[%H:%M:%S]",
            handlers=[RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )],
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
    # Sempre silencia bibliotecas externas a não ser no modo debug
    if not debug:
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        logging.getLogger("requests").setLevel(logging.CRITICAL)


def main() -> None:
    args = parse_args()
    _setup_logging(args.debug, args.verbose)

    # ── Resolver configurações (CLI sobrescreve env vars) ─────────────────────
    token       = args.token or GITHUB_TOKEN
    orgs        = args.orgs  or GITHUB_ORGS
    count_files = not args.no_files

    # Usuários: --users > GITHUB_SQUADS (expandido) > GITHUB_USERS
    if args.users:
        users  = args.users
        squads: Dict[str, List[str]] = {}
    elif GITHUB_SQUADS:
        seen: set = set()
        users = []
        for sq_users in GITHUB_SQUADS.values():
            for u in sq_users:
                if u not in seen:
                    users.append(u)
                    seen.add(u)
        squads = GITHUB_SQUADS
    else:
        users  = GITHUB_USERS
        squads = {}

    # ── Validações ────────────────────────────────────────────────────────────
    if not token:
        print("❌  Token do GitHub não configurado.")
        print("    Defina GITHUB_TOKEN como variável de ambiente ou use --token <TOKEN>")
        sys.exit(1)

    if not users:
        print("❌  Nenhum usuário informado.")
        print("    Configure GITHUB_USERS ou SQUAD_<NOME> como variáveis de ambiente.")
        sys.exit(1)

    # ── Resolver range de datas ───────────────────────────────────────────────
    date_range = None
    if args.date_from or args.date_to:
        if args.weekly or args.month:
            print("❌  --from/--to não pode ser combinado com --weekly ou --month.")
            sys.exit(1)
        if not (args.date_from and args.date_to):
            print("❌  --from e --to devem ser usados juntos.")
            sys.exit(1)
        try:
            d_from = date.fromisoformat(args.date_from)
            d_to   = date.fromisoformat(args.date_to)
        except ValueError as exc:
            print(f"❌  Data inválida: {exc}. Use o formato YYYY-MM-DD.")
            sys.exit(1)
        if d_from > d_to:
            print(f"❌  --from ({d_from}) não pode ser posterior a --to ({d_to}).")
            sys.exit(1)
        from auditor import _day_range
        date_range = (_day_range(d_from)[0], _day_range(d_to)[1])

    # ── Banner inicial ────────────────────────────────────────────────────────
    if date_range:
        mode_label = (
            f"📅 Range: {date_range[0].strftime('%d/%m/%Y')} → "
            f"{date_range[1].strftime('%d/%m/%Y')}"
        )
    elif args.weekly:
        mode_label = "📅 Semanal (últimos 5 dias úteis)"
    elif args.month:
        mode_label = "📆 Mensal (últimos 30 dias úteis)"
    else:
        mode_label = "📅 Último dia útil"

    if HAS_RICH:
        squads_line = (
            "\n[bold]Squads:[/bold] " + ", ".join(
                f"{name} ({len(members)})" for name, members in squads.items()
            )
            if squads else ""
        )
        console.print(Panel(
            f"[bold]Usuários:[/bold] {', '.join(users)}\n"
            f"[bold]Organizações:[/bold] {', '.join(orgs) if orgs else 'todas'}"
            f"{squads_line}\n"
            f"[bold]Modo:[/bold] {mode_label}\n"
            f"[bold]Contagem de arquivos:[/bold] {'sim' if count_files else 'não (--no-files)'}",
            title="[bold cyan]🔍 ghaudit — Iniciando auditoria[/bold cyan]",
            border_style="cyan",
        ))

        console.print(Panel(
            "  [cyan bold]PR aberto[/cyan bold]            [white]+10 pts[/white]   [dim]→ início de entrega[/dim]\n"
            "  [cyan bold]Commit[/cyan bold]               [white] +2 pts[/white]   [dim]→ progresso incremental[/dim]\n"
            "  [cyan bold]Review realizado[/cyan bold]     [white] +8 pts[/white]   [dim]→ desbloqueio de colegas[/dim]\n"
            "  [cyan bold]Comentário em review[/cyan bold] [white] +3 pts[/white]   [dim]→ qualidade da revisão[/dim]\n"
            "  [cyan bold]Arquivo alterado[/cyan bold]     [white]+0.5 pts[/white]  [dim]→ limitado a 15 pts (evita ruído de refactors)[/dim]\n"
            "\n"
            "  [green]● SCI ≥ 25[/green]  Alta Produtividade   "
            "[yellow]● SCI 10–24[/yellow]  Normal   "
            "[red]● SCI < 10[/red]  Baixa Atividade",
            title="[bold]📐 Regras de Pontuação (SCI)[/bold]",
            border_style="dim",
        ))
    else:
        print(f"\nghaudit — auditando {len(users)} usuário(s)... ({mode_label})")
        print("\nRegras SCI: PR +10 | Commit +2 | Review +8 | Comentário +3 | Arquivo +0.5 (max 15)")

    # ── Cache ─────────────────────────────────────────────────────────────────
    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    cache = AuditCache(db_path)

    if args.force and HAS_RICH:
        console.print("[dim]⚡ --force: ignorando cache, buscando dados frescos...[/dim]")

    # ── Executar auditoria (com barra de progresso quando disponível) ─────────
    try:
        if HAS_RICH and not args.debug:
            progress_callback = None
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                task_id = progress.add_task(
                    f"Auditando {len(users)} usuário(s)...",
                    total=len(users),
                )

                def _on_complete(username: str) -> None:
                    progress.advance(task_id)
                    remaining = len(users) - progress.tasks[task_id].completed
                    if remaining > 0:
                        progress.update(task_id, description=f"✓ {username} — aguardando {remaining} restante(s)...")
                    else:
                        progress.update(task_id, description="✓ Todos os usuários concluídos")

                results, date_start, date_end = audit_users(
                    users=users,
                    token=token,
                    orgs=orgs,
                    count_files=count_files,
                    weekly=args.weekly,
                    monthly=args.month,
                    date_range=date_range,
                    max_workers=args.max_workers,
                    cache=cache,
                    force=args.force,
                    progress_callback=_on_complete,
                )
        else:
            results, date_start, date_end = audit_users(
                users=users,
                token=token,
                orgs=orgs,
                count_files=count_files,
                weekly=args.weekly,
                monthly=args.month,
                date_range=date_range,
                max_workers=args.max_workers,
                cache=cache,
                force=args.force,
            )
    except Exception as exc:
        msg = f"❌  Falha na auditoria: {exc}"
        if HAS_RICH:
            console.print(f"[bold red]{msg}[/bold red]")
        else:
            print(msg)
        cache.close()
        sys.exit(1)

    # ── Montar título da tabela ───────────────────────────────────────────────
    if args.weekly or args.month or date_range:
        title = (
            f"{'Semanal' if args.weekly else 'Mensal' if args.month else 'Range'}: "
            f"{date_start.strftime('%d/%m/%Y')} → {date_end.strftime('%d/%m/%Y')}"
        )
    else:
        weekday_en = date_start.strftime("%A")
        weekday_pt = WEEKDAYS_PT.get(weekday_en, weekday_en)
        title = f"{date_start.strftime('%d/%m/%Y')} ({weekday_pt})"

    # ── Exibir tabela ─────────────────────────────────────────────────────────
    cache_hits = sum(1 for r in results if r.get("from_cache"))
    if HAS_RICH:
        render_table_rich(results, title, count_files, cache_hits=cache_hits, squads=squads)
    else:
        render_table_plain(results, title, count_files, squads=squads)

    # ── Exportar CSV (opcional) ───────────────────────────────────────────────
    if args.csv:
        try:
            export_csv(results, args.csv)
            msg = f"✅  CSV exportado: {args.csv}"
            if HAS_RICH:
                console.print(f"[green]{msg}[/green]\n")
            else:
                print(msg)
        except Exception as exc:
            msg = f"❌  Erro ao exportar CSV: {exc}"
            if HAS_RICH:
                console.print(f"[red]{msg}[/red]")
            else:
                print(msg)

    cache.close()


if __name__ == "__main__":
    main()
