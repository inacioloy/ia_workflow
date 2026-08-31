"""Textos de ajuda detalhada para o comando `iaw help`."""

from __future__ import annotations

COMMAND_HELP: dict[str, dict] = {
    "setup": {
        "resumo": "Configura as credenciais globais da ferramenta (uma única vez).",
        "detalhe": (
            "Assistente interativo que pergunta token do GitLab, URL do GitLab, "
            "projeto padrão, motor de IA, seu nome e diretório dos relatórios PGD. "
            "Grava tudo em ~/.config/ia_workflow/config.toml."
        ),
        "exemplos": ["iaw setup"],
    },
    "config": {
        "resumo": "Gerencia a configuração global (set/get/list).",
        "detalhe": (
            "Lê e grava chaves do ~/.config/ia_workflow/config.toml. "
            "O token do GitLab é sempre mascarado na exibição.\n"
            "Chaves: gitlab_url, gitlab_token, gitlab_project, default_engine, "
            "default_model, default_agent, dev_name, pgd_report_path, "
            "auto_write_files, skill_repo, context_max_chars, "
            "context_max_file_chars."
        ),
        "exemplos": [
            "iaw config set default_engine antigravity",
            "iaw config set default_model gemini-3.1-pro-high",
            "iaw config list",
        ],
    },
    "init": {
        "resumo": "Cria/reconfigura a pasta .iaw/ no projeto atual.",
        "detalhe": (
            "Assistente que pergunta a stack e onde ficam os testes, e gera a "
            "estrutura .iaw/ (stack.md, contexto.md, README.md, workflows "
            "nova_feature/bug_fix/refatoracao, skill padrão, templates e pastas). "
            "Por padrão não analisa o projeto: use `iaw init --analyze` (ou "
            "`iaw analyze`) para preencher stack.md/contexto.md com a IA. "
            "Commita o .iaw/ para o time."
        ),
        "exemplos": ["iaw init", "iaw init --analyze", "iaw init && iaw analyze"],
    },
    "analyze": {
        "resumo": "Analisa o projeto e preenche .iaw/stack.md e .iaw/contexto.md.",
        "detalhe": (
            "Coleta um fingerprint do repositório (stack detectada, árvore de "
            "arquivos e arquivos-chave) e pede ao motor de IA que gere versões "
            "ricas de stack.md (guardrails técnicos) e contexto.md (domínio). "
            "Se a IA falhar, usa heurísticas simples para não deixar os arquivos "
            "vazios. Use --dry-run para pré-visualizar."
        ),
        "exemplos": ["iaw analyze", "iaw analyze --dry-run"],
    },
    "start-task": {
        "resumo": "Inicia uma tarefa a partir de uma Issue do GitLab (Task-First).",
        "detalhe": (
            "Baixa a Issue, cruza com o .iaw/stack.md e gera o artefato "
            ".iaw_workspace/1_requisitos_validados.md + contexto.json. "
            "Use --project-id se o projeto padrão não estiver configurado."
        ),
        "exemplos": [
            "iaw start-task 4512",
            "iaw start-task 4512 --project-id cosinf/suap",
        ],
    },
    "run": {
        "resumo": "Orquestra a IA pelo workflow YAML (.iaw/workflows).",
        "detalhe": (
            "Executa as etapas do workflow na ordem (depends_on), chamando o "
            "motor de IA, rodando comandos de terminal e parando nos gates de "
            "aprovação humana. Registra a execução em `iaw status`.\n"
            "Use --issue-id (ou --task) para indicar a tarefa alvo; senão o id "
            "é inferido da branch ou do workspace. --notify avisa ao terminar. "
            "--log mostra o log de execução da IA (prompt, contexto e saída). "
            "--no-publish (ou --local) roda sem criar MR nem registrar no PGD.\n"
            "Cada step pode ter `skill:` ou `agent:` para usar um especialista "
            "(.iaw/skills/<nome>/SKILL.md ou .iaw/agents/<nome>.md). "
            "`allow_no_change: true` permite à IA pular a etapa quando nada "
            "precisar ser feito."
        ),
        "exemplos": [
            "iaw run --workflow bug_fix --issue-id 4512",
            "iaw run --task 4512 --workflow nova_feature --notify --log",
            "iaw run --workflow bug_fix --issue-id 4512 --no-publish",
        ],
    },
    "finish-task": {
        "resumo": "Encerra a tarefa: resumo + MR + relatório PGD.",
        "detalhe": (
            "Gera o git diff, pede resumo executivo à IA, abre o Merge Request "
            "no GitLab e registra a atividade no relatório mensal do PGD. "
            "Limpa o .iaw_workspace/ ao final."
        ),
        "exemplos": [
            "iaw finish-task",
            "iaw finish-task --no-mr",
            "iaw finish-task --summary \"Correção de N+1 nos diários\"",
        ],
    },
    "status": {
        "resumo": "Mostra o andamento das execuções.",
        "detalhe": (
            "Lista o histórico de execuções do `iaw run` (running/success/failed) "
            "com workflow e issue."
        ),
        "exemplos": ["iaw status"],
    },
    "skill": {
        "resumo": "Gerencia as skills do projeto (.iaw/skills/).",
        "detalhe": (
            "list: lista as skills instaladas.\n"
            "create: cria uma nova skill em branco para editar.\n"
            "add: instala uma skill de uma fonte central (caminho local ou URL Git).\n"
            "update: atualiza as skills instaladas a partir da fonte.\n"
            "Para mapear uma skill num workflow, use `skill: <nome>` no step."
        ),
        "exemplos": [
            "iaw skill list",
            "iaw skill create frontend-suap --description \"Design system do SUAP\"",
            "iaw skill add django-security --source https://github.com/ifrn/ia-skills.git",
            "iaw skill update",
        ],
    },
    "import-legacy": {
        "resumo": "Importa skills/agents/hooks do legado para .iaw/ (não apaga nada).",
        "detalhe": (
            "Copia .agents/, .claude/, .opencode/ e arquivos de contexto da raiz "
            "para a estrutura canônica .iaw/. Use --dry-run para pré-visualizar."
        ),
        "exemplos": [
            "iaw import-legacy --dry-run",
            "iaw import-legacy --source /caminho/do/projeto",
        ],
    },
    "eval": {
        "resumo": "Roda os evals (Golden Dataset + LLM-as-a-Judge) de skills.",
        "detalhe": (
            "Testa uma skill (ou 'all') contra os casos em .iaw/evals/ e compara "
            "o score com o baseline. Regressão retorna exit code 1. "
            "--update-baseline aceita o score atual; --no-block só reporta."
        ),
        "exemplos": [
            "iaw eval django_security",
            "iaw eval all",
            "iaw eval django_security --update-baseline",
        ],
    },
    "install-hooks": {
        "resumo": "Instala o hook de pre-commit que roda os evals das skills alteradas.",
        "detalhe": (
            "Grava .iaw/hooks/pre-commit-eval e instala em .git/hooks/pre-commit "
            "(sem sobrescrever um hook existente; --force para substituir)."
        ),
        "exemplos": ["iaw install-hooks", "iaw install-hooks --force"],
    },
    "version": {
        "resumo": "Exibe a versão da ferramenta.",
        "detalhe": "Mostra a versão instalada do ia_workflow.",
        "exemplos": ["iaw version"],
    },
}


def all_commands() -> list[str]:
    return list(COMMAND_HELP)
