# =============================================================================
# CONFIGURAÇÕES via variáveis de ambiente
# =============================================================================
# Crie um arquivo .env (não commitar) e exporte as variáveis antes de usar:
#
#   export GITHUB_TOKEN="ghp_seu_token_aqui"
#   export GITHUB_USERS="user1,user2,user3"
#   export GITHUB_ORGS="OrgA,OrgB"          # opcional; vazio = todas as orgs
#
# Ou copie .env.example → .env e preencha os valores.
# =============================================================================

import os
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()


def _parse_list(env_var: str) -> List[str]:
    """Lê uma variável de ambiente com lista separada por vírgulas."""
    raw = os.environ.get(env_var, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_squads() -> Dict[str, List[str]]:
    """
    Lê variáveis SQUAD_<NOME>=user1,user2 e retorna {nome: [users]}.

    Exemplo:
        SQUAD_BACKEND=alice,bob
        SQUAD_FRONTEND=carol,dave
    A ordem de inserção é preservada (Python 3.7+).
    """
    squads: Dict[str, List[str]] = {}
    for key in sorted(os.environ):
        if key.startswith("SQUAD_") and len(key) > 6:
            name = key[6:]  # remove prefixo "SQUAD_"
            users = [u.strip() for u in os.environ[key].split(",") if u.strip()]
            if users:
                squads[name] = users
    return squads


# Token de acesso pessoal do GitHub
# Permissões necessárias: repo, read:user, read:org
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Usuários a auditar (separados por vírgula na env var)
GITHUB_USERS = _parse_list("GITHUB_USERS")

# Organizações a filtrar (separadas por vírgula; vazio = sem filtro)
GITHUB_ORGS = _parse_list("GITHUB_ORGS")

# Squads: dict {nome_squad: [usuarios]}  — lido de SQUAD_* env vars
GITHUB_SQUADS: Dict[str, List[str]] = _parse_squads()
