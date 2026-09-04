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
iaw create (--task | --issue) [--demanda] [--title <título>] [--project-id <path>] [--recording]
```

| Opção | Descrição |
|-------|-----------|
| `--task` | Cria uma **Task** (obrigatório escolher entre `--task` e `--issue`). |
| `--issue` | Cria uma **Issue** (erro/bug). |
| `--demanda` | Só com `--task`: adiciona o label `demandas` (task de demanda). |
| `--title <t>` | Título do work item. Se omitido, o `iaw` **pergunta** o título. |
| `--project-id <path>` | Sobrescreve o projeto padrão (ex.: `cosinf/suap`). |
| `--recording`, `--record` | Grava janelas ativas + screenshots da tela. Encerre com `iaw finish-task`. |

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

### 3.4 Gravação de atividades (`--recording`)

Com `--recording`, o `iaw` cria o work item **e já inicia um processo em segundo
plano** que registra:

- o **título da janela ativa** (com timestamp) num log local;
- **screenshots periódicos** da tela inteira (todos os monitores), salvos em
  `.iaw_workspace/recording/<id>/shots/` (redimensionados para JPEG).

A captura se adapta ao ambiente:

| Ambiente | Título da janela | Screenshot |
|----------|------------------|------------|
| Windows nativo | API nativa (`ctypes`) | `mss` |
| **WSL** | `powershell.exe` (tela do Windows) | `powershell.exe` (tela do Windows) |
| Linux | `xdotool` | `mss` |

> ⚠️ **No WSL**, o `iaw` roda no Linux, mas captura a tela do **Windows** (seu
> desktop real, com e-mail/WhatsApp/etc.) via interop `powershell.exe`. É o
> comportamento esperado: sem isso, o display do WSL ficaria preto.

```bash
# 1. Cria a task e começa a gravar (janelas + screenshots)
iaw create --task --title "Enviar RIT com atividades do mês" --recording

# 2. ... realiza suas atividades normalmente ...

# 3. Encerra: para a gravação, sugere o resumo e fecha a task
iaw finish-task
```

O `iaw finish-task` detecta a gravação ativa e, em sequência:

1. **Para a gravação** e mostra o histórico de janelas registradas;
2. **Sugere um resumo**: com screenshots capturados, o `iaw` envia as imagens
   para o **Gemini via `agy`** (motor Antigravity), que **lê as telas** e resume
   o que foi feito — você pode editar antes de confirmar. Sem screenshots, o
   resumo é gerado a partir dos títulos das janelas pelo motor configurado;
3. **Pergunta se quer atualizar o título** da task;
4. **Atualiza e fecha o work item** no GitLab com: título (atualizado ou
   original), descrição = resumo, **assignee = você** (já definido na criação),
   **data de fechamento** (o GitLab preenche ao fechar) e **label do mês**
   (garantido, preservando os labels existentes).

> O processo de gravação roda em background e é encerrado automaticamente pelo
> `finish-task`. Se precisar cancelar sem fechar, basta apagar o arquivo
> `.iaw_workspace/recording_session.json` e o processo para na próxima iteração.

---

## 4. Relatório de tasks/issues fechadas (`iaw relatorio tasks`)

Lista os work items do mês **do usuário do token** (você), divididos em **três
listas**:

- ✅ **Task geral**
- 🐞 **Erros (issues)**
- 📦 **Demandas**

O mês é indicado pelo argumento (ex.: `AGO/2026`). Um item entra no relatório se:

1. **Tiver o label do mês** (ex.: `AGO/2026`) — **prioridade**; ou
2. **Tiver sido fechado dentro do mês** (`closed_at`) — mesmo sem o label.

Itens com mais de um label de mês (ex.: `AGO/2026` e `SET/2026`) aparecem **nos
dois relatórios**. Só entram itens em que você é **autor** ou **assignee**.

O relatório mostra o papel (`autor`, `resolvido por`, `autor e resolvido por`),
o status (`fechado`/`execução`) e o link.

### 4.1 Sintaxe

```bash
iaw relatorio tasks [<label-do-mês>] [--incluir-abertos] [--project-id <path>]
```

| Argumento/Opção | Descrição |
|-----------------|-----------|
| `<mês>` | Mês do relatório (ex.: `AGO/2026`). Se omitido, usa o **mês atual**. |
| `--incluir-abertos` | Inclui itens **abertos** com o label do mês, ao final (status `execução`). |
| `--project-id <path>` | Sobrescreve o projeto padrão. |

### 4.2 Exemplos

```bash
# Relatório de um mês específico
iaw relatorio tasks SET/2026

# Incluindo itens abertos (em execução)
iaw relatorio tasks SET/2026 --incluir-abertos

# Relatório do mês atual (label gerado automaticamente)
iaw relatorio tasks

# Em outro projeto
iaw relatorio tasks SET/2026 --project-id cosinf/suap
```

### 4.3 Saída

```
Relatório SET/2026 — inacio

✅ Task geral
  #1234  Task  autor              Corrigir N+1 nos diários  https://.../1234

🐞 Erros (issues)
  #1236  Issue  autor e resolvido por  Erro 500 ao salvar boletim  https://.../1236

📦 Demandas
  #1235  Task  resolvido por  Nova tela de relatórios  https://.../1235

🔄 Em execução (com --incluir-abertos)
  #1240  Task  autor  Nova funcionalidade  https://.../1240  (status: execução)

Total: 4 work item(s) — 1 task geral (fechado), 1 erro (fechado), 1 demanda (fechado), 1 task geral (execução).
```

A categoria é determinada assim:

| Categoria | Regra |
|-----------|-------|
| **erro** | Issue com label `bug` |
| **demanda** | Task com label `demandas` |
| **task geral** | Task sem `demandas` |

O campo **Papel** indica a relação do usuário do token com o item:

| Papel | Significado |
|-------|-------------|
| `autor` | Você criou o work item |
| `resolvido por` | Você é o assignee |
| `autor e resolvido por` | Você criou e também é o assignee |

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

Fluxo com gravação de atividades:

```bash
# 1. Cria a task já gravando as janelas ativas
iaw create --task --title "Enviar RIT com atividades do mês" --recording

# 2. ... trabalha normalmente ...

# 3. Para a gravação, sugere o resumo e fecha a task
iaw finish-task
```

---

## 6. Referência rápida

| Comando | Descrição |
|---------|-----------|
| `iaw create --task --title "..."` | Cria uma Task (task geral) |
| `iaw create --task --demanda --title "..."` | Cria uma Task de demanda |
| `iaw create --issue --title "..."` | Cria uma Issue (erro/bug) |
| `iaw create --task` | Cria Task perguntando o título |
| `iaw create --task --title "..." --recording` | Cria Task e grava janelas + screenshots; feche com `iaw finish-task` |
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
