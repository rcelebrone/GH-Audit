#!/usr/bin/env python3
"""
ghaudit — GitHub Activity Auditor

CLI para auditar a atividade diária (ou semanal) de desenvolvedores
dentro de uma organização do GitHub.

Uso:
    python3 ghaudit.py [OPÇÕES]

Exemplos:
    # Auditoria diária padrão (dia anterior)
    python3 ghaudit.py

    # Auditoria semanal (últimos 5 dias úteis)
    python3 ghaudit.py --weekly

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
import sys
from datetime import date
from typing import Dict, List, Optional

# Rich para output colorido no terminal
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from config import GITHUB_TOKEN, GITHUB_USERS, GITHUB_ORG
from auditor import audit_users

console = Console() if HAS_RICH else None

# ── Helpers de display ────────────────────────────────────────────────────────

SCI_COLORS = {
    "green":  ("green",  "Alta Produtividade"),
    "yellow": ("yellow", "Atividade Normal"),
    "red":    ("red",    "Baixa Atividade"),
}

WEEKDAYS_PT = {
    "Monday":    "Segunda",
    "Tuesday":   "Terça",
    "Wednesday": "Quarta",
    "Thursday":  "Quinta",
    "Friday":    "Sexta",
    "Saturday":  "Sábado",
    "Sunday":    "Domingo",
}


def _pt_weekday(dt_str: str) -> str:
    """Converte '%d/%m/%Y (%A)' usando dias em português."""
    from datetime import datetime
    dt = datetime.strptime(dt_str, "%d/%m/%Y (%A)")
    weekday_en = dt.strftime("%A")
    return f"{dt.strftime('%d/%m/%Y')} ({WEEKDAYS_PT.get(weekday_en, weekday_en)})"


def _lines_str_rich(adds: int, dels: int, count_files: bool) -> str:
    if not count_files:
        return "[dim]—[/dim]"
    return f"[green]+{adds}[/green] [red]-{dels}[/red]"


def _sci_rich(sci: float, level: str) -> str:
    color = level  # level já é o nome da cor Rich
    return f"[{color} bold]{sci:.1f}[/{color} bold]"


def _username_rich(username: str, is_mvp: bool) -> str:
    if is_mvp:
        return f"[bold gold1]👑 {username}[/bold gold1]"
    return f"[white]{username}[/white]"


# ── Render Rich ───────────────────────────────────────────────────────────────

def render_table_rich(
    results: List[Dict],
    title: str,
    count_files: bool,
) -> None:
    """Exibe a tabela completa com Rich (colorida, com SCI e perfil)."""

    table = Table(
        title=f"[bold cyan]📊 ghaudit — {title}[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
        show_lines=True,
        expand=True,
    )

    table.add_column("#",           style="dim",        width=3,  justify="right")
    table.add_column("Usuário",                         min_width=16)
    table.add_column("Commits",     justify="center",   width=9)
    table.add_column("PRs",         justify="center",   width=5)
    table.add_column("Reviews",     justify="center",   width=9)
    table.add_column("Coments.",    justify="center",   width=10)
    table.add_column("Arquivos",    justify="center",   width=9)
    table.add_column("+Adds/-Dels", justify="center",   width=14)
    table.add_column("SCI",         justify="center",   width=8)
    table.add_column("Perfil",                          min_width=18)
    table.add_column("Insights",                        min_width=22)

    for i, row in enumerate(results, start=1):
        erro = row.get("erro") or ""

        # SCI
        sci_str = _sci_rich(row["sci"], row["sci_level"])

        # Nome + MVP
        name_str = _username_rich(row["usuario"], row.get("is_mvp", False))

        # Perfil
        profile_str = f"{row['profile_emoji']} {row['profile_tag']}"

        # Insights
        insights_list = row.get("insights", [])
        if erro:
            insights_str = f"[red dim]{erro[:45]}[/red dim]"
        else:
            insights_str = "  ".join(insights_list) if insights_list else "[dim]—[/dim]"

        # +/- linhas
        lines_str = _lines_str_rich(
            row["additions"], row["deletions"], count_files
        )

        table.add_row(
            str(i),
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

    console.print()
    console.print(table)

    # ── Legenda de SCI ────────────────────────────────────────────────────────
    console.print(
        "  [green]●[/green] SCI ≥ 25 Alta Produtividade   "
        "[yellow]●[/yellow] SCI 10-24 Normal   "
        "[red]●[/red] SCI < 10 Baixa Atividade"
    )
    console.print()

    # ── Resumo ────────────────────────────────────────────────────────────────
    total   = len(results)
    errors  = sum(1 for r in results if r.get("erro"))
    high    = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "green")
    medium  = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "yellow")
    low     = sum(1 for r in results if not r.get("erro") and r["sci_level"] == "red")

    mvp_row = next((r for r in results if r.get("is_mvp")), None)
    mvp_line = (
        f"   [bold gold1]👑 MVP do dia: {mvp_row['usuario']} "
        f"(SCI {mvp_row['sci']:.1f})[/bold gold1]"
        if mvp_row else ""
    )

    console.print(Panel(
        f"[bold]Total:[/bold] {total}   "
        f"[green bold]Alta: {high}[/green bold]   "
        f"[yellow]Normal: {medium}[/yellow]   "
        f"[red]Baixa: {low}[/red]   "
        f"[red dim]Erros: {errors}[/red dim]"
        f"{mvp_line}",
        title="[bold]Resumo",
        border_style="cyan",
    ))
    console.print()


# ── Render plain (fallback sem Rich) ─────────────────────────────────────────

def render_table_plain(
    results: List[Dict],
    title: str,
    count_files: bool,
) -> None:
    """Exibe a tabela em texto puro (sem Rich)."""
    print(f"\n{'='*70}")
    print(f"  ghaudit — {title}")
    print(f"{'='*70}")

    headers = ["Usuário", "Cmts", "PRs", "Revs", "Comnts", "Arqs", "SCI", "Perfil"]
    widths  = [    18,     5,     4,     5,      6,       5,     7,      20  ]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {h:<{widths[i]}} " for i, h in enumerate(headers)) + "|"
    print(sep)
    print(hdr)
    print(sep)

    for row in results:
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
        line = "|" + "|".join(
            f" {v:<{widths[i]}} " for i, v in enumerate(vals)
        ) + "|"
        print(line)

    print(sep)

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
        description="Audita a atividade diária ou semanal de devs no GitHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--date", "-d",
        type=str, default=None, metavar="YYYY-MM-DD",
        help=(
            "Data de referência para calcular o dia anterior. "
            "Padrão: hoje. Se for segunda, audita a sexta anterior."
        ),
    )
    parser.add_argument(
        "--weekly", "-w",
        action="store_true", default=False,
        help="Audita os últimos 5 dias úteis (visão semanal de produtividade).",
    )
    parser.add_argument(
        "--users", "-u",
        nargs="+", default=None, metavar="USUARIO",
        help="Lista de usuários. Sobrescreve GITHUB_USERS do config.py.",
    )
    parser.add_argument(
        "--org", "-o",
        type=str, default=None, metavar="ORG",
        help="Organização GitHub. Sobrescreve GITHUB_ORG do config.py.",
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

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Resolver configurações (CLI sobrescreve config.py) ────────────────────
    token      = args.token or GITHUB_TOKEN
    users      = args.users or GITHUB_USERS
    org        = args.org   or GITHUB_ORG
    count_files = not args.no_files

    # ── Validações ────────────────────────────────────────────────────────────
    if not token:
        print("❌  Token do GitHub não configurado.")
        print("    Configure GITHUB_TOKEN em config.py ou use --token <TOKEN>")
        sys.exit(1)

    if not users:
        print("❌  Nenhum usuário informado.")
        print("    Configure GITHUB_USERS em config.py ou use --users <u1> <u2> ...")
        sys.exit(1)

    # ── Parsear data de referência ────────────────────────────────────────────
    reference_date = None
    if args.date:
        try:
            reference_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"❌  Data inválida '{args.date}'. Use o formato YYYY-MM-DD.")
            sys.exit(1)

    # ── Banner inicial ────────────────────────────────────────────────────────
    mode_label = "🗓️  Semanal (últimos 5 dias úteis)" if args.weekly else "📅 Diário (dia anterior)"
    if HAS_RICH:
        console.print(Panel(
            f"[bold]Usuários:[/bold] {', '.join(users)}\n"
            f"[bold]Organização:[/bold] {org or 'todas'}\n"
            f"[bold]Modo:[/bold] {mode_label}\n"
            f"[bold]Contagem de arquivos:[/bold] {'sim' if count_files else 'não (--no-files)'}",
            title="[bold cyan]🔍 ghaudit — Iniciando auditoria[/bold cyan]",
            border_style="cyan",
        ))

        # ── Regras de pontuação (SCI) ─────────────────────────────────────────
        console.print(Panel(
            "  [cyan bold]PR aberto[/cyan bold]          [white]+10 pts[/white]   [dim]→ início de entrega[/dim]\n"
            "  [cyan bold]Commit[/cyan bold]             [white] +2 pts[/white]   [dim]→ progresso incremental[/dim]\n"
            "  [cyan bold]Review realizado[/cyan bold]   [white] +8 pts[/white]   [dim]→ desbloqueio de colegas[/dim]\n"
            "  [cyan bold]Comentário em review[/cyan bold] [white]+3 pts[/white]   [dim]→ qualidade da revisão[/dim]\n"
            "  [cyan bold]Arquivo alterado[/cyan bold]   [white]+0.5 pts[/white]  [dim]→ limitado a 15 pts (evita ruído de refactors)[/dim]\n"
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

    # ── Executar auditoria ────────────────────────────────────────────────────
    try:
        results, date_start, date_end = audit_users(
            users=users,
            token=token,
            org=org,
            reference_date=reference_date,
            count_files=count_files,
            weekly=args.weekly,
        )
    except Exception as exc:
        msg = f"❌  Falha na auditoria: {exc}"
        if HAS_RICH:
            console.print(f"[bold red]{msg}[/bold red]")
        else:
            print(msg)
        sys.exit(1)

    # ── Montar título da tabela ───────────────────────────────────────────────
    if args.weekly:
        title = (
            f"Semanal: {date_start.strftime('%d/%m/%Y')} "
            f"→ {date_end.strftime('%d/%m/%Y')}"
        )
    else:
        weekday_en = date_start.strftime("%A")
        weekday_pt = WEEKDAYS_PT.get(weekday_en, weekday_en)
        title = f"{date_start.strftime('%d/%m/%Y')} ({weekday_pt})"

    # ── Exibir tabela ─────────────────────────────────────────────────────────
    if HAS_RICH:
        render_table_rich(results, title, count_files)
    else:
        render_table_plain(results, title, count_files)

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


if __name__ == "__main__":
    main()
