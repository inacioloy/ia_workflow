"""Criação e gerenciamento da pasta `.iaw/` (Context as Code) do projeto.

Fase 2: implementa o `iaw init` — gera a estrutura canônica onde ficam as
regras, workflows, skills, agents, templates, hooks e evals do projeto.
"""

from __future__ import annotations

from pathlib import Path

IAW_DIR = Path(".iaw")

# --- Conteúdo padrão gerado pelo `iaw init` --------------------------------- #

README_CONTENT = """# 🤖 IA Workflow (iaw) — Contexto do Projeto

Este diretório contém as regras de negócio, arquitetura e fluxos de trabalho
(Graph Engineering) usados pela IA para auxiliar no desenvolvimento deste projeto.

## 📂 Estrutura

- `stack.md` — o "Context as Code": stack, comandos e guardrails rígidos (evita alucinação arquitetural).
- `contexto.md` — domínio do negócio: atores, subsistemas, invariantes e integrações.
- `workflows/` — grafos YAML (bug_fix, nova_feature, refatoracao) com as etapas e gates de aprovação.
- `skills/` — skills modulares (SKILL.md) que os desenvolvedores podem importar.
- `agents/` — subagentes especializados (documentador, security-reviewer, etc.).
- `templates/` — templates de artefatos (requisitos, especificação, MR).
- `hooks/` — scripts de enforcement (complexidade, pre-commit, time-spent).
- `evals/` — Golden Dataset para testar skills/agentes (Fase 5).

## 🚀 Como usar

1. `iaw init` — reconfigura o contexto deste projeto.
2. `iaw start-task <id_gitlab>` — inicia uma tarefa a partir de uma Issue do GitLab.
3. `iaw run` — orquestra a IA pelo workflow configurado.
4. `iaw finish-task` — audita o código, abre o MR e atualiza o relatório PGD.

*Importante: nunca versione credenciais/tokens aqui. Use `iaw config set` para a sua máquina.*
"""

WORKFLOW_NOVA_FEATURE = """# Workflow: nova funcionalidade (Spec-Driven, 5 etapas da Attekita)
name: nova_feature
description: "Fluxo completo para novas features: Entendimento → Planejamento → Código → Prova → Consolidação."
version: "1.0"

steps:
  # ETAPA 1: ENTENDIMENTO
  - id: 1_entendimento_problema
    action: ask_clarifying_questions
    inputs:
      - source: gitlab_api
        type: issue_description
    context:
      - .iaw/stack.md
      - .iaw/contexto.md
    outputs:
      - file: .iaw_workspace/1_requisitos_validados.md
    require_human_approval: true

  # ETAPA 2: PLANEJAMENTO (Spec)
  - id: 2_planejamento_arquitetura
    depends_on: [1_entendimento_problema]
    action: generate_artifact
    inputs:
      - file: .iaw_workspace/1_requisitos_validados.md
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/2_especificacao_tecnica.md
    require_human_approval: true

  # ETAPA 3: CÓDIGO
  - id: 3_materializacao_codigo
    depends_on: [2_planejamento_arquitetura]
    action: execute_ai_coding
    inputs:
      - file: .iaw_workspace/2_especificacao_tecnica.md
    require_human_approval: false
    sandbox:
      blocked_paths: [manage.py, .env]

  # ETAPA 4: PROVA (testes + validação visual)
  - id: 4a_prova_testes
    depends_on: [3_materializacao_codigo]
    action: run_terminal_command
    command: "pytest -q"

  - id: 4b_prova_visual_browser
    depends_on: [4a_prova_testes]
    action: run_browser_harness
    config:
      start_url: "http://localhost:8000/"
    outputs:
      - file: .iaw_workspace/screenshot_prova.png

  # ETAPA 5: CONSOLIDAÇÃO + PGD
  - id: 5_consolidacao_relatorio
    depends_on: [4b_prova_visual_browser]
    action: generate_summary_and_publish
    integrations:
      - gitlab:
          action: create_merge_request
      - local_fs:
          action: append_to_file
          target: "{{pgd_report_path}}/{{mes_ano}}.md"
"""

WORKFLOW_BUG_FIX = """# Workflow: correção de bug (direto, focado no traceback)
name: bug_fix
description: "Correção de bug enxuta: analisar erro → fix → testes → MR. Pula a etapa de arquitetura."
version: "1.0"

steps:
  - id: 1_analisar_erro
    action: generate_artifact
    inputs:
      - source: gitlab_api
        type: issue_description
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/1_diagnostico_bug.md
    require_human_approval: true

  - id: 2_corrigir_codigo
    depends_on: [1_analisar_erro]
    action: execute_ai_coding
    require_human_approval: false
    sandbox:
      blocked_paths: [manage.py, .env]

  - id: 3_prova_testes
    depends_on: [2_corrigir_codigo]
    action: run_terminal_command
    command: "pytest -q"

  - id: 4_abrir_mr
    depends_on: [3_prova_testes]
    action: generate_summary_and_publish
    integrations:
      - gitlab:
          action: create_merge_request
"""

WORKFLOW_REFATORACAO = """# Workflow: refatoração (clean code + testes de regressão)
name: refatoracao
description: "Refatoração segura: reduzir complexidade sem alterar comportamento, com regressão forte."
version: "1.0"

steps:
  - id: 1_mapear_alvo
    action: generate_artifact
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/1_plano_refatoracao.md
    require_human_approval: true

  - id: 2_refatorar
    depends_on: [1_mapear_alvo]
    action: execute_ai_coding
    context:
      - .iaw/hooks/check_complexity.py
    require_human_approval: false

  - id: 3_regressao
    depends_on: [2_refatorar]
    action: run_terminal_command
    command: "pytest -q"

  - id: 4_abrir_mr
    depends_on: [3_regressao]
    action: generate_summary_and_publish
    integrations:
      - gitlab:
          action: create_merge_request
"""

TEMPLATE_BUG = """# Diagnóstico de Bug

## Issue GitLab
<!-- preenchido pelo `iaw start-task` -->

## Comportamento esperado
<!-- o que deveria acontecer -->

## Comportamento atual
<!-- o que está acontecendo -->

## Traceback / erro
```
<!-- cole o traceback aqui -->
```

## Causa raiz (a preencher pela IA)
<!-- identificada ANTES de propor correção -->

## Arquivos suspeitos
- 
"""

TEMPLATE_FEATURE = """# Requisitos de Nova Funcionalidade

## Issue GitLab
<!-- preenchido pelo `iaw start-task` -->

## Regra de negócio
<!-- o que a funcionalidade deve fazer -->

## Models afetados
- 

## Endpoints / views
- 

## Critérios de aceitação
- [ ] 
"""

CI_EVALS_TEMPLATE = """# Exemplo de estágio de Evals de IA para o .gitlab-ci.yml do projeto.
#
# Copie este bloco para o seu .gitlab-ci.yml (ou use `include`) e ajuste a
# imagem/base conforme o ambiente. O motor de IA (pi/aider) e as credenciais
# devem estar disponíveis no runner.
#
# Primeira execução: cria o baseline (.iaw/evals/.baseline.json) e passa.
# Execuções seguintes: falham se uma skill regredir o score.
ai-evals:
  stage: test
  image: python:3.12
  script:
    - pip install ia_workflow
    - iaw eval all
  rules:
    - changes:
        - .iaw/**/*
"""


def ensure_structure() -> None:
    """Cria a estrutura de diretórios da `.iaw/` se ainda não existir."""
    for sub in ("workflows", "skills", "agents", "templates", "hooks", "evals"):
        (IAW_DIR / sub).mkdir(parents=True, exist_ok=True)


def write_default_files(stack: str, testes: str) -> None:
    """Escreve os arquivos padrão (stack.md, README, workflows, templates)."""
    ensure_structure()

    stack_content = (
        "# Diretrizes Técnicas do Projeto\n\n"
        f"- **Stack:** {stack}\n"
        f"- **Testes:** {testes}\n"
        "- **Regras de Negócio:** respeite a arquitetura existente. Não sugira "
        "bibliotecas externas sem aprovação.\n"
        "- **Idioma:** pt-BR (código, comentários, commits, docs).\n"
    )
    (IAW_DIR / "stack.md").write_text(stack_content, encoding="utf-8")

    # contexto.md só é criado se não existir (não sobrescreve domínio já documentado).
    contexto_path = IAW_DIR / "contexto.md"
    if not contexto_path.exists():
        contexto_path.write_text(
            "# Contexto do Projeto\n\n<!-- Descreva aqui o domínio, atores, "
            "subsistemas e invariantes. -->\n",
            encoding="utf-8",
        )

    (IAW_DIR / "README.md").write_text(README_CONTENT, encoding="utf-8")

    workflows = {
        "nova_feature.yaml": WORKFLOW_NOVA_FEATURE,
        "bug_fix.yaml": WORKFLOW_BUG_FIX,
        "refatoracao.yaml": WORKFLOW_REFATORACAO,
    }
    for name, content in workflows.items():
        path = IAW_DIR / "workflows" / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    templates = {
        "bug_template.md": TEMPLATE_BUG,
        "feature_template.md": TEMPLATE_FEATURE,
        "gitlab-ci-evals.yml": CI_EVALS_TEMPLATE,
    }
    for name, content in templates.items():
        path = IAW_DIR / "templates" / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def init_project(stack: str, testes: str) -> None:
    """Inicializa a estrutura `.iaw/` completa."""
    write_default_files(stack, testes)
