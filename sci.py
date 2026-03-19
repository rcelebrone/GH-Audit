"""
Score de Colaboração e Impacto (SCI) — cálculo e classificação de perfil.

Fórmula:
    SCI = (PRs × 10) + (Commits × 2) + (Reviews × 8)
            + (Comments × 3) + min(Files × 0.5, 15)
"""
from typing import List, Tuple

# ── Pesos ──────────────────────────────────────────────────────────────────────
W_PR      = 10    # PR Aberto        → indica início de entrega
W_COMMIT  =  2    # Commit           → progresso incremental
W_REVIEW  =  8    # Review realizado → desbloqueio de colegas
W_COMMENT =  3    # Comentário       → qualidade da revisão
W_FILE    =  0.5  # Arquivo alterado → limitado para evitar ruído de refactors
FILE_CAP  = 15.0  # Teto de pontos por arquivos


def calculate_sci(
    commits: int,
    prs: int,
    reviews: int,
    comments: int,
    files: int,
) -> float:
    """Calcula o Score de Colaboração e Impacto (SCI)."""
    file_score = min(files * W_FILE, FILE_CAP)
    return (
        (prs * W_PR)
        + (commits * W_COMMIT)
        + (reviews * W_REVIEW)
        + (comments * W_COMMENT)
        + file_score
    )


def get_profile(
    commits: int,
    prs: int,
    reviews: int,
    files: int,
) -> Tuple[str, str]:
    """
    Classifica o desenvolvedor e retorna (emoji, label).

    Ordem de prioridade das regras:
    1. Sem atividade alguma          → Bloqueado
    2. Muitos arquivos, poucos PRs   → Refatorador
    3. Muitos reviews, poucos commits→ O Revisor
    4. Muitos commits ou vários PRs  → Construtor
    5. Equilíbrio PR + Reviews       → Colaborativo
    6. Qualquer outra atividade      → Ativo
    """
    total = commits + prs + reviews + files

    if total == 0:
        return "😶", "Bloqueado"

    if files > 20 and prs == 1:
        return "🔧", "Refatorador"

    if reviews > 3 and commits < 2:
        return "🔎", "O Revisor"

    if commits > 5 or prs >= 2:
        return "🔨", "Construtor"

    if prs >= 1 and reviews >= 2:
        return "🤝", "Colaborativo"

    return "⚡", "Ativo"


def sci_color(sci: float) -> str:
    """
    Retorna o nome da cor Rich de acordo com o nível de SCI.
    Verde ≥ 25  /  Amarelo 10-24  /  Vermelho < 10
    """
    if sci >= 25:
        return "green"
    if sci >= 10:
        return "yellow"
    return "red"


def get_insights(
    sci: float,
    prs: int,
    reviews: int,
    files: int,
) -> List[str]:
    """Retorna lista de observações/alertas individuais."""
    notes: List[str] = []

    if sci > 30:
        notes.append("🔥 Alta Entrega")

    if prs > 0 and reviews == 0:
        notes.append("⚠️ Gargalo de Review")

    if files > 50:
        notes.append("📦 PR Gigante (risco)")

    return notes
