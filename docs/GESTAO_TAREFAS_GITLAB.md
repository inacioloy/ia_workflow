# Gestão de Tarefas no GitLab (`iaw create` e `iaw relatorio tasks`)

> Guia de uso dos comandos de **criação** e **relatório** de work items
> (Tasks/Issues) do `iaw` no GitLab. Complementa o [README](../README.md) e o
> [Guia do Desenvolvedor](GUIA_DESENVOLVEDOR.md).

---

## 1. Conceitos

O `iaw` trata o trabalho como **work items** do GitLab, que podem ser de dois tipos:

| Tipo | Comando | Uso típico |
|------|---------|-----------|
| **Task** | `iaw create --task` | Tarefa de desenvolvimento em geral |
| **Issue** | `iaw create --issue` | Bug/erro a corrigir |

Cada work item recebe **labels** que permitem classificar o trabalho depois:

| Label | Quando é aplicado | Categoria no relatório |
|-------|-------------------|------------------------|
| `SET/2026` (mês/ano) | **Sempre** — em todo work item criado | — (filtro do mês) |
| `demandas` | Task criada com `--demanda` | **demanda** |
| `bug` | Issue criada com `--issue` | **erro** |
| *(nenhum label extra)* | Task criada só com `--task` | **task geral** |

> O label do mês segue o formato abreviado em português: `JAN`, `FEV`, `MAR`,
> `ABR`, `MAI`, `JUN`, `JUL`, `AGO`, `SET`, `OUT`, `NOV`, `DEZ` + `/ano`.
> Exemplo: **`SET/2026`**.

---

## 2. Pré-requisitos

Antes de usar, configure as credenciais do GitLab:

```bash
iaw setup
```

O assistente pergunta o **token** (Personal Access Token), a **URL do GitLab** e
o **projeto padrão**. Para o projeto `suap`, informe o path completo do projeto
(por exemplo `cosinf/suap` ou apenas `suap`, conforme o seu GitLab).

Também dá para configurar direto:

```bash
iaw config set gitlab_url https://gitlab.com
iaw config set gitlab_token <seu_token>
iaw config set gitlab_project suap
```

O token precisa ter permissão `api` (ou `write_repository` + `write_issues`).

---

## 3. Criando work items (`iaw create`)

### 3.1 Sintaxe

```bash
iaw create (--task | --issue) [--demanda] [--title <título>] [--project-id <path>]
```

| Opção | Descrição |
|-------|-----------|
| `--task` | Cria uma **Task** (obrigatório escolher entre `--task` e `--issue`). |
| `--issue` | Cria uma **Issue** (erro/bug). |
| `--demanda` | Só com `--task`: adiciona o label `demandas` (task de demanda). |
| `--title <t>` | Título do work item. Se omitido, o `iaw` **pergunta** o título. |
| `--project-id <path>` | Sobrescreve o projeto padrão (ex.: `cosinf/suap`). |

O work item é criado com **assignee = seu usuário** (o usuário autenticado do
token) e já recebe o **label do mês atual**.

### 3.2 Exemplos

```bash
# Task geral (sem label extra além do mês)
iaw create --task --title "Corrigir N+1 na listagem de diários"

# Task de demanda (label demandas + mês)
iaw create --task --demanda --title "Nova tela de relatórios gerenciais"

# Issue/erro (label bug + mês)
iaw create --issue --title "Erro 500 ao salvar boletim"

# Sem --title, o título é perguntado interativamente
iaw create --task
# → Título do work item: <digite aqui>

# Em outro projeto (sem mudar a config global)
iaw create --issue --title "Timeout no login" --project-id cosinf/outro-projeto
```

### 3.3 Saída de sucesso

```
✓ Task criada: https://gitlab.com/cosinf/suap/-/issues/1234
   #1234 — Corrigir N+1 na listagem de diários
   Categoria: task geral | Labels: SET/2026
```

---

## 4. Relatório de tasks/issues fechadas (`iaw relatorio tasks`)

Lista todos os work items **fechados** de um mês e indica a categoria de cada um.

O mês é definido por **dois critérios combinados**:

1. **Label do mês** (ex.: `SET/2026`) — filtrado na API do GitLab.
2. **Data de fechamento** (`closed_at`) — o item precisa ter sido **fechado dentro
   daquele mês**.

Ou seja, só entra no relatório o item que tiver o label do mês **e** tiver sido
fechado naquele mês.

### 4.1 Sintaxe

```bash
iaw relatorio tasks [<label-do-mês>] [--project-id <path>]
```

| Argumento/Opção | Descrição |
|-----------------|-----------|
| `<label-do-mês>` | Label do mês (ex.: `SET/2026`). Se omitido, usa o **mês atual**. |
| `--project-id <path>` | Sobrescreve o projeto padrão. |

### 4.2 Exemplos

```bash
# Relatório de um mês específico
iaw relatorio tasks SET/2026

# Relatório do mês atual (label gerado automaticamente)
iaw relatorio tasks

# Em outro projeto
iaw relatorio tasks SET/2026 --project-id cosinf/suap
```

### 4.3 Saída

```
      Relatório de tasks/issues fechadas (SET/2026)
┏━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃     # ┃ Categoria    ┃ Tipo  ┃ Título                              ┃
┡━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  1234 │ ✅ task geral │ Task  │ Corrigir N+1 na listagem de diários │
│  1235 │ 📦 demanda    │ Task  │ Nova tela de relatórios gerenciais  │
│  1236 │ 🐞 erro       │ Issue │ Erro 500 ao salvar boletim          │
└───────┴──────────────┴───────┴──────────────────────────────────────┘

Total: 3 work item(s) — 1 erro, 1 demanda, 1 task geral.
```

A categoria é determinada assim:

| Categoria | Regra |
|-----------|-------|
| **erro** | Issue com label `bug` |
| **demanda** | Task com label `demandas` |
| **task geral** | Task sem `demandas` |

---

## 5. Fluxo completo de exemplo

```bash
# 1. Abre as tarefas do dia/mês no GitLab
iaw create --task --demanda --title "Tela de exportação de diários"
iaw create --issue --title "Erro 500 ao gerar PDF de boletim"

# 2. Trabalha normalmente (start-task/run/finish-task) e fecha os itens no GitLab

# 3. No fim do mês, gera o relatório de itens fechados
iaw relatorio tasks SET/2026
```

---

## 6. Referência rápida

| Comando | Descrição |
|---------|-----------|
| `iaw create --task --title "..."` | Cria uma Task (task geral) |
| `iaw create --task --demanda --title "..."` | Cria uma Task de demanda |
| `iaw create --issue --title "..."` | Cria uma Issue (erro/bug) |
| `iaw create --task` | Cria Task perguntando o título |
| `iaw relatorio tasks SET/2026` | Lista fechadas do mês (task geral/demanda/erro) |
| `iaw relatorio tasks` | Lista fechadas do mês atual |
| `iaw relatorio tasks --project-id cosinf/suap` | Relatório em outro projeto |

---

## 7. Solução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `Projeto GitLab não configurado` | `gitlab_project` vazio | `iaw config set gitlab_project suap` ou use `--project-id` |
| `Token do GitLab não configurado` | Config global vazia | `iaw setup` |
| `Nenhum work item fechado com o label '...'` | Nenhum item fechado com aquele label, ou label com grafia diferente | Verifique os labels no GitLab (o `iaw` usa maiúsculas, ex.: `SET/2026`) |
| `--demanda só é válido junto de --task` | Usou `--demanda` com `--issue` | Use `--demanda` apenas com `--task` |
| `use apenas um de --task ou --issue` | Passou as duas flags juntas | Escolha só uma |
