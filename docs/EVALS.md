# Evals (LLMOps) — como testar skills e agentes

O `iaw` garante que mudanças em skills/agentes **não regridam** a qualidade,
usando um **Golden Dataset** + **LLM-as-a-Judge**.

## Estrutura do Golden Dataset

Cada skill pode ter casos de teste em `.iaw/evals/<skill>/<caso>/`:

```
.iaw/evals/
├── .baseline.json          # scores de referência (gerado automaticamente)
└── django_security/
    ├── caso_sql_injection/
    │   ├── input.md         # cenário (ex: código com bug)
    │   └── expected.md      # critério esperado (rubrica do juiz)
    └── caso_idor/
        ├── input.md
        └── expected.md
```

- **`input.md`** — o cenário dado à skill (ex.: uma view do Django com SQL injection).
- **`expected.md`** — o que a saída da skill **deve** conter/atingir. É a rubrica
  que o juiz usa para dar PASS/FAIL.

## Comandos

```bash
# Roda os evals de uma skill (cria o baseline na 1ª vez)
iaw eval django_security

# Roda todas as skills com Golden Dataset
iaw eval all

# Reporta sem bloquear (útil para CI/investigação)
iaw eval django_security --no-block

# Aceita o score atual como novo baseline (mudança intencional)
iaw eval django_security --update-baseline
```

## Como funciona

1. **Executor**: a CLI roda a skill (SKILL.md + `input.md`) no motor de IA.
2. **LLM-as-a-Judge**: a saída é enviada a um juiz com a rubrica (`expected.md`)
   e a instrução de responder **apenas** `PASS` ou `FAIL`.
3. **Baseline**: o score (acerto %) é comparado com o baseline salvo em
   `.iaw/evals/.baseline.json`. Se cair → **regressão** (exit code 1).

## Automação

- **Pre-commit** (`iaw install-hooks`): antes de cada `git commit`, o hook
  detecta as skills alteradas em `.iaw/skills/` e roda os evals delas. Se
  regredir, o commit é **abortado**.
- **GitLab CI**: o template em `.iaw/templates/gitlab-ci-evals.yml` roda
  `iaw eval all` quando arquivos em `.iaw/` mudam, bloqueando o MR se o score
  cair.

## Criando um caso de eval

```bash
mkdir -p .iaw/evals/minha_skill/caso_bug_qualquer
# input.md  → o cenário
# expected.md → a rubrica (o que a skill deve produzir)
```

> **Fail-safe**: se o juiz não responder `PASS`/`FAIL` de forma clara, o caso
> é considerado `FAIL` (conservador — não deixa regressão passar).
