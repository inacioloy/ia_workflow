# Entendendo um arquivo de Workflow (`.iaw/workflows/*.yaml`)

Este documento explica o formato, o funcionamento e as regras de delegação dos
workflows do `iaw`. Ele complementa o [README](../README.md) e o
[Guia do Desenvolvedor](GUIA_DESENVOLVEDOR.md).

---

## 1. O que é um workflow

Um workflow é um **grafo de etapas (nós)** declarado em YAML. O `iaw run` lê esse
grafo, ordena as etapas pelas dependências (`depends_on`) e executa cada uma delas
chamando o motor de IA, rodando comandos de terminal ou acionando integrações
(GitLab, navegador, relatório).

Cada workflow é um arquivo em `.iaw/workflows/<nome>.yaml`. O nome do arquivo
(sem extensão) é o nome usado em `iaw run --workflow <nome>`.

---

## 2. Estrutura do arquivo

```yaml
name: nova_feature                # nome do workflow
description: "Fluxo para ..."     # descrição curta (exibida no iaw run)
version: "1.0"                    # versão do fluxo

steps:
  - id: 1_entendimento_problema   # identificador único da etapa
    action: ask_clarifying_questions
    description: "..."            # o que a etapa faz (usado no monitoramento)
    depends_on: []                # dependências (ordem de execução)
    inputs: []                    # artefatos/fontes de entrada
    context: []                   # arquivos de contexto anexados ao prompt
    outputs: []                   # artefatos gravados pela etapa
    skill: default                # delegação (Agente Principal)
    # subagent: suap-frontend     # delegação alternativa (Especialista)
    allow_no_change: false        # etapa opcional
    require_human_approval: true  # gate de aprovação humana
```

---

## 3. Anatomia de um `step`

| Campo | Obrigatório | O que faz |
|-------|:-----------:|-----------|
| `id` | ✅ | Identificador único da etapa (ex.: `2_planejamento_arquitetura`). |
| `action` | ✅ | A ação executada (ver [seção 4](#4-ações-disponíveis)). |
| `description` | ❌ | Texto humano do que a etapa faz — exibido no monitoramento detalhado. |
| `depends_on` | ❌ | Lista de `id`s que devem terminar antes desta etapa. |
| `inputs` | ❌ | Entradas: arquivos (`file:`) ou fontes (`source: gitlab_api`). |
| `context` | ❌ | Arquivos adicionais anexados ao prompt da IA. |
| `outputs` | ❌ | Arquivos que a IA deve gerar/gravar (`file:`). |
| `prompts` | ❌ | Instrução explícita da etapa (substitui o prompt padrão da ação). |
| `skill` | ❌ | Delega ao **Agente Principal** usando uma skill (`.iaw/skills/<nome>/SKILL.md`). |
| `subagent` | ❌ | Delega a um **Especialista isolado** (`.iaw/agents/<nome>/`). `agent:` é sinônimo. |
| `allow_no_change` | ❌ | Se `true`, a IA pode responder `SEM_ALTERACOES_NECESSARIAS` e pular a etapa. |
| `require_human_approval` | ❌ | Se `true`, o `iaw` pausa e pede aprovação antes de seguir. |
| `command` | ❌ | Comando shell (usado pela ação `run_terminal_command`). |
| `config` | ❌ | Parâmetros extras (ex.: `start_url` do `run_browser_harness`). |
| `sandbox` | ❌ | Caminhos bloqueados (`blocked_paths`), como `manage.py` e `.env`. |
| `integrations` | ❌ | Integrações da etapa (GitLab, relatório local). |

> O `iaw` injeta automaticamente, em **todas** as etapas de IA, o contexto
> canônico do projeto (`.iaw/stack.md` e `.iaw/contexto.md`) — **a menos que o
> step declare `context:` explicitamente** — além dos artefatos (`.md`) gerados
> nas etapas anteriores da tarefa. Assim a IA sempre enxerga as regras do projeto
> e o histórico acumulado.

---

## 4. Ações disponíveis

| Ação | O que faz |
|------|-----------|
| `ask_clarifying_questions` | A IA analisa requisitos e faz perguntas para fechar a regra de negócio. |
| `generate_artifact` | A IA gera um artefato (spec, diagnóstico, plano, rede de segurança). |
| `execute_ai_coding` | A IA escreve código (autônoma ou com gate). |
| `run_terminal_command` | Executa um comando shell (ex.: `pytest`). |
| `run_browser_harness` | Abre o navegador e captura screenshot (prova visual). |
| `generate_summary_and_publish` | Gera resumo, registra no relatório e (com `--create-mr`) abre o MR. |

---

## 5. Delegação: `skill` (Agente Principal) vs `subagent` (Especialista)

O `iaw` separa **taticamente** as etapas:

- **`skill:`** → executada pelo **Agente Principal**. Ideal para backend,
  planejamento, commits e formatação. Exemplos: `backend_tdd`, `sentry-fix`,
  `mr-format`, `generate-test`.

- **`subagent:`** (ou `agent:`) → **Especialista isolado** com restrição de
  persona. Use apenas para etapas altamente especializadas, como UI/Design System
  (`suap-frontend`) ou simulação externa de testes (`e2e-tester`).

```yaml
- id: 3a_materializacao_backend
  action: execute_ai_coding
  skill: backend_tdd        # Agente Principal

- id: 3b_materializacao_frontend
  action: execute_ai_coding
  subagent: suap-frontend   # Especialista isolado
```

- `skill` lê `.iaw/skills/<nome>/SKILL.md`.
- `subagent` lê `.iaw/agents/<nome>.md` (ou `.iaw/agents/<nome>/AGENT.md`).

Se a skill/subagente não existir, o `iaw` **não falha**: degrada para a skill
padrão (`default`), com aviso no prompt.

---

## 6. Ordenação e gates

- A ordem de execução é **topológica**, derivada de `depends_on`.
- Ciclos ou dependências inexistentes geram erro na hora de carregar o workflow.
- `require_human_approval: true` cria um **gate**: a CLI pausa e pergunta
  `Aprovar esta etapa e continuar?`.

---

## 7. Criação de Merge Request (opt-in)

Por padrão, **nenhum workflow cria MR**. A etapa `generate_summary_and_publish`
sempre gera o resumo e registra a atividade no relatório; o MR só é aberto com:

```bash
iaw run --workflow nova_feature --issue-id 4512 --create-mr
```

---

## 8. Monitoramento detalhado

Ao executar, o `iaw` exibe, para cada etapa:

- número da etapa e `id`;
- `action`;
- `description` (o que está sendo feito);
- delegação (`skill` ou `subagent`);
- entradas e saídas;
- indicação de gate de aprovação;
- resultado (sucesso/falha) e, em `--log`, o prompt e a saída da IA.

---

## 9. Exemplo mínimo

```yaml
name: meu_fluxo
description: "Exemplo mínimo."
version: "1.0"

steps:
  - id: 1_entender
    action: ask_clarifying_questions
    description: "Faz perguntas para esclarecer a regra de negócio."
    require_human_approval: true

  - id: 2_codar
    depends_on: [1_entender]
    action: execute_ai_coding
    description: "Implementa a solução."
    skill: backend_tdd

  - id: 3_testar
    depends_on: [2_codar]
    action: run_terminal_command
    description: "Roda os testes."
    command: "pytest -q"

  - id: 4_publicar
    depends_on: [3_testar]
    action: generate_summary_and_publish
    description: "Resumo + relatório (+ MR com --create-mr)."
    skill: mr-format
```

---

## 10. Workflows padrão

| Workflow | Objetivo | Delegação principal |
|----------|----------|---------------------|
| `nova_feature` | Nova funcionalidade (Spec-Driven) | `skill: backend_tdd` (backend), `subagent: suap-frontend` (frontend), `subagent: e2e-tester` (prova), `skill: mr-format` (consolidação). |
| `bug_fix` | Correção cirúrgica de bug | `skill: sentry-fix`, `skill: backend_tdd` (teste Red), `skill: mr-format`. |
| `refatoracao` | Refatoração segura | `skill: generate-test` + `subagent: e2e-tester` (rede de segurança), hooks de complexidade, `subagent: suap-frontend` (adaptação). |
