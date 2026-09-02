# Guia do Desenvolvedor — IA Workflow (`iaw`)

> Guia completo para desenvolvedores usarem o `iaw` no dia a dia.
> Leitura recomendada antes do primeiro uso. Complementa o [README](../README.md),
> os [exemplos de fluxos de dev](exemplos_fluxos_dev.md) e o [plano de implementação](PLANO.md).

---

## 1. Conceitos-chave

### 1.1 Context as Code (a pasta `.iaw/`)
As regras do projeto ficam **versionadas no próprio repositório**, dentro de `.iaw/`.
A IA lê essa pasta antes de qualquer ação, o que elimina a "alucinação arquitetural"
(ex.: sugerir Flask num projeto Django).

```
.iaw/
├── stack.md        # stack, comandos e guardrails rígidos
├── contexto.md     # domínio: atores, subsistemas, invariantes
├── workflows/      # grafos YAML (bug_fix, nova_feature, refatoracao)
├── skills/         # skills modulares (SKILL.md)
├── agents/         # subagentes especializados
├── templates/      # templates de artefatos + CI
├── hooks/          # scripts de enforcement (complexidade, pre-commit)
└── evals/          # Golden Dataset (testes de qualidade)
```

### 1.2 Artifact-Driven Development
A IA **não** recebe "crie o módulo X" e sai codando. O fluxo é quebrado em
**artefatos** (documentos) que precisam ser validados antes de avançar:

```
Issue → 1_requisitos_validados.md → (aprovação) → 2_especificacao_tecnica.md
      → (aprovação) → código → testes → MR → relatório
```

Se a IA entendeu errado a regra de negócio, você corrige o **documento**, não o código.

### 1.3 Graph Engineering (workflows YAML)
Cada workflow é um **grafo** de etapas (nós) com dependências (`depends_on`).
A CLI orquestra a execução e **bloqueia** o avanço se uma etapa falhar.

### 1.4 Skills e Agents
- **Skill** = pacote reutilizável (`SKILL.md` + ferramentas) com papel, gatilho e ação.
- **Agent** = subagente especializado (documentador, security-reviewer, e2e-tester...).

### 1.5 Task-First
O trabalho começa por uma **Issue do GitLab** (`iaw start-task <id>`), não por um
prompt solto. Tudo fica rastreável: Issue → artefatos → código → MR → relatório.

### 1.6 Evals / LLMOps
Skills e agents são testados contra um **Golden Dataset** com um **LLM-as-a-Judge**.
Se uma mudança piora a skill, o commit/MR é **bloqueado**.

---

## 2. Instalação e configuração

### 2.1 Instalar

```bash
git clone git@github.com:inacioloy/ia_workflow.git
cd ia_workflow
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # básico
pip install -e '.[browser]' # + Playwright (prova visual)
pip install -e '.[notify]'  # + notificações desktop
```

### 2.2 Configuração inicial (uma vez por máquina)

```bash
iaw setup
```

O assistente pergunta:
- **Token do GitLab** (Personal Access Token)
- **URL do GitLab** (ex.: `https://gitlab.com`)
- **Projeto padrão** (ex.: `cosinf/suap`)
- **Motor de IA** (`pi-coding`, `aider` ou `antigravity`)
- **Seu nome** (para o relatório)
- **Diretório dos relatórios** (padrão: `~/.config/ia_workflow/reports`)

### 2.3 Config global vs. local

| Escopo | Local | O que guarda |
|--------|-------|--------------|
| **Global** (máquina) | `~/.config/ia_workflow/config.toml` | token, engine, nome, caminho do relatório |
| **Local** (projeto) | `./.iaw/` | stack, workflows, skills, contexto |

Gerencie a config com:

```bash
iaw config set <chave> <valor>
iaw config get <chave>
iaw config list
```

Chaves: `gitlab_url`, `gitlab_token`, `gitlab_project`, `default_engine`,
`default_model`, `default_agent`, `dev_name`, `relatorio_path`,
`auto_write_files`, `antigravity_skip_permissions`, `skill_repo`,
`context_max_chars`, `context_max_file_chars`.

### 2.4 Preparar um projeto

```bash
cd <projeto>
iaw init              # cria .iaw/ (rápido; stack/contexto ficam simples)
iaw init --analyze    # cria .iaw/ E já preenche stack.md/contexto.md com a IA
```

Por padrão o `iaw init` **não** executa a análise — ele cria o `.iaw/` com a
estrutura completa, os 3 workflows padrão e a **skill padrão**
(`.iaw/skills/default/SKILL.md`), deixando `stack.md`/`contexto.md` em versão
simples e avisando como preenchê-los. Para já gerar os documentos ricos na
inicialização, use `--analyze` (ou rode `iaw analyze` depois — veja a seção 2.7).
**Faça commit do `.iaw/`** — é a fonte da verdade do time.

### 2.5 Usando o Antigravity como motor (sem API key)

O Antigravity não expõe chave de API; a integração usa o **CLI oficial** (`agy`),
já autenticado via OAuth na sua máquina. Para configurá-lo:

```bash
# 1. Garanta que o CLI está no PATH
which agy

# 2. Aponte o iaw para ele
iaw config set default_engine antigravity

# 3. (opcional) escolha o modelo/agente
iaw config set default_model gemini-3.1-pro-high
iaw config set default_agent ""

# 4. (opcional) o motor já aprova ferramentas no modo --print; para desligar:
iaw config set antigravity_skip_permissions false
```

O motor roda `agy --print --output-format json` no diretório do projeto e usa
`--add-dir` para que o agente enxergue/edite os arquivos com caminhos absolutos.
Modelos disponíveis: `agy models`.

### 2.6 Janela de contexto (engine-agnóstico)

Para evitar estourar a janela do modelo quando o `.iaw/` e os artefatos crescem,
o `iaw` limita o conteúdo anexado ao prompt — **independente do motor**:

```bash
iaw config set context_max_chars 80000        # total máximo anexado
iaw config set context_max_file_chars 20000   # máximo por arquivo
```

- Arquivos acima do limite são **truncados** (com aviso `[arquivo truncado]`).
- Se o total estourar, os arquivos restantes são **omitidos** e listados no prompt.
- Use `0` para desativar o limite.

Além disso, quando o motor suporta (ex.: Antigravity), o `iaw` **reusa a mesma
sessão** entre as etapas do workflow — a conversa continua, mantendo o contexto
do diagnóstico ao passar para a etapa de código.

### 2.7 Preencher stack.md/contexto.md a partir do projeto (`iaw analyze`)

O `iaw init` gera um `stack.md` simples e um `contexto.md` vazio. Para preenchê-los
com a análise real do repositório:

```bash
iaw analyze            # gera stack.md + contexto.md usando a IA
iaw analyze --dry-run  # só pré-visualiza, sem gravar
```

**Como funciona o passo a passo:**

1. O `iaw` monta um **fingerprint do projeto**: stack detectada (Django, Node, etc.),
   árvore de arquivos e conteúdo dos arquivos-chave (README, `pyproject.toml`,
   `requirements.txt`, `package.json`, `manage.py`, `settings.py`, etc.).
2. Envia esse resumo ao motor de IA com dois pedidos:
   - **`stack.md`** → diretrizes técnicas rígidas (stack/versões, comandos de
     build/teste/lint, convenções e guardrails).
   - **`contexto.md`** → domínio (objetivo, atores, subsistemas, invariantes e
     integrações).
3. Grava os dois arquivos em `.iaw/`.
4. Se a IA não estiver disponível (motor fora do PATH, falha de rede), o `iaw`
   **não deixa os arquivos vazios**: usa heurísticas com a stack detectada e
   marca os tópicos de domínio como `(a preencher)`.

Depois disso, revise os documentos (eles são a fonte da verdade da IA) e faça
commit. Você pode rodar `iaw analyze` de novo quando o projeto evoluir.

---

## 3. Ciclo de vida de uma tarefa (exemplo completo)

> Para o passo a passo **no projeto SUAP** (com a questão do venv), veja
> [exemplos_fluxos_dev.md](exemplos_fluxos_dev.md).

```bash
# 1. Inicia a partir de uma Issue do GitLab
iaw start-task 4512

# 2. Revisa o artefato de requisitos gerado
#    .iaw_workspace/1_requisitos_validados.md

# 3. Orquestra a IA pelo workflow (aprovando os gates)
#    A tarefa é inferida da branch/workspace; para indicar explicitamente:
iaw run --workflow nova_feature --issue-id 4512
#    Para ver o log de execução da IA (prompt, contexto e saída):
iaw run --workflow nova_feature --issue-id 4512 --log
#    Para abrir o MR ao final (por padrão, não cria MR):
iaw run --workflow nova_feature --issue-id 4512 --create-mr

# 4. Encerra: resumo + relatório (+ MR com --create-mr)
iaw finish-task
```

### Detalhamento

**`iaw start-task <id>`** baixa a Issue, cruza com o `stack.md` e gera
`.iaw_workspace/1_requisitos_validados.md` + `contexto.json`.

**`iaw run`** executa as etapas do workflow. Quando uma etapa tem
`require_human_approval: true`, a CLI **pausa** e pergunta:

```
Aprovar esta etapa e continuar? [y/n] (y):
```

Aprove para avançar; `n` interrompe o fluxo.

Opções úteis do `iaw run`:

```bash
# --issue-id (ou --task) indica a tarefa; sem ele, infere da branch/workspace
iaw run --workflow bug_fix --issue-id 4512 --log          # mostra o log da IA
iaw run --workflow bug_fix --issue-id 4512 --create-mr    # abre MR ao final
iaw run --workflow bug_fix --issue-id 4512 --resume       # retoma do state.json
```

**`iaw finish-task`** gera o `git diff`, pede um resumo executivo à IA e registra
a atividade no relatório mensal. Por padrão **não** abre MR; use `--create-mr`.

Opções úteis do `finish-task`:

```bash
iaw finish-task --create-mr          # abre o MR (por padrão, só atualiza o relatório)
iaw finish-task --summary "texto"    # pula a geração do resumo via IA
iaw finish-task --target-branch main # branch de destino do MR
iaw finish-task --keep-workspace     # mantém .iaw_workspace/ após concluir
```

---

## 4. Workflows

### 4.1 Os três workflows padrão

| Workflow | Quando usar | Etapas |
|----------|-------------|--------|
| `nova_feature` | Nova funcionalidade | Entendimento → Spec → Backend (TDD) → Frontend (Design System) → Testes/E2E/Visual → Consolidação |
| `bug_fix` | Correção de bug | Sentry → Diagnóstico → Teste Red → Fix → Testes → Consolidação |
| `refatoracao` | Refatoração segura | Rede de segurança → Refatorar → Regressão → Adaptar frontend → Consolidação |

### 4.2 Anatomia de um workflow YAML

```yaml
name: nova_feature
steps:
  - id: 1_entendimento_problema
    action: ask_clarifying_questions        # ação do nó
    context: [.iaw/stack.md]                # arquivos de contexto
    outputs:
      - file: .iaw_workspace/1_requisitos_validados.md
    require_human_approval: true            # gate de aprovação

  - id: 2_planejamento_arquitetura
    depends_on: [1_entendimento_problema]   # ordem de execução
    action: generate_artifact
    require_human_approval: true

  - id: 3a_materializacao_backend
    depends_on: [2_planejamento_arquitetura]
    action: execute_ai_coding               # IA escreve código
    description: "Implementa o backend em ciclos TDD."   # monitoramento
    skill: backend_tdd                        # Agente Principal (skill)

  - id: 3b_materializacao_frontend
    depends_on: [3a_materializacao_backend]
    action: execute_ai_coding
    subagent: suap-frontend                 # Especialista isolado
    require_human_approval: false           # etapa autônoma
```

### 4.2.1 Especialista por etapa (`skill:` / `subagent:`)

Cada step pode apontar para uma **skill** (Agente Principal) ou um **subagente**
(`subagent:`/`agent:`) que será injetado no prompt como perfil de especialista:

```yaml
steps:
  - id: 1_analisar_erro
    action: generate_artifact
    skill: bug-analyst            # lê .iaw/skills/bug-analyst/SKILL.md

  - id: 2_corrigir_frontend
    action: execute_ai_coding
    skill: frontend-suap          # segue o design system do SUAP

  - id: 3_validar_fluxo
    action: execute_ai_coding
    subagent: e2e-tester          # lê .iaw/agents/e2e-tester/
```

- `skill:` → `./.iaw/skills/<nome>/SKILL.md` (Agente Principal)
- `subagent:` (ou `agent:`) → `./.iaw/agents/<nome>.md` (ou `./.iaw/agents/<nome>/AGENT.md`) — Especialista isolado

Se a skill/subagente não existir, o `iaw` **degrada** para a skill padrão
(`default`) com aviso. As skills são instaladas com `iaw skill add <nome>
--source <path|url>` e os agents são importados do legado com `iaw import-legacy`.

#### Etapa opcional (`allow_no_change: true`)

Quando uma etapa é especializada (ex.: `skill: frontend-suap`) mas a tarefa pode
não precisar daquele tipo de alteração, marque-a como opcional:

```yaml
- id: 2_corrigir_frontend
  depends_on: [1_analisar_erro]
  action: execute_ai_coding
  skill: frontend-suap
  allow_no_change: true   # se não houver ajuste de frontend, a IA avisa e segue
```

Com isso, o `iaw` instrui a IA a **não modificar arquivos** e responder
`SEM_ALTERACOES_NECESSARIAS` quando a etapa não se aplicar. O orquestrador
reconhece esse marcador, registra a etapa como concluída (“sem alterações
ecessárias”) e continua o fluxo normalmente.

### 4.3 Ações disponíveis

| Ação | O que faz |
|------|-----------|
| `ask_clarifying_questions` | IA questiona/fecha buracos da regra de negócio |
| `generate_artifact` | Gera um artefato (spec, diagnóstico) via IA |
| `execute_ai_coding` | IA escreve código (autônoma ou com gate) |
| `run_terminal_command` | Executa comando shell (ex.: `pytest`) |
| `run_browser_harness` | Abre o navegador e tira screenshot (prova visual) |
| `generate_summary_and_publish` | Resumo + relatório (+ MR com `--create-mr`) |

### 4.4 Criando um workflow próprio

```bash
# crie .iaw/workflows/meu_fluxo.yaml e rode:
iaw run --workflow meu_fluxo
```

---

## 5. Skills

### 5.1 Criar, listar, instalar e atualizar

```bash
# 1. Criar uma skill nova em branco (para escrever você mesmo)
iaw skill create frontend-suap --description "Design system do SUAP"
#    → gera .iaw/skills/frontend-suap/SKILL.md

# 2. Listar as skills instaladas
iaw skill list

# 3. Instalar/atualizar a partir de uma fonte central
iaw skill add <nome> --source <path|url>
iaw skill update --source <path|url>
```

A fonte central pode ser configurada uma vez:

```bash
iaw config set skill_repo https://github.com/sua-org/ia-skills.git
```

**Como mapear a skill num workflow:** abra o YAML e informe o nome no step:

```yaml
- id: 2_corrigir_frontend
  action: execute_ai_coding
  skill: frontend-suap   # nome = pasta em .iaw/skills/
```

Se a skill não existir, o `iaw` usa a **skill padrão** (não falha).

### 5.2 Skill padrão e fallback

O `iaw init` cria a skill **`default`** em `.iaw/skills/default/SKILL.md`. Ela é
o fallback para quando um step declara `skill:`/`agent:` que ainda não existe:

```yaml
- id: 2_corrigir_frontend
  action: execute_ai_coding
  skill: frontend-suap   # se não existir, usa a skill default (com aviso)
```

Ao executar, o prompt da etapa recebe:

```
⚠ A skill/agent 'frontend-suap' não foi encontrada; usando a skill padrão 'default'.
```

Ou seja: **a execução não falha** por skill ausente — ela degrada para a skill
padrão. Para ter especialistas reais, instale as skills com `iaw skill add` (ou
importe do legado com `iaw import-legacy`) e troque `default` pelo nome correto.

### 5.3 Estrutura de uma skill

```yaml
# .iaw/skills/minha_skill/SKILL.md
---
name: minha_skill
description: O que esta skill faz.
trigger: /minha_skill
---
# Instruções da skill...
```

---

## 6. Monitoramento e notificações

### 6.1 Acompanhar execuções

```bash
iaw status
```

Mostra o histórico de execuções (running/success/failed) com issue e workflow.

### 6.2 Notificações

```bash
iaw run --notify          # notificação desktop ao terminar
```

Usa `plyer` (nativa do SO); sem ele, cai para mensagem no terminal.

> `--detach` (execução em background) está declarado; o suporte completo a
> execução desacoplada é uma evolução futura.

---

## 7. Registro no relatório

O relatório fica **fora do repositório**, no diretório configurado em
`relatorio_path` (padrão `~/.config/ia_workflow/reports/`), um arquivo por mês
(`agosto_2026.md`).

Cada `iaw finish-task` adiciona:

```markdown
- **[28/08/2026] Issue #4512:**
  - *Resumo IA:* Correção de lentidão na listagem de diários (N+1 → select_related).
  - *Evidência:* [Merge Request](https://gitlab.com/cosinf/suap/-/merge_requests/892)
```

No fim do mês, o arquivo está pronto para a prestação de contas do relatório, já
vinculado às Issues/MRs rastreáveis.

---

## 8. Evals — garantia de qualidade

Skills e agents são testados contra um **Golden Dataset** (`.iaw/evals/`).

```bash
iaw eval minha_skill       # roda os evals (cria baseline na 1ª vez)
iaw eval all               # todas as skills com dataset
iaw eval all --no-block    # reporta sem bloquear
```

- **Pre-commit**: `iaw install-hooks` instala um hook que roda os evals das
  skills alteradas e **aborta o commit** se houver regressão.
- **CI**: o template `.iaw/templates/gitlab-ci-evals.yml` faz o mesmo no MR.

Veja o [guia de Evals](EVALS.md) para criar casos de teste.

---

## 9. Permissões e segurança

A permissão não é por arquivo, e sim por **etapa do fluxo**:

| Camada | Onde | Papel |
|--------|------|-------|
| Global | `config.toml` (`auto_write_files`) | Autonomia do motor |
| Projeto | `.iaw/stack.md` | Regras/guardrails (sandbox) |
| Workflow | `require_human_approval` | Gate por etapa |

Regras de ouro:

- A IA **nunca faz merge** — só abre o MR. O merge é revisão humana no GitLab.
- A IA trabalha em **branch isolada** (`iaw/issue-<id>`), nunca em `master`.
- Se a etapa de testes/validação falhar, o fluxo **interrompe** (fail-safe).

---

## 10. Migração do legado

Para centralizar skills/agents que hoje vivem em `.agents/`, `.claude/`,
`.opencode/` etc.:

```bash
iaw import-legacy --dry-run   # pré-visualiza (não escreve)
iaw import-legacy             # copia para .iaw/ (mantém os originais)
```

Veja a análise completa em [MIGRACAO_SUAP.md](MIGRACAO_SUAP.md).

---

## 11. Referência rápida de comandos

| Comando | Descrição |
|---------|-----------|
| `iaw setup` | Configura credenciais globais |
| `iaw config set/get/list` | Gerencia a config global |
| `iaw init [--analyze]` | Cria/reconfigura `.iaw/` (com `--analyze`, preenche stack/contexto via IA) |
| `iaw analyze [--dry-run]` | Analisa o projeto e preenche stack.md/contexto.md |
| `iaw start-task <id>` | Inicia tarefa a partir de Issue do GitLab |
| `iaw run [--workflow <nome>] [--issue-id <id>] [--log] [--create-mr]` | Orquestra o workflow (tarefa, log e/ou abrindo MR) |
| `iaw finish-task [--create-mr]` | Resumo + relatório (+ MR) |
| `iaw status` | Acompanha execuções |
| `iaw skill list/create/add/update` | Gerencia skills (criar, instalar, atualizar) |
| `iaw import-legacy [--dry-run]` | Importa legado para `.iaw/` |
| `iaw eval <skill\|all>` | Roda evals de qualidade |
| `iaw install-hooks [--force]` | Instala hook pre-commit de evals |
| `iaw version` | Exibe a versão |

---

## 12. Solução de problemas

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| `Token do GitLab não configurado` | Config global vazia | `iaw setup` |
| `Workflow 'x' não encontrado` | `.iaw/workflows/x.yaml` ausente | `iaw init` ou crie o arquivo |
| `Comando 'pi' não encontrado` | Motor de IA fora do PATH | instale o Pi ou mude `default_engine` |
| `Comando 'agy' não encontrado` | Antigravity CLI fora do PATH | instale o Antigravity CLI ou mude `default_engine` |
| `Playwright não está instalado` | Dependência opcional ausente | `pip install -e '.[browser]'` + `playwright install chromium` |
| `Skill 'x' não encontrada` | Step usa `skill: x` mas a skill não existe | `iaw skill add x --source <path\|url>` ou remova o `skill:` |
| `Skill 'x' já existe` | Duplicata em `.iaw/skills/` | use `--overwrite` |
