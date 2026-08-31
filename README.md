# ia_workflow

**CLI de orquestração de IA para desenvolvimento assistido — IFRN.**

O `ia_workflow` (comando **`iaw`**) padroniza o uso de IA em equipe, independente
da ferramenta de cada desenvolvedor (Pi Coding, Aider, Claude, etc.), combinando
**Artifact-Driven Development** + **Graph Engineering** e integrando **GitLab** e o
**relatório mensal do PGD**.

## Por quê?

- ❌ Sem padrão: cada dev usa uma IA diferente, com prompts ad-hoc.
- ❌ Alucinação arquitetural: a IA sugere padrões/bibliotecas que violam o projeto.
- ❌ Burocracia manual: atrelar código a Issues/MRs e relatórios na mão.

- ✅ **Context as Code**: as regras vivem em `.iaw/`, versionadas no projeto.
- ✅ **Artifact-Driven**: a IA valida artefatos antes de gerar código.
- ✅ **Graph Engineering**: workflows YAML orquestram as etapas com gates.
- ✅ **Task-First**: tudo começa em uma Issue do GitLab e termina no PGD.

## Instalação

```bash
git clone git@github.com:inacioloy/ia_workflow.git
cd ia_workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # básico
pip install -e '.[browser]'   # + Playwright (prova visual)
```

## Uso rápido

```bash
iaw setup                      # configura token GitLab, engine, nome, caminho PGD
iaw init                       # cria a pasta .iaw/ no projeto atual

iaw start-task 4512            # baixa a Issue do GitLab e gera o artefato
iaw run --workflow bug_fix --issue-id 4512   # orquestra a IA (indicando a tarefa)
iaw run --workflow bug_fix --issue-id 4512 --log   # idem, com log de execução da IA
iaw run --workflow bug_fix --issue-id 4512 --no-publish   # idem, sem MR/PGD
iaw finish-task                # resumo + MR + relatório PGD
```

## Motores de IA suportados

| Motor | Como funciona | Configurar |
|-------|---------------|-----------|
| **Pi Coding** | RPC/JSONL (`pi --mode rpc`) | `iaw config set default_engine pi-coding` |
| **Aider** | subprocess (`aider --message`) | `iaw config set default_engine aider` |
| **Antigravity** | CLI oficial `agy --print` (OAuth, **sem API key**) | `iaw config set default_engine antigravity` |

Para Antigravity, escolha o modelo com `iaw config set default_model <id>`
(ex.: `gemini-3.1-pro-high`). Veja os modelos com `agy models`.

**Janela de contexto** (funciona com qualquer motor):

```bash
iaw config set context_max_chars 80000        # limite total anexado ao prompt
iaw config set context_max_file_chars 20000   # limite por arquivo
```

Arquivos acima do limite são truncados/omitidos com aviso no prompt — evita
estourar a janela do modelo quando o `.iaw/` e os artefatos crescem.

## Conceitos-chave

| Conceito | O que é |
|----------|---------|
| **Context as Code** | Regras do projeto em `.iaw/` (stack.md, contexto.md) |
| **Artifact-Driven** | Artefatos validados antes do código (requisitos → spec → código) |
| **Graph Engineering** | Workflows YAML com `depends_on` e gates de aprovação |
| **Skills / Agents** | Pacotes reutilizáveis em `.iaw/skills/` e `.iaw/agents/` |
| **Skill padrão** | `.iaw/skills/default/` é criada no `init` e usada quando uma skill não existe |
| **Especialista por etapa** | Cada step do workflow pode usar `skill:`/`agent:` (ex.: frontend-suap) |
| **Etapa opcional** | `allow_no_change: true` deixa a IA pular a etapa quando não há trabalho |
| **Task-First** | Fluxo ancorado em Issues do GitLab |
| **Evals / LLMOps** | Golden Dataset + LLM-as-a-Judge contra regressão |

### Especialistas por etapa (`skill:` / `agent:`)

```yaml
# .iaw/workflows/bug_fix.yaml
steps:
  - id: 1_analisar_erro
    action: generate_artifact
    skill: bug-analyst            # .iaw/skills/bug-analyst/SKILL.md

  - id: 2_corrigir_frontend
    action: execute_ai_coding
    skill: frontend-suap          # segue o design system do SUAP
    allow_no_change: true         # pula se não houver ajuste de frontend
```

## Comandos

| Comando | Descrição |
|---------|-----------|
| `iaw setup` | Configura credenciais globais |
| `iaw config set/get/list` | Gerencia a config global |
| `iaw init [--analyze]` | Cria/reconfigura `.iaw/` (com `--analyze`, preenche stack/contexto via IA) |
| `iaw analyze [--dry-run]` | Analisa o projeto e preenche stack.md/contexto.md (IA) |
| `iaw start-task <id>` | Baixa Issue do GitLab e gera artefato inicial |
| `iaw run [--workflow <n>] [--issue-id <id>] [--log] [--no-publish]` | Orquestra o workflow (tarefa, log e/ou sem publicar MR/PGD) |
| `iaw finish-task` | Abre MR e atualiza o relatório PGD |
| `iaw status` | Acompanha execuções |
| `iaw skill list/create/add/update` | Gerencia skills (criar, instalar, atualizar) |
| `iaw import-legacy [--dry-run]` | Centraliza skills/agents do legado em `.iaw/` |
| `iaw eval <skill\|all>` | Evals de qualidade (Golden Dataset) |
| `iaw install-hooks` | Hook pre-commit que bloqueia regressão |
| `iaw version` | Exibe a versão |

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [Guia do Desenvolvedor](docs/GUIA_DESENVOLVEDOR.md) | ⭐ Uso completo: conceitos, config, workflows, PGD, monitoramento |
| [Exemplos de Fluxos Dev](docs/exemplos_fluxos_dev.md) | Passo a passo no SUAP (bug e nova funcionalidade) + como chamar o `iaw` |
| [Plano de Implementação](docs/PLANO.md) | Fases, decisões e arquitetura |
| [Migração do SUAP](docs/MIGRACAO_SUAP.md) | Análise das pastas legadas → `.iaw/` |
| [Evals](docs/EVALS.md) | Como testar skills/agents (Golden Dataset) |

## Estrutura

```
ia_workflow/                 # repositório da ferramenta
├── pyproject.toml
├── ia_workflow/             # pacote Python
│   ├── cli.py               # comandos (Typer)
│   ├── runner.py            # orquestrador de workflows
│   ├── workflow_parser.py   # parser YAML (grafos)
│   ├── evals.py             # Golden Dataset + LLM-as-a-Judge
│   ├── skills.py            # gerenciador de skills
│   ├── gitlab_client.py     # integração GitLab
│   ├── publish.py           # finish-task (MR + PGD)
│   ├── reports.py           # relatório mensal PGD
│   └── engines/             # Pi Coding (RPC), Aider e Antigravity (subprocess/CLI)
└── docs/                    # documentação

<projeto>/.iaw/              # Context as Code (versionado no projeto)
├── stack.md / contexto.md
├── workflows/  skills/  agents/  templates/  hooks/  evals/
```

## Licença

MIT — veja [LICENSE](LICENSE).
