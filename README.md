# 📊 ghaudit — GitHub Activity Auditor

CLI em Python para auditar a atividade diária (ou semanal) de desenvolvedores dentro de uma organização do GitHub. Exibe uma tabela rica no terminal com **Score de Colaboração e Impacto (SCI)**, perfil de comportamento, insights individuais e destaque do MVP do dia.

---

## ✅ Pré-requisitos

- Python 3.8 ou superior
- Token do GitHub com permissões: `repo`, `read:user`, `read:org`

---

## 🚀 Instalação

```bash
cd /home/rcelebrone/ghaudit

pip install -r requirements.txt
```

---

## ⚙️ Configuração (`config.py`)

| Variável | Descrição | Obrigatório |
|---|---|---|
| `GITHUB_TOKEN` | Token de acesso pessoal do GitHub | ✅ Sim |
| `GITHUB_USERS` | Lista de usuários GitHub a auditar | ✅ Sim |
| `GITHUB_ORG` | Organização para filtrar os dados | ❌ Opcional |

```python
# config.py
GITHUB_TOKEN = "ghp_seu_token_aqui"

GITHUB_USERS = [
    "rcelebrone",
    "user",
    "user-2",
    "user-3",
    "user-4",
    "user-5",
]

GITHUB_ORG = None
```

---

## 🖥️ Uso

### Comando padrão (time completo, dia anterior)

```bash
python3 ghaudit.py
```

> ⚠️ Se hoje for **segunda-feira**, o dia auditado será automaticamente a **sexta-feira** anterior.

### Auditoria semanal (últimos 5 dias úteis)

```bash
python3 ghaudit.py --weekly
```

---

## 📋 Parâmetros disponíveis

| Parâmetro | Atalho | Descrição |
|---|---|---|
| `--date YYYY-MM-DD` | `-d` | Data de referência. O dia auditado será o **anterior** a essa data |
| `--weekly` | `-w` | Audita os **últimos 5 dias úteis** (visão de semana completa) |
| `--users USER ...` | `-u` | Usuários a auditar. Sobrescreve `GITHUB_USERS` |
| `--org ORG` | `-o` | Organização GitHub. Sobrescreve `GITHUB_ORG` |
| `--csv ARQUIVO.csv` | — | Exporta resultado para CSV |
| `--no-files` | — | Não conta arquivos/additions/deletions (mais rápido) |
| `--token TOKEN` | `-t` | Token GitHub. Sobrescreve `GITHUB_TOKEN` |

---

## 💡 Exemplos

```bash
# Auditoria padrão do time (dia anterior)
python3 ghaudit.py

# Auditoria semanal
python3 ghaudit.py --weekly

# Data específica (audita o dia 14/03/2025)
python3 ghaudit.py --date 2025-03-15

# Apenas alguns usuários
python3 ghaudit.py --users rcelebrone user1 user2

# Exportar CSV
python3 ghaudit.py --csv relatorio.csv

# Mais rápido (sem arquivos)
python3 ghaudit.py --no-files

# Combinado
python3 ghaudit.py --weekly --csv semana.csv --no-files
```

---

## 📊 Colunas da tabela

| Coluna | Descrição |
|---|---|
| **Usuário** | Login do GitHub (👑 para o MVP do dia) |
| **Commits** | Commits feitos no período |
| **PRs** | Pull Requests abertos |
| **Reviews** | PRs revisados |
| **Coments.** | Comentários feitos em reviews (via Events API) |
| **Arquivos** | Arquivos únicos alterados |
| **+Adds/-Dels** | Linhas adicionadas e removidas |
| **SCI** | Score de Colaboração e Impacto (colorido) |
| **Perfil** | Emoji + classificação de comportamento |
| **Insights** | Alertas e destaques individuais |

---

## 🧮 Score de Colaboração e Impacto (SCI)

```
SCI = (PRs × 10) + (Commits × 2) + (Reviews × 8) + (Comentários × 3) + min(Arquivos × 0.5, 15)
```

| Cor | SCI | Interpretação |
|---|---|---|
| 🟢 Verde | ≥ 25 | Alta Produtividade / Colaboração |
| 🟡 Amarelo | 10 – 24 | Atividade Normal |
| 🔴 Vermelho | < 10 | Baixa Atividade |

---

## 🏷️ Classificação de Perfil

| Perfil | Condição |
|---|---|
| 😶 Bloqueado/Reunião | Atividade total = 0 |
| 🔧 Refatorador | Arquivos > 20 e PRs = 1 |
| 🔎 O Revisor | Reviews > 3 e Commits < 2 |
| 🏗️ O Construtor | Commits > 5 ou PRs ≥ 2 |
| 🤝 Colaborativo | PRs ≥ 1 e Reviews ≥ 2 |
| ⚡ Ativo | Demais casos com atividade |

---

## 💬 Insights Individuais

| Insight | Condição |
|---|---|
| 🔥 Alta Entrega | SCI > 30 |
| ⚠️ Gargalo de Review | PRs > 0 e Reviews = 0 |
| 📦 PR Gigante (risco) | Arquivos alterados > 50 |

---

## 🗓️ Regra do dia anterior

| Hoje | Dia auditado |
|---|---|
| Segunda-feira | Sexta-feira (3 dias antes) |
| Terça a Sábado | Dia imediatamente anterior |

---

## 📁 Estrutura do projeto

```
ghaudit/
├── ghaudit.py        # 🚀 Ponto de entrada do CLI
├── auditor.py        # Orquestra chamadas e monta o relatório
├── github_client.py  # Client da API GitHub
├── sci.py            # Fórmula SCI e classificação de perfil
├── config.py         # ⚙️ Configurações (edite aqui)
├── requirements.txt  # Dependências Python
└── README.md
```

---

## ⚡ Dica de performance

O parâmetro `--no-files` evita uma chamada à API por commit, tornando a execução muito mais rápida. Recomendado quando há muitos commits ou usuários:

```bash
python3 ghaudit.py --no-files
```
