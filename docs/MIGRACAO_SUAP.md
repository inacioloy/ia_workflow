# Análise de Migração — SUAP → `.iaw/` (ia_workflow)

> Objetivo: remover os diretórios de configuração de IA espalhados no SUAP e
> centralizar tudo em `.iaw/`, gerenciado pelo `iaw`.
> Data da análise: 2026-08-28.

---

## 1. Inventário atual (o que existe em cada pasta)

| Local | Conteúdo | Tamanho |
|-------|----------|---------|
| `AGENTS.md` (raiz) | Fonte única de orientação de agentes: comandos, arquitetura, guardrails, skills, subagents, seção OpenCode | 120 linhas |
| `CLAUDE.md` (raiz) | Notas específicas do Claude Code (importa `AGENTS.md`) + hooks/MCP | 23 linhas |
| `CONTEXT.md` (raiz) | Domínio e decisões: atores, subsistemas, invariantes, integrações, tabus | 64 linhas |
| `GEMINI.md` (raiz) | Overview simples para Gemini | 37 linhas |
| `.agents/skills/` | **18 skills** (fonte da verdade, formato `SKILL.md` + frontmatter) | 664K |
| `.agents/documentador/` | 7 templates de documentação (FLUXO, FRONTEIRA, GLOSSARIO, HLA, MODELO_DADOS…) | — |
| `.claude/agents/` | 5 subagentes (documentador, documentador-usuario, e2e-tester, security-reviewer, suap-frontend) | 232K |
| `.claude/commands/suap/` | 3 "experts" de domínio (ponto, rsc-docente, setor) | — |
| `.claude/hooks/` | 3 scripts Python (check_complexity, register_mr_time_spent + teste) | 687 linhas |
| `.claude/skills/` | 5 symlinks → `.agents/skills/` | — |
| `.claude/settings.json` | Config de hooks (PostToolUse/PreToolUse) | — |
| `.claude/specs/` | 1 spec MCP (demandas) | — |
| `.claude/launch.json` | Config de debug | — |
| `.gitlab/` | CODEOWNERS, issue/MR templates, changelog_config, agents | 52K |
| `.gitlab-ci.yml` (raiz) | Pipeline CI (fora de `.gitlab/`) | 37K |
| `.junie/` | **vazia** (só `plans/` vazio) | — |
| `.opencode/agent/` | 6 subagentes (formato TOML) | 88K |
| `.opencode/plugin/` | 3 plugins TS (check-complexity, pre-commit, register-mr-time-spent) | — |

## 2. As 18 skills (`.agents/skills/`)

| Skill | Propósito |
|-------|-----------|
| `sentry-fix` | Corrige erro do Sentry ponta-a-ponta (fetch→fix→branch→testes→pre-commit→push→MR) |
| `tdd` → `backend_tdd` | Loop red-green-refactor, testes de integração via interface pública (pytest) |
| `generate-test` | Gera testes Django/pytest para um MR (CI-ready) |
| `generate-docstrings` | Reescreve docstrings pt-BR (Google style) nas defs tocadas |
| `code-review` | Revisão multi-linguagem de PRs (assets + reference + scripts) |
| `mr-format` | Padroniza título/descrição de MR (convenção `[module]`) |
| `migration-check` | Verifica migrações Django |
| `carga-horaria` | Mede esforço real da tarefa (via `register_mr_time_spent.py --horas`) |
| `semble-search` | Busca semântica de código via `semble` |
| `pre-commit` | Documenta os checks automáticos (ruff→pre-commit) |
| `behave-feature-generator` | Gera `.feature` behave |
| `avaliacao-integrada` | Avaliação integrada |
| `concurso_publico` | Especialista em concurso público |
| `caveman` / `caveman-commit` / `caveman-review` / `caveman-compress` / `caveman-help` | Modos de resposta ultra-comprimida (economia de tokens) |

## 3. É possível centralizar? **Sim, com 3 níveis de viabilidade**

### ✅ Nível 1 — Centralizável 100% (vira `.iaw/`)

| Origem | Destino `.iaw/` | Observação |
|--------|-----------------|------------|
| `.agents/skills/` | `.iaw/skills/` | Já é a "fonte da verdade" (`.claude/skills` são symlinks) |
| `.claude/agents/` + `.opencode/agent/` | `.iaw/agents/` | Mesmos agentes em 2 formatos → 1 formato canônico |
| `.claude/hooks/*.py` | `.iaw/hooks/` | Scripts Python são reutilizados pelos plugins |
| `.claude/commands/suap/*.md` | `.iaw/agents/` (ou `experts/`) | Especialistas de domínio |
| `.agents/documentador/` | `.iaw/templates/documentador/` | Templates de docs |
| `AGENTS.md` + `CLAUDE.md` | `.iaw/stack.md` | Regras técnicas consolidadas |
| `CONTEXT.md` + `GEMINI.md` | `.iaw/contexto.md` | Domínio e decisões |

### ⚠️ Nível 2 — Centralizável com adaptador (tool-shim gerado)

Estes precisam ficar em caminho fixo para a ferramenta descobrir, mas o **conteúdo** pode ser gerado/importado de `.iaw/`:

| Caminho fixo (nativo da ferramenta) | Gerado a partir de `.iaw/` |
|-------------------------------------|---------------------------|
| `AGENTS.md` (OpenCode lê nativamente) | `.iaw/stack.md` (shim `@.iaw/stack.md`) |
| `CLAUDE.md` (Claude Code lê nativamente) | shim que importa `.iaw/stack.md` |
| `.claude/skills/*` | symlinks → `.iaw/skills/*` (auto-criados) |
| `.opencode/agent/*`, `.opencode/plugin/*` | gerados de `.iaw/agents/*` + `.iaw/hooks/*` |
| `.claude/settings.json` | gerado de `.iaw/hooks/*` |

### ❌ Nível 3 — **NÃO** pode sair de `.gitlab/` (consumido pela UI/API do GitLab)

Estes são lidos nativamente pelo GitLab e **não** podem ser movidos para `.iaw/`:

- `.gitlab/CODEOWNERS` — o GitLab exige este caminho para proteção de branch/revisores.
- `.gitlab/issue_templates/*` e `.gitlab/merge_request_templates/*` — a UI do GitLab só lê `.gitlab/`.
- `.gitlab/changelog_config.yml` — convenção do GitLab Changelog.
- `.gitlab-ci.yml` (raiz) — o pipeline é descoberto na raiz.

**Estratégia**: manter `.gitlab/` como está (são templates nativos do GitLab, não "config de IA"), ou gerar a partir de `.iaw/templates/gitlab/` via `iaw sync`. Na prática, `.gitlab/` **não é config de IA** — não entra no escopo de centralização do `iaw`.

### `.junie/` — removível agora (está vazio)

## 4. Arquitetura alvo

```
<projeto>/                         # ex.: suap
├── .iaw/                          # ← ÚNICA fonte da verdade (versionada)
│   ├── README.md                  # auto-gerado
│   ├── stack.md                   # ← AGENTS.md + CLAUDE.md
│   ├── contexto.md                # ← CONTEXT.md + GEMINI.md
│   ├── workflows/                 # bug_fix.yaml, nova_feature.yaml, refatoracao.yaml
│   ├── skills/                    # ← .agents/skills/*
│   ├── agents/                    # ← .claude/agents + .opencode/agent (formato canônico)
│   ├── templates/                 # artefatos + documentador + gitlab
│   ├── hooks/                     # ← .claude/hooks/*.py
│   └── evals/                     # golden dataset (Fase 5)
│
├── AGENTS.md                      # shim fino (1 linha) → aponta para .iaw/stack.md
├── CLAUDE.md                      # shim fino → @.iaw/stack.md + notas de hooks
├── .claude/skills/                # symlinks gerados → .iaw/skills/
├── .opencode/                     # gerado por iaw sync a partir de .iaw/
└── .gitlab/                       # PERMANECE (nativo do GitLab)
```

## 5. Plano de migração (etapas)

1. **`iaw init`** no SUAP → cria a estrutura `.iaw/` completa.
2. **`iaw import-legacy`** ✅ → copia skills/agents/hooks dos diretórios antigos para `.iaw/` e normaliza formatos (não apaga nada).
3. **`iaw sync`** → gera os shims/symlinks nas posições nativas de cada ferramenta.
4. **Validação** → conferir que OpenCode/Claude Code continuam descobrindo skills e agents.
5. **Remoção** → apagar `.agents/`, `.claude/agents`, `.claude/commands`, `.opencode/agent`, `.opencode/plugin`, `.junie/` (após validação).
