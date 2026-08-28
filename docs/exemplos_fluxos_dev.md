# Exemplos de Fluxos de Dev — `iaw` no SUAP

> Passo a passo prático para testar o `iaw` no projeto SUAP, cobrindo uma
> **issue de bug** e uma **nova funcionalidade**.

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
iaw run --workflow bug_fix       # iaw chama o pytest que estiver no PATH
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
#   → URL: https://gitlab.ifrn.edu.br
#   → projeto: cosinf/suap
#   → motor: pi-coding
#   → seu nome (para o PGD)

# 2. Preparar o SUAP
cd /home/inacio/workspace/suap
source .venv/bin/activate
iaw init                 # cria .iaw/ (stack: Python, Django, PostgreSQL; testes: pytest)
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
iaw run --workflow bug_fix
```

| Etapa | Ação | Você precisa? |
|-------|------|---------------|
| `1_analisar_erro` | IA gera o diagnóstico → `.iaw_workspace/1_diagnostico_bug.md` | **Aprovar** (gate) |
| `2_corrigir_codigo` | IA corrige o código | Não (autônoma) |
| `3_prova_testes` | Roda `pytest -q` | Não |
| `4_abrir_mr` | Resumo + **abre o MR** + registra no PGD | Não |

### 5. Acompanhe

```bash
iaw status            # histórico de execuções
```

**Resultado esperado**: MR aberto no GitLab (com `Closes #4512`) e atividade
registrada em `~/.config/ia_workflow/reports/<mes>_<ano>.md`.

> Alternativa manual: se preferir controlar a publicação, use `iaw finish-task`
> (ou `--no-mr` para só atualizar o relatório).

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

### 3. Prepare a prova visual (etapa 4b)

```bash
# Playwright + chromium (se ainda não instalou)
pip install -e '.[browser]' && playwright install chromium

# SUAP rodando em outro terminal:
python manage.py runserver
```

### 4. Orquestra o workflow completo

```bash
iaw run --workflow nova_feature --notify
```

| Etapa | Ação | Você precisa? |
|-------|------|---------------|
| `1_entendimento_problema` | IA faz perguntas para fechar a regra de negócio | **Aprovar** |
| `2_planejamento_arquitetura` | IA gera a spec técnica (models/views) | **Aprovar** |
| `3_materializacao_codigo` | IA escreve o código | Não |
| `4a_prova_testes` | Roda `pytest -q` | Não |
| `4b_prova_visual_browser` | Abre o navegador e tira **screenshot** da tela | Não |
| `5_consolidacao_relatorio` | Resumo + **MR** + **PGD** | Não |

`--notify` avisa no desktop ao terminar — você pode sair da frente do
computador **após aprovar a spec na etapa 2**.

---

## Regras que valem para os dois cenários

- A IA **nunca faz merge** — só abre o MR; o merge é revisão humana no GitLab.
- Se testes/validação falham, o fluxo **interrompe** (fail-safe).
- Você corrige **documentos** (artefatos) antes do código, não o código.
- Tudo fica rastreável: Issue → artefatos → código → MR → PGD.

## Fluxo mental (resumo)

```
git branch → iaw start-task → REVISAR artefato → iaw run (aprovando gates)
           → MR automático → PGD registrado → code review humano no GitLab
```

---

## Solução de problemas rápidos

| Erro | Causa | Solução |
|------|-------|---------|
| `Token do GitLab não configurado` | `iaw setup` não foi feito | `iaw setup` |
| `Comando 'pi' não encontrado` | motor fora do PATH | instale o Pi ou `iaw config set default_engine aider` |
| `Playwright não está instalado` | extra `browser` ausente | `pip install -e '.[browser]'` + `playwright install chromium` |
| Etapa 4b falha | SUAP não está em `localhost:8000` | `python manage.py runserver` e rode de novo |
