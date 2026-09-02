"""Criação e gerenciamento da pasta `.iaw/` (Context as Code) do projeto.

Fase 2: implementa o `iaw init` — gera a estrutura canônica onde ficam as
regras, workflows, skills, agents, templates, hooks e evals do projeto.
"""

from __future__ import annotations

import re
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
4. `iaw finish-task` — audita o código, atualiza o relatório e (com --create-mr) abre o MR.

*Importante: nunca versione credenciais/tokens aqui. Use `iaw config set` para a sua máquina.*
"""

WORKFLOW_NOVA_FEATURE = """# Workflow: nova funcionalidade (Spec-Driven, 5 etapas da Attekita)
name: nova_feature
description: "Fluxo completo para novas features: Entendimento → Planejamento → Backend (TDD) → Frontend (Design System) → Prova → Consolidação."
version: "1.0"

steps:
  # ETAPA 1: ENTENDIMENTO (Agente Principal)
  - id: 1_entendimento_problema
    action: ask_clarifying_questions
    description: "Lê a Issue e o contexto do projeto e faz perguntas para fechar a regra de negócio."
    inputs:
      - source: gitlab_api
        type: issue_description
    context:
      - .iaw/stack.md
      - .iaw/contexto.md
    outputs:
      - file: .iaw_workspace/1_requisitos_validados.md
    require_human_approval: true

  # ETAPA 2: PLANEJAMENTO (Spec — Agente Principal)
  - id: 2_planejamento_arquitetura
    depends_on: [1_entendimento_problema]
    action: generate_artifact
    description: "Gera a especificação técnica (Models, Views, endpoints) a partir dos requisitos validados."
    inputs:
      - file: .iaw_workspace/1_requisitos_validados.md
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/2_especificacao_tecnica.md
    require_human_approval: true

  # ETAPA 3A: BACKEND (Agente Principal + skill: backend_tdd)
  - id: 3a_materializacao_backend
    depends_on: [2_planejamento_arquitetura]
    action: execute_ai_coding
    description: "Implementa o backend (Models, Views, Forms) em ciclos TDD com pytest."
    skill: backend_tdd
    inputs:
      - file: .iaw_workspace/2_especificacao_tecnica.md
    require_human_approval: false
    sandbox:
      blocked_paths: [manage.py, .env]

  # ETAPA 3B: FRONTEND (Subagente suap-frontend)
  - id: 3b_materializacao_frontend
    depends_on: [3a_materializacao_backend]
    action: execute_ai_coding
    description: "Desenha os templates usando estritamente o Design System do SUAP (sem CSS customizado), a partir das Views criadas."
    subagent: suap-frontend
    inputs:
      - file: .iaw_workspace/2_especificacao_tecnica.md
    require_human_approval: false
    sandbox:
      blocked_paths: [manage.py, .env]

  # ETAPA 4: PROVA (testes + validação E2E + visual)
  - id: 4a_prova_testes
    depends_on: [3b_materializacao_frontend]
    action: run_terminal_command
    description: "Roda a suíte de testes do backend (pytest)."
    command: "pytest -q {test_target}"

  - id: 4b_prova_e2e
    depends_on: [4a_prova_testes]
    action: execute_ai_coding
    description: "Escreve/executa os testes E2E de interface (Playwright/Behave) com o subagente e2e-tester."
    subagent: e2e-tester
    allow_no_change: true

  - id: 4c_prova_visual_browser
    depends_on: [4b_prova_e2e]
    action: run_browser_harness
    description: "Abre a aplicação no navegador e captura screenshot como prova visual."
    config:
      start_url: "http://localhost:8000/"
    outputs:
      - file: .iaw_workspace/screenshot_prova.png

  # ETAPA 5: CONSOLIDAÇÃO + MR (Agente Principal + skill: mr-format)
  - id: 5_consolidacao_relatorio
    depends_on: [4c_prova_visual_browser]
    action: generate_summary_and_publish
    description: "Gera o resumo, registra a atividade no relatório e abre o MR (somente com --create-mr)."
    skill: mr-format
    integrations:
      - gitlab:
          action: create_merge_request
      - local_fs:
          action: append_to_file
          target: "{{relatorio_path}}/{{mes_ano}}.md"
"""

WORKFLOW_BUG_FIX = """# Workflow: correção de bug (cirúrgico, concentrado no Agente Principal)
name: bug_fix
description: "Correção de bug enxuta: Sentry → diagnóstico → teste Red → fix → testes → MR. Alta concentração de skills."
version: "1.0"

steps:
  # 1. ANÁLISE DO ERRO (Agente Principal + skill: sentry-fix)
  - id: 1_analisar_erro
    action: generate_artifact
    description: "Analisa o evento/traceback (Sentry) e localiza a causa raiz no código."
    skill: sentry-fix
    inputs:
      - source: gitlab_api
        type: issue_description
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/1_diagnostico_bug.md
    require_human_approval: true

  # 2. TESTE QUE FALHA (Red) — obrigatório antes da correção
  - id: 2_teste_red
    depends_on: [1_analisar_erro]
    action: execute_ai_coding
    description: "Escreve um teste que reproduz o bug e DEVE falhar (Red) antes da correção."
    skill: backend_tdd
    inputs:
      - file: .iaw_workspace/1_diagnostico_bug.md
    require_human_approval: false

  # 3. CORREÇÃO (Agente Principal + skill: sentry-fix)
  - id: 3_corrigir_codigo
    depends_on: [2_teste_red]
    action: execute_ai_coding
    description: "Corrige o código (Green) para o teste passar, de forma cirúrgica."
    skill: sentry-fix
    require_human_approval: false
    sandbox:
      blocked_paths: [manage.py, .env]

  # 4. PROVA
  - id: 4_prova_testes
    depends_on: [3_corrigir_codigo]
    action: run_terminal_command
    description: "Roda os testes para confirmar a correção e ausência de regressão."
    command: "pytest -q {test_target}"

  # 5. CONSOLIDAÇÃO + MR (Agente Principal + skill: mr-format)
  - id: 5_abrir_mr
    depends_on: [4_prova_testes]
    action: generate_summary_and_publish
    description: "Gera o resumo, registra a atividade no relatório e abre o MR (somente com --create-mr)."
    skill: mr-format
    integrations:
      - gitlab:
          action: create_merge_request
"""

WORKFLOW_REFATORACAO = """# Workflow: refatoração segura (rede de segurança + regressão)
name: refatoracao
description: "Refatoração segura: rede de segurança → refatorar → regressão → adaptar frontend → MR."
version: "1.0"

steps:
  # 1A. REDE DE SEGURANÇA — BACKEND (Agente Principal + skill: generate-test)
  - id: 1a_rede_seguranca_backend
    action: generate_artifact
    description: "Gera a rede de segurança do backend (testes de regressão) com a skill generate-test."
    skill: generate-test
    context:
      - .iaw/stack.md
    outputs:
      - file: .iaw_workspace/1a_rede_seguranca_backend.md
    allow_no_change: true
    require_human_approval: true

  # 1B. REDE DE SEGURANÇA — FRONTEND (Subagente e2e-tester)
  - id: 1b_rede_seguranca_frontend
    depends_on: [1a_rede_seguranca_backend]
    action: generate_artifact
    description: "Mapeia a tela atual (comportamento visual) antes de refatorar, com o subagente e2e-tester."
    subagent: e2e-tester
    outputs:
      - file: .iaw_workspace/1b_rede_seguranca_frontend.md
    allow_no_change: true
    require_human_approval: true

  # 2. REFATORAR (Agente Principal + hooks de complexidade)
  - id: 2_refatorar
    depends_on: [1b_rede_seguranca_frontend]
    action: execute_ai_coding
    description: "Refatora o código mantendo o comportamento, rodando os hooks de complexidade (check_complexity.py, complexidade <= 10)."
    context:
      - .iaw/hooks/check_complexity.py
    require_human_approval: false

  # 3. REGRESSÃO
  - id: 3_regressao
    depends_on: [2_refatorar]
    action: run_terminal_command
    description: "Roda a suíte de testes para garantir que nenhum comportamento mudou (regressão)."
    command: "pytest -q {test_target}"

  # 4. ADAPTAR FRONTEND (Subagente suap-frontend)
  - id: 4_adaptar_frontend
    depends_on: [3_regressao]
    action: execute_ai_coding
    description: "Adapta o frontend se as variáveis de contexto das Views refatoradas mudaram."
    subagent: suap-frontend
    allow_no_change: true

  # 5. CONSOLIDAÇÃO + MR (Agente Principal + skill: mr-format)
  - id: 5_abrir_mr
    depends_on: [4_adaptar_frontend]
    action: generate_summary_and_publish
    description: "Gera o resumo, registra a atividade no relatório e abre o MR (somente com --create-mr)."
    skill: mr-format
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

SKILL_DEFAULT = """---
name: default
description: Skill padrão usada quando nenhuma skill específica é definida.
trigger: /default
---
# Skill padrão (full-stack)

Você é um desenvolvedor sênior full-stack. Trabalhe de forma incremental,
respeite a arquitetura existente e as diretrizes de `stack.md`/`contexto.md`.
Não introduza bibliotecas/padrões externos sem aprovação. Prefira código
simples, testável e em pt-BR.
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


SUAP_SKILLS: dict[str, str] = {
    "backend_tdd": """---
name: backend_tdd
description: Desenvolvimento backend orientado a testes (TDD) com pytest, para o SUAP.
trigger: /backend_tdd
---
# Skill: Backend TDD (Django + pytest)

Você é um especialista em desenvolvimento backend no SUAP (Django + PostgreSQL),
seguindo estritamente os padrões do sistema definidos em `stack.md` e `contexto.md`.
Trabalhe em ciclos TDD:

1. **Red** — escreva um teste que falha (pytest) para o comportamento desejado.
2. **Green** — implemente a menor quantidade de código para o teste passar.
3. **Refactor** — limpe o código mantendo os testes verdes.

- Foco: Models, Views, Forms, Serializers e regras de negócio.
- Sempre rode `pytest -q {test_target}` após cada ciclo.
- Respeite a arquitetura e os padrões existentes do SUAP.
- Não introduza bibliotecas externas sem aprovação.
""",
    "sentry-fix": """---
name: sentry-fix
description: Correção de bugs a partir de eventos do Sentry (análise de causa raiz).
trigger: /sentry-fix
---
# Skill: Sentry Fix

Você é um especialista em triagem e correção de bugs via Sentry.

1. Analise o traceback/evento do Sentry para identificar a causa raiz.
2. Reproduza o cenário em um teste que falha (Red).
3. Corrija o código (Green) e garanta que o teste passa.
4. Valide o impacto no código relacionado (regressão).

- Use busca semântica para localizar o código relevante.
- Foco em correções cirúrgicas, sem refatorações desnecessárias.
""",
    "mr-format": """---
name: mr-format
description: Formatação do Merge Request (título, descrição e changelog).
trigger: /mr-format
---
# Skill: MR Format

Você formata a abertura do Merge Request no GitLab.

- Título: `[módulo] Issue #id: resumo curto`.
- Descrição: sumário, causa raiz, arquivos modificados, impacto e changelog.
- Sempre inclua `Closes #id`.
- Linguagem: pt-BR, objetivo e claro.
""",
    "generate-test": """---
name: generate-test
description: Geração de rede de segurança (testes de regressão) para código existente.
trigger: /generate-test
---
# Skill: Generate Test

Você gera a "rede de segurança" antes de qualquer refatoração ou correção.

- Mapeie o comportamento atual e escreva testes de regressão (pytest).
- Cubra os fluxos críticos e casos de borda.
- Garanta que os testes passem ANTES de alterar o código de produção.
- Foco: backend Django (Models, Views, Forms, regras de negócio).
""",
}

SUAP_AGENTS: dict[str, str] = {
    "suap-frontend": """---
name: suap-frontend
description: Especialista em frontend do SUAP (Design System, templates Django).
---
# Agente: SUAP Frontend

Você é um especialista em frontend do SUAP, restrito ao Design System oficial.

- Trabalhe APENAS com templates Django e o Design System do SUAP.
- Proibido CSS customizado ou frameworks externos.
- Reaproveite componentes existentes; respeite classes, variáveis e padrões visuais.
- Receba as Views/contextos criados e desenhe os templates correspondentes.
""",
    "e2e-tester": """---
name: e2e-tester
description: Especialista em testes E2E (Playwright/Behave) — simulação externa de UI.
---
# Agente: E2E Tester

Você é um especialista em testes end-to-end (Playwright/Behave).

- Escreva e/ou execute cenários E2E que simulam o usuário real.
- Valide fluxos de interface (navegação, formulários, feedback visual).
- Relate o resultado com evidências (screenshots/logs).
- Não altere regra de negócio; apenas valide o comportamento externo.
""",
}


def is_suap_project(root: Path) -> bool:
    """Detecta (por heurística) se `root` é o projeto SUAP."""
    root = Path(root)
    if root.name.lower() == "suap" or (root / "suap").is_dir():
        return True
    manage = root / "manage.py"
    if manage.is_file():
        try:
            if "suap" in manage.read_text(encoding="utf-8").lower():
                return True
        except (OSError, UnicodeDecodeError):
            pass
    return False


def create_suap_defaults(root: Path) -> list[Path]:
    """Cria as skills/agentes padrão quando o projeto é o SUAP.

    Também renomeia a skill legada ``tdd`` para ``backend_tdd`` (caso o legado
    a tenha importado) e ajusta o ``name:`` do frontmatter.

    Retorna a lista de arquivos criados (vazia se não for SUAP ou já existirem).
    """
    if not is_suap_project(root):
        return []

    # O legado do SUAP usa o nome `tdd`; aqui a skill vira `backend_tdd`.
    legacy_tdd = IAW_DIR / "skills" / "tdd"
    backend_tdd = IAW_DIR / "skills" / "backend_tdd"
    if legacy_tdd.is_dir() and not backend_tdd.exists():
        legacy_tdd.rename(backend_tdd)
        _rename_skill_name(backend_tdd, "tdd", "backend_tdd")

    created: list[Path] = []
    for name, content in SUAP_SKILLS.items():
        skill_file = IAW_DIR / "skills" / name / "SKILL.md"
        if not skill_file.exists():
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            skill_file.write_text(content, encoding="utf-8")
            created.append(skill_file)

    for name, content in SUAP_AGENTS.items():
        # O agente pode já ter vindo do legado (`.iaw/agents/<name>.md`) ou
        # existir como diretório (`AGENT.md`/`SKILL.md`/`agent.md`).
        if any([
            (IAW_DIR / "agents" / f"{name}.md").is_file(),
            (IAW_DIR / "agents" / name / "AGENT.md").is_file(),
            (IAW_DIR / "agents" / name / "SKILL.md").is_file(),
            (IAW_DIR / "agents" / name / "agent.md").is_file(),
        ]):
            continue
        agent_file = IAW_DIR / "agents" / name / "AGENT.md"
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text(content, encoding="utf-8")
        created.append(agent_file)

    return created


def _rename_skill_name(skill_dir: Path, old: str, new: str) -> None:
    """Atualiza o ``name:`` do frontmatter de um SKILL.md renomeado."""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return
    text = skill_file.read_text(encoding="utf-8")
    updated = re.sub(
        rf"(?m)^name:\s*{re.escape(old)}\s*$", f"name: {new}", text, count=1
    )
    if updated != text:
        skill_file.write_text(updated, encoding="utf-8")


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

    # Skill padrão: sempre existe, usada como fallback quando um step aponta
    # para uma skill/agent que ainda não foi instalada.
    default_skill = IAW_DIR / "skills" / "default" / "SKILL.md"
    if not default_skill.exists():
        default_skill.parent.mkdir(parents=True, exist_ok=True)
        default_skill.write_text(SKILL_DEFAULT, encoding="utf-8")

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
    """Inicializa a estrutura `.iaw/` completa (base)."""
    write_default_files(stack, testes)
