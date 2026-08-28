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
iaw run --workflow bug_fix     # orquestra a IA pelo workflow
iaw finish-task                # resumo + MR + relatório PGD
```

## Conceitos-chave

| Conceito | O que é |
|----------|---------|
| **Context as Code** | Regras do projeto em `.iaw/` (stack.md, contexto.md) |
| **Artifact-Driven** | Artefatos validados antes do código (requisitos → spec → código) |
| **Graph Engineering** | Workflows YAML com `depends_on` e gates de aprovação |
| **Skills / Agents** | Pacotes reutilizáveis em `.iaw/skills/` e `.iaw/agents/` |
| **Task-First** | Fluxo ancorado em Issues do GitLab |
| **Evals / LLMOps** | Golden Dataset + LLM-as-a-Judge contra regressão |

## Comandos

| Comando | Descrição |
|---------|-----------|
| `iaw setup` | Configura credenciais globais |
| `iaw config set/get/list` | Gerencia a config global |
| `iaw init` | Cria/reconfigura a pasta `.iaw/` |
| `iaw start-task <id>` | Baixa Issue do GitLab e gera artefato inicial |
| `iaw run [--workflow <n>]` | Orquestra o workflow YAML |
| `iaw finish-task` | Abre MR e atualiza o relatório PGD |
| `iaw status` | Acompanha execuções |
| `iaw skill list/add/update` | Gerencia skills |
| `iaw import-legacy [--dry-run]` | Centraliza skills/agents do legado em `.iaw/` |
| `iaw eval <skill\|all>` | Evals de qualidade (Golden Dataset) |
| `iaw install-hooks` | Hook pre-commit que bloqueia regressão |
| `iaw version` | Exibe a versão |

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [Guia do Desenvolvedor](docs/GUIA_DESENVOLVEDOR.md) | ⭐ Uso completo: conceitos, config, workflows, PGD, monitoramento |
| [Cenários de Teste](docs/cenarios.md) | Passo a passo no SUAP (bug e nova funcionalidade) + como chamar o `iaw` |
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
│   └── engines/             # Pi Coding (RPC) e Aider (subprocess)
└── docs/                    # documentação

<projeto>/.iaw/              # Context as Code (versionado no projeto)
├── stack.md / contexto.md
├── workflows/  skills/  agents/  templates/  hooks/  evals/
```

## Licença

MIT — veja [LICENSE](LICENSE).
