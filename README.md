# ghaudit — GitHub Activity Auditor

CLI em Python para auditar a atividade de desenvolvedores no GitHub. Gera relatórios com o **Score de Colaboração e Impacto (SCI)**, separados por squad, com cache local e barra de progresso.

---

## Pré-requisitos

- Python 3.8+
- Token de acesso pessoal do GitHub com permissões: `repo`, `read:user`, `read:org`
- O token precisa estar **autorizado via SSO** para cada organização privada (GitHub → Settings → Tokens → Authorize)

---

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
# edite .env com seu token e usuários
```

---

## Configuração (`.env`)

Todas as configurações são feitas via variáveis de ambiente. Copie `.env.example` e ajuste:

```env
# Token do GitHub (obrigatório)
GITHUB_TOKEN=ghp_seu_token_aqui

# Organizações a filtrar, separadas por vírgula
GITHUB_ORGS=MinhaOrg,OutraOrg

# Squads: uma variável SQUAD_<NOME> por equipe
SQUAD_BACKEND=alice,bob,carol
SQUAD_MOBILE=dave,eve
# Quando SQUAD_* estiver definido, GITHUB_USERS é ignorado

# Usuários avulsos (sem squads)
GITHUB_USERS=user1,user2,user3
```

### Variáveis disponíveis

| Variável | Descrição | Obrigatório |
|---|---|---|
| `GITHUB_TOKEN` | Token de acesso pessoal | ✅ Sim |
| `GITHUB_ORGS` | Organizações a filtrar (vírgula) | Recomendado |
| `GITHUB_USERS` | Usuários a auditar (vírgula) | Se não usar squads |
| `SQUAD_<NOME>` | Usuários de uma squad (vírgula) | Alternativa a GITHUB_USERS |

---

## Uso

```bash
python ghaudit.py [OPÇÕES]
```

### Modos de período

```bash
# Último dia útil (padrão)
python ghaudit.py

# Últimos 5 dias úteis
python ghaudit.py --weekly

# Últimos 30 dias úteis
python ghaudit.py --month

# Range explícito de datas
python ghaudit.py --from 2026-03-01 --to 2026-03-18
```

### Todos os parâmetros

| Parâmetro | Atalho | Descrição |
|---|---|---|
| `--from YYYY-MM-DD` | — | Início do range de datas |
| `--to YYYY-MM-DD` | — | Fim do range de datas |
| `--weekly` | `-w` | Últimos 5 dias úteis |
| `--month` | `-m` | Últimos 30 dias úteis |
| `--users USER ...` | `-u` | Sobrescreve usuários do `.env` |
| `--orgs ORG ...` | `-o` | Sobrescreve organizações do `.env` |
| `--token TOKEN` | `-t` | Sobrescreve `GITHUB_TOKEN` |
| `--no-files` | — | Não busca stats de arquivos (mais rápido) |
| `--csv ARQUIVO` | — | Exporta resultado para CSV |
| `--force` | `-f` | Ignora o cache e re-busca da API |
| `--db CAMINHO` | — | Banco SQLite alternativo (padrão: `~/.ghaudit/cache.db`) |
| `--verbose` | `-v` | Exibe logs de progresso por usuário |
| `--debug` | — | Exibe logs detalhados (queries, rate limit) |
| `--max-workers N` | — | Usuários em paralelo (padrão: 5). Reduza para evitar rate limit com `--force` |

### Exemplos práticos

```bash
# Relatório mensal com squads (configuradas no .env)
python ghaudit.py --month

# Semana de um grupo específico
python ghaudit.py --weekly --users alice bob carol

# Range personalizado, forçando re-busca
python ghaudit.py --from 2026-02-01 --to 2026-02-28 --force

# Exportar mensal para CSV sem contar arquivos
python ghaudit.py --month --no-files --csv fevereiro.csv

# Debug de uma consulta específica
python ghaudit.py --from 2026-03-10 --to 2026-03-18 --users alice --debug
```

---

## Cache

Os resultados são armazenados em `~/.ghaudit/cache.db` (SQLite). Na segunda execução com os mesmos parâmetros, os dados vêm do cache instantaneamente — sem consumir rate limit da API.

```bash
# Re-busca tudo da API e atualiza o cache
python ghaudit.py --month --force

# Usar banco em outro local (ex.: compartilhado em equipe)
python ghaudit.py --month --db /shared/ghaudit.db
```

O painel de resumo exibe `💾 Cache: N/M` quando há hits.

---

## Squads

Quando variáveis `SQUAD_*` estão definidas no `.env`, o relatório exibe **uma tabela separada por squad**:

```env
SQUAD_BACKEND=renatoguedes,fams-dev,gsb6
SQUAD_MOBILE=KaioMaia,MarceloAzevedo
```

- A ordem das squads no relatório é **alfabética** pelo nome da variável
- O 🏆 marca o **MVP de cada squad** (maior SCI dentro da squad)
- O 👑 marca o **MVP geral** (maior SCI entre todos os usuários)
- Usuários não pertencentes a nenhuma squad são exibidos em um grupo "Outros"
- `GITHUB_USERS` é ignorado quando squads estão configuradas

---

## Tabela de resultados

| Coluna | Descrição |
|---|---|
| **Usuário** | Login do GitHub (👑 MVP geral, 🏆 MVP da squad) |
| **Commits** | Commits feitos no período (Search API `author-date:`) |
| **PRs** | Pull Requests abertos no período |
| **Reviews** | PRs revisados (`reviewed-by:` Search API) |
| **Coments.** | PRs alheios comentados (`commenter:` Search API) |
| **Arquivos** | Arquivos únicos alterados |
| **+Adds/-Dels** | Linhas adicionadas e removidas |
| **SCI** | Score de Colaboração e Impacto |
| **Perfil** | Emoji + classificação de comportamento |
| **Insights** | Alertas e destaques individuais |

---

## Score de Colaboração e Impacto (SCI)

```
SCI = (PRs × 10) + (Commits × 2) + (Reviews × 8) + (Comentários × 3) + min(Arquivos × 0.5, 15)
```

| Cor | SCI | Interpretação |
|---|---|---|
| 🟢 Verde | ≥ 25 | Alta Produtividade |
| 🟡 Amarelo | 10–24 | Atividade Normal |
| 🔴 Vermelho | < 10 | Baixa Atividade |

---

## Perfis de comportamento

| Perfil | Condição |
|---|---|
| 😶 Bloqueado | Atividade total = 0 |
| 🔧 Refatorador | Arquivos > 20 e PRs = 1 |
| 🔎 O Revisor | Reviews > 3 e Commits < 2 |
| 🔨 Construtor | Commits > 5 ou PRs ≥ 2 |
| 🤝 Colaborativo | PRs ≥ 1 e Reviews ≥ 2 |
| ⚡ Ativo | Demais casos com atividade |

---

## Insights individuais

| Insight | Condição |
|---|---|
| 🔥 Alta Entrega | SCI > 30 |
| ⚠️ Gargalo de Review | PRs > 0 e Reviews = 0 |
| 📦 PR Gigante (risco) | Arquivos alterados > 50 |

---

## Como os dados são coletados

| Métrica | Fonte | Observação |
|---|---|---|
| Commits | Search API (`author-date:`) | Usa data de autoria, não de merge |
| PRs | Search API (`is:pr author: created:`) | PRs criados no período |
| Reviews | Search API (`reviewed-by: updated:`) | PRs distintos revisados |
| Comentários | Search API (`commenter: -author: updated:`) | PRs alheios comentados |
| Arquivos/Stats | Commits Detail API | 1 chamada por commit; desative com `--no-files` |

> **Nota sobre a Events API**: reviews e comentários usam a Search API em vez da Events API porque esta última não retorna eventos de repositórios privados quando o token pertence a outro usuário.

---

## Rate Limit

A aplicação respeita automaticamente os limites da API do GitHub:

- **Retry automático** em respostas `429` (rate limit secundário) e `403` com `X-RateLimit-Remaining: 0`
- **Execução paralela** com até 5 usuários simultâneos (cada thread usa sua própria sessão HTTP)
- **Cache SQLite** evita re-consultas para períodos já processados

---

## Testes

```bash
pytest tests/
```

Cobertura inclui: `sci.py`, `auditor.py`, `github_client.py`, `ghaudit.py`, `config.py`.

---

## Estrutura do projeto

```
ghaudit/
├── ghaudit.py        # CLI — entry point, render, argumentos
├── auditor.py        # Orquestração paralela, cálculo do SCI
├── github_client.py  # Client da API GitHub (Search, Commits, Reviews)
├── sci.py            # Fórmula SCI, perfis, insights
├── cache.py          # Cache SQLite thread-safe
├── config.py         # Leitura de env vars e squads
├── requirements.txt  # Dependências Python
├── .env.example      # Template de configuração
├── .gitignore
├── tests/
│   ├── conftest.py
│   ├── test_sci.py
│   ├── test_auditor.py
│   ├── test_github_client.py
│   └── test_ghaudit.py
└── README.md
```
