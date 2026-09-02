# Exemplos de Fluxos de Dev — `iaw` no SUAP

> Passo a passo prático para testar o `iaw` no projeto SUAP, cobrindo uma
> **issue de bug**, uma **nova funcionalidade** e um **bug com especialistas
> por área** (frontend/backend).

---

## 0. Como chamar o `iaw` a partir do SUAP (a questão do venv)

O `iaw` é um **executável independente** (console script) que vive no venv do
projeto `ia_workflow`, **não** precisa ser instalado no venv do SUAP.

O SUAP tem seu próprio `.venv` (com Django, pytest etc.) — e isso **não conflita**:
são dois ambientes separados, usados em momentos diferentes.

### Três formas de chamar o `iaw` de dentro do SUAP

**Opção A — caminho absoluto (funciona já, sem configurar nada):**

```bash
cd /home/inacio/workspace/suap
/home/inacio/workspace/ia_workflow/.venv/bin/iaw --help
```

**Opção B — symlink no `~/.local/bin` (recomendado para o seu dia a dia):**

```bash
mkdir -p ~/.local/bin
ln -s /home/inacio/workspace/ia_workflow/.venv/bin/iaw ~/.local/bin/iaw
# ~/.local/bin precisa estar no PATH (normalmente já está)
iaw --help
```

**Opção C — pipx (recomendado para o time inteiro):**

```bash
pipx install /home/inacio/workspace/ia_workflow
iaw --help
```

### E o venv do SUAP?

O venv do SUAP continua sendo usado **para o SUAP** (rodar `pytest`, `manage.py`,
etc.). Ative-o **antes** de rodar `iaw run`, para que a etapa de testes use o
`pytest` correto:

```bash
cd /home/inacio/workspace/suap
source .venv/bin/activate        # venv do SUAP (para pytest/manage.py)
iaw run --workflow bug_fix --issue-id 4512   # iaw chama o pytest que estiver no PATH
```

> Resumindo: **`iaw` = ferramenta global** (fora do venv do SUAP). **venv do
> SUAP = dependências do SUAP** (Django, pytest). Ative o venv do SUAP quando
> for rodar workflows que executam `pytest`.

---

## Pré-requisitos (uma única vez)

```bash
# 1. Configurar o iaw (token do GitLab com permissão de API)
iaw setup
#   → token GitLab
#   → URL: https://gitlab.com
#   → projeto: cosinf/suap
#   → motor: antigravity   (ou pi-coding / aider)
#   → seu nome (para o relatório)

# Se usar Antigravity (sem API key), defina também o modelo:
iaw config set default_engine antigravity
iaw config set default_model gemini-3.1-pro-high
# Veja os modelos disponíveis com: agy models

# (opcional) limite da janela de contexto — evita estourar o modelo
iaw config set context_max_chars 80000
iaw config set context_max_file_chars 20000

# 2. Preparar o SUAP
cd /home/inacio/workspace/suap
source .venv/bin/activate
iaw init                 # cria .iaw/ (rápido; stack/contexto ficam simples)
iaw init --analyze       # (opcional) já preenche stack.md/contexto.md com a IA
iaw import-legacy        # copia as 18 skills + agents + hooks (não apaga o legado)

git add .iaw && git commit -m "feat: adiciona .iaw (Context as Code do iaw)"
```

---

## Cenário 1 — Issue de **bug** 🐛

> Exemplo: Issue `#4512` — "Corrigir lentidão na listagem de diários".

```bash
cd /home/inacio/workspace/suap
source .venv/bin/activate

# 1. Branch da tarefa
git checkout master && git pull origin master
git checkout -b iaw/issue-4512

# 2. Baixa a Issue e gera o artefato inicial
iaw start-task 4512
#    → .iaw_workspace/1_requisitos_validados.md (Issue + stack.md)
```

### 3. Revise o artefato antes de prosseguir

```bash
cat .iaw_workspace/1_requisitos_validados.md
```

Se a IA entendeu errado a regra de negócio, **corrija o texto** (não o código).

### 4. Orquestra o workflow de bug

```bash
# A tarefa é inferida da branch (iaw/issue-4512); para ser explícito:
iaw run --workflow bug_fix --issue-id 4512

# Para ver o log de execução da IA (prompt, contexto e saída):
iaw run --workflow bug_fix --issue-id 4512 --log

# Para abrir o MR ao final (por padrão, não cria MR):
iaw run --workflow bug_fix --issue-id 4512 --create-mr
```

| Etapa | Ação | Você precisa? |
|-------|------|---------------|
| `1_analisar_erro` | IA (skill sentry-fix) gera o diagnóstico → `.iaw_workspace/1_diagnostico_bug.md` | **Aprovar** (gate) |
| `2_teste_red` | IA (skill backend_tdd) escreve um teste que falha (Red) | Não |
| `3_corrigir_codigo` | IA (skill sentry-fix) corrige o código | Não (autônoma) |
| `4_prova_testes` | Roda `pytest -q` | Não |
| `5_abrir_mr` | Resumo + relatório (+ MR com `--create-mr`) | Não |

### 5. Acompanhe

```bash
iaw status            # histórico de execuções
```

**Resultado esperado**: atividade registrada em
`~/.config/ia_workflow/reports/<mes>_<ano>.md` (e, com `--create-mr`, MR aberto
no GitLab com `Closes #4512`).

> Alternativa manual: se preferir controlar a publicação, use `iaw finish-task`
> (ou `--create-mr` para abrir o MR).

---

## Cenário 2 — Issue de **nova funcionalidade** ✨

> Exemplo: Issue `#4540` — "Adicionar exportação CSV na listagem de diários".

```bash
cd /home/inacio/workspace/suap
source .venv/bin/activate

# 1. Branch da tarefa
git checkout master && git pull origin master
git checkout -b iaw/issue-4540

# 2. Baixa a Issue
iaw start-task 4540
```

### 3. Prepare a prova visual (etapa 4c)

```bash
# Playwright + chromium (se ainda não instalou)
pip install -e '.[browser]' && playwright install chromium

# SUAP rodando em outro terminal:
python manage.py runserver
```

### 4. Orquestra o workflow completo

```bash
iaw run --workflow nova_feature --issue-id 4540 --notify
# adicione --log para ver o prompt/contexto/saída da IA em cada etapa
```

| Etapa | Ação | Você precisa? |
|-------|------|---------------|
| `1_entendimento_problema` | IA faz perguntas para fechar a regra de negócio | **Aprovar** |
| `2_planejamento_arquitetura` | IA gera a spec técnica (models/views) | **Aprovar** |
| `3a_materializacao_backend` | IA (skill backend_tdd) implementa o backend | Não |
| `3b_materializacao_frontend` | Subagente suap-frontend desenha os templates (Design System) | Não |
| `4a_prova_testes` | Roda `pytest -q` | Não |
| `4b_prova_e2e` | Subagente e2e-tester valida o fluxo de UI | Não |
| `4c_prova_visual_browser` | Abre o navegador e tira **screenshot** da tela | Não |
| `5_consolidacao_relatorio` | Resumo + relatório (+ MR com `--create-mr`) | Não |

`--notify` avisa no desktop ao terminar — você pode sair da frente do
computador **após aprovar a spec na etapa 2**.

---

## Cenário 3 — Bug com **especialistas por área** (frontend/backend) 🎯

> Exemplo: Issue `#4600` — erro em tela e na API; nem toda tarefa precisa das
> duas frentes. Aqui usamos `skill:` para cada área e `allow_no_change: true`
> para a IA pular a frente que não se aplicar.

### 1. Workflow especializado (`.iaw/workflows/bug_fix_por_area.yaml`)

```yaml
name: bug_fix_por_area
description: "Bug com diagnóstico + correção por área (frontend e backend)."
version: "1.0"

steps:
  - id: 1_analisar_erro
    action: generate_artifact
    skill: bug-analyst            # .iaw/skills/bug-analyst/SKILL.md
    context: [.iaw/stack.md]
    outputs:
      - file: .iaw_workspace/1_diagnostico_bug.md
    require_human_approval: true

  - id: 2_corrigir_frontend
    depends_on: [1_analisar_erro]
    action: execute_ai_coding
    skill: frontend-suap          # segue o design system do SUAP
    allow_no_change: true         # sem ajuste de frontend? a IA avisa e segue

  - id: 3_corrigir_backend
    depends_on: [2_corrigir_frontend]
    action: execute_ai_coding
    skill: backend-suap           # padrões Django do SUAP
    allow_no_change: true

  - id: 4_prova_testes
    depends_on: [3_corrigir_backend]
    action: run_terminal_command
    command: "pytest -q {test_target}"

  - id: 5_abrir_mr
    depends_on: [4_prova_testes]
    action: generate_summary_and_publish
```

> As skills `bug-analyst`, `frontend-suap` e `backend-suap` precisam existir em
> `.iaw/skills/`. Se uma delas não existir, a etapa falha com erro claro —
> instale com `iaw skill add <nome> --source <path|url>` ou use `agent:` para
> ler de `.iaw/agents/<nome>.md`.

### 2. Execução

```bash
git checkout -b iaw/issue-4600
iaw start-task 4600
iaw run --workflow bug_fix_por_area --issue-id 4600 --log
```

### 3. O que acontece se só o backend precisar de mudança

- `2_corrigir_frontend` roda com o perfil `frontend-suap`; a IA percebe que não
  há ajuste de frontend e responde `SEM_ALTERACOES_NECESSARIAS`.
- O `iaw` registra:
  ```
  ⏭ Etapa 2_corrigir_frontend: sem alterações necessárias (a IA indicou que nada precisa ser feito).
  ```
- O fluxo **continua** para `3_corrigir_backend` sem abrir gate nem escrever arquivos.

---

## Regras que valem para os dois cenários

- A IA **nunca faz merge** — só abre o MR; o merge é revisão humana no GitLab.
- Se testes/validação falham, o fluxo **interrompe** (fail-safe).
- Você corrige **documentos** (artefatos) antes do código, não o código.
- Tudo fica rastreável: Issue → artefatos → código → MR → relatório.

## Fluxo mental (resumo)

```
git branch → iaw start-task → REVISAR artefato → iaw run (aprovando gates)
           → MR automático → relatório registrado → code review humano no GitLab

# quer enxergar o que a IA está fazendo em cada etapa?
#   iaw run --workflow <nome> --issue-id <id> --log
```

---

## Solução de problemas rápidos

| Erro | Causa | Solução |
|------|-------|---------|
| `Token do GitLab não configurado` | `iaw setup` não foi feito | `iaw setup` |
| `Comando 'pi' não encontrado` | motor fora do PATH | instale o Pi ou `iaw config set default_engine aider` |
| `Comando 'agy' não encontrado` | Antigravity CLI fora do PATH | instale o Antigravity CLI ou `iaw config set default_engine pi-coding` |
| `Skill 'x' não encontrada` | step usa `skill:` sem a skill em `.iaw/skills/` | `iaw skill add x --source <path\|url>` ou remova o `skill:` |
| `Playwright não está instalado` | extra `browser` ausente | `pip install -e '.[browser]'` + `playwright install chromium` |
| Etapa 4b falha | SUAP não está em `localhost:8000` | `python manage.py runserver` e rode de novo |
