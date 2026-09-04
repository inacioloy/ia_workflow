# Plano de Implementação — `ia_workflow` (comando `iaw`)

> Fonte: investigação consolidada na conversa com o Gemini (25 turnos).
> Repositório: `https://github.com/inacioloy/ia_workflow` · Licença: **MIT**.

---

## 1. Problemática

- **Falta de padronização**: desenvolvedores usam IAs diferentes (Claude, OpenCode, Codex, Pi, etc.) de forma isolada e sem estrutura para evoluir o SUAP (Python/Django/PostgreSQL).
- **Alucinação arquitetural**: prompts ad-hoc sem contexto fazem a IA sugerir padrões/bibliotecas que violam as regras do projeto.
- **Desconexão burocrática**: o fluxo técnico ignora a necessidade de rastreabilidade institucional — vincular o trabalho a Issues/MRs no GitLab e ao relatório mensal.

## 2. Solução consolidada

Uma **CLI orquestradora em Python** (`ia_workflow`, comando `iaw`), instalada globalmente na máquina de cada dev, que:

1. Lê a pasta **`.iaw/`** (Context as Code) versionada dentro de cada projeto;
2. Orquestra a IA via **Graph Engineering** (workflows em YAML) + **Artifact-Driven Development** (artefatos validados antes do código);
3. Integra **GitLab** (Issue → artefato → código → MR);
4. Gera o **relatório mensal** automaticamente;
5. É **agnóstica de motor de IA** (Pi Coding, Aider, Claude etc.).

## 3. Decisões tomadas

| # | Tema | Decisão |
|---|------|---------|
| 1 | Nome | Repositório `ia_workflow`, comando CLI **`iaw`** |
| 2 | Pasta de contexto | **`.iaw/`** (versionada no Git, com README auto-gerado) |
| 3 | Config global | `~/.config/ia_workflow/config.toml` (token GitLab, engine, nome, caminho do relatório) |
| 4 | Estrutura `.iaw/` | `workflows/`, `skills/`, `templates/`, `stack.md`, `README.md`, `evals/` |
| 5 | Comandos | `setup`, `init`, `analyze`, `start-task`, `run`, `finish-task`, `status`, `config set`, `skill add/update`, `eval` |
| 6 | Workflows por cenário | `bug_fix`, `nova_feature`, `refatoracao` |
| 7 | Motor agnóstico | Padrão Adapter: `PiCodingEngine`, `AiderEngine`, `AntigravityEngine` (config `default_engine`) |
| 8 | Metodologia | 5 etapas da Attekita: Entendimento → Planejamento → Código → Prova → Consolidação |
| 9 | Artefatos transitórios | Pasta `.iaw_workspace/` (limpa no final da task) |
| 10 | Relatório mensal | Fora do repo, em diretório global (`relatorio_path`), 1 arquivo/mês (`agosto_2026.md`) |
| 11 | Licença | **MIT** |
| 12 | Monitoramento | `--detach`/`--notify`, notificações desktop/webhook, comando `iaw status` |
| 13 | Permissões | 3 camadas: config global (`auto_write_files`), `stack.md` (sandbox), workflow (`require_human_approval`) |
| 14 | Segurança | Branch isolation, contexto restrito, rollback (`git reset --hard`), CLI **só cria MR** (nunca faz merge) |
| 15 | Controle de qualidade | Evals com Golden Dataset + LLM-as-a-Judge, via GitLab CI/CD + pre-commit hook |
| 16 | Arquitetura final | **CLI independente (Cenário 2)** como alvo; MVP pode começar como extensão do Pi (Cenário 1) |
| 17 | Especialista por etapa | Step YAML aceita `skill:`/`agent:` (lê `.iaw/skills/<nome>/SKILL.md` ou `.iaw/agents/`) |
| 18 | Etapa opcional | `allow_no_change: true` → a IA responde `SEM_ALTERACOES_NECESSARIAS` e o orquestrador pula a etapa |
| 19 | Log de execução | `iaw run --log` mostra prompt, contexto e saída da IA em cada etapa |
| 20 | Tarefa explícita | `iaw run --issue-id <id>` (alias `--task`) indica a Issue sem depender da branch |
| 21 | Execução sem MR | `iaw run` por padrão não cria MR; use `iaw run --create-mr` para abrir |
| 22 | Janela de contexto | `context_max_chars`/`context_max_file_chars` limitam o conteúdo anexado (engine-agnóstico) |
| 23 | Reuso de sessão | Uma instância de engine por execução; Antigravity continua a conversa (`--conversation`) entre etapas |
| 24 | Análise de contexto | `iaw analyze` gera stack.md/contexto.md a partir do fingerprint do projeto (com fallback heurístico) |
| 25 | Skill padrão | `.iaw/skills/default/` é criada no `init`; skill/agent ausente degrada para a padrão (não falha) |

**Stack técnica**: Python ≥3.10, Typer, Rich, python-gitlab, tomli/tomli-w, PyYAML, Playwright, plyer/notify2.

## 4. Fases de implementação

### Fase 1 — Fundação (CLI + Config Global) ✅ em andamento
- [x] `pyproject.toml` com entrypoint `iaw` e dependências
- [x] Estrutura do pacote `ia_workflow/`
- [x] `config_manager.py` → ler/escrever `~/.config/ia_workflow/config.toml`
- [x] Interface `AIEngine` (abstract) + `PiCodingEngine` (RPC/JSONL) + `AiderEngine` (subprocess)
- [x] `cli.py` (Typer + Rich) com `setup` e `config`

### Fase 2 — Context as Code + GitLab (Task-First) ✅ concluída
- [x] `iaw init` (wizard interativo, gera `.iaw/` + `stack.md` + `README.md` + workflows)
- [x] `iaw start-task <id>` (python-gitlab: baixa Issue → gera `1_requisitos_validados.md` em `.iaw_workspace/`)
- [x] `gitlab_client.py` (cliente python-gitlab com tratamento de erro)
- [x] Análise de migração das pastas do SUAP → `docs/MIGRACAO_SUAP.md`

### Fase 3 — Graph Engineering + Skills ✅ concluída
- [x] Parser de workflows YAML (`workflow_parser.py` com `depends_on` + ordem topológica)
- [x] `iaw run` (orquestrador `runner.py`: ações de engine, comandos de terminal, gates de aprovação)
- [x] `iaw skill list/add/update` (carregador de skills de repo central, local ou Git)

### Fase 4 — Prova Visual + relatório ✅ concluída
- [x] Browser Harness (`browser_harness.py` com Playwright headless + screenshot)
- [x] `iaw finish-task` (git diff → resumo via IA → cria MR no GitLab → append no relatório mensal)
- [x] Relatório mensal (`reports.py`, arquivo por mês em `relatorio_path`)
- [x] `iaw status` (registro de tarefas em `state.py`) + notificações (`notify.py`)

### Fase 5 — Evals / LLMOps (qualidade) ✅ concluída
- [x] `iaw eval <skill|all>` (Golden Dataset em `.iaw/evals/<skill>/<caso>/` + LLM-as-a-Judge)
- [x] Baseline por skill (`.iaw/evals/.baseline.json`) com bloqueio de regressão
- [x] `iaw install-hooks` (hook pre-commit que roda evals das skills alteradas)
- [x] Template de CI (`.iaw/templates/gitlab-ci-evals.yml`)

### Fase 6 — Gestão de work items no GitLab ✅ concluída
- [x] `iaw create --task/--issue [--demanda]` (`work_items.py`): cria work item com assignee = usuário e labels (`bug`/`demandas` + mês/ano)
- [x] `iaw relatorio tasks <MÊS/ANO>`: lista fechadas do mês divididas em task geral/erro/demanda (+ `--incluir-abertos`)
- [x] `iaw create --recording` + `recorder.py`: grava janelas ativas (Windows/ctypes, Linux/xdotool) e `iaw finish-task` fecha a task com resumo sugerido pela IA

## 5. Estrutura de diretórios (alvo)

```
ia_workflow/                      # repositório da ferramenta
├── pyproject.toml
├── README.md
├── LICENSE
├── docs/PLANO.md
└── ia_workflow/                  # pacote Python
    ├── __init__.py
    ├── cli.py
    ├── config_manager.py
    ├── gitlab_client.py          # Fase 2
    ├── workflow_parser.py        # Fase 3
    ├── skills.py                 # Fase 3
    ├── expertise.py              # skill/agent por etapa (Fase 3)
    ├── analyzer.py               # iaw analyze (stack/contexto a partir do projeto)
    ├── reports.py                # Fase 4
    └── engines/
        ├── __init__.py
        ├── base.py               # AIEngine (ABC)
        ├── pi_coding.py          # Pi Coding via RPC/JSONL
        ├── aider.py              # Aider via subprocess
        └── antigravity.py        # Antigravity via CLI agy (--print)

<projeto>/.iaw/                   # Context as Code (versionado no projeto)
├── README.md                     # auto-gerado
├── stack.md                      # regras rígidas de stack
├── workflows/                    # grafos YAML (bug_fix, nova_feature, refatoracao)
├── skills/                       # skills modulares (SKILL.md)
├── agents/                       # subagentes especializados (importados do legado)
├── experts/                      # experts de domínio (Claude Code commands)
├── templates/                    # templates de artefatos
└── evals/                        # Golden Dataset

~/.config/ia_workflow/            # config global (por máquina)
├── config.toml
└── reports/                      # relatórios mensais (fora do Git)
```
