"""Motor de Evals (LLMOps) do iaw.

Garante que alterações em skills/agentes não regridam a qualidade: cada skill
pode ter um **Golden Dataset** em ``.iaw/evals/<skill>/<caso>/`` com
``input.md`` (cenário) e ``expected.md`` (critério esperado). O juiz é um
**LLM-as-a-Judge** que responde apenas PASS/FAIL.

Estrutura:
    .iaw/evals/
    ├── .baseline.json           # scores de referência (gerado)
    └── <skill>/
        └── <caso>/
            ├── input.md         # cenário (ex: código com bug)
            └── expected.md      # rubrica do juiz
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import project
from .engines import build_engine
from .skills import parse_frontmatter

BASELINE_FILE = ".baseline.json"

JUDGE_PROMPT = """Você é um juiz determinístico de qualidade (LLM-as-a-Judge).

Avalie se a SAÍDA DO AGENTE atende ao CRITÉRIO ESPERADO abaixo.

## Critério esperado
{expected}

## Saída do agente
{output}

Responda APENAS com "PASS" ou "FAIL". Nada mais.
"""


@dataclass
class EvalCase:
    skill: str
    name: str
    input_path: Path
    expected_path: Path


@dataclass
class EvalResult:
    case: str
    passed: bool
    skill_output: str = ""
    judge_verdict: str = ""


@dataclass
class EvalReport:
    skill: str
    results: list[EvalResult] = field(default_factory=list)
    baseline: float | None = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def score(self) -> float:
        return (self.passed / self.total * 100) if self.total else 0.0

    @property
    def regressed(self) -> bool:
        """True se o score caiu em relação ao baseline."""
        return self.baseline is not None and self.score < self.baseline


# --------------------------------------------------------------------------- #
# Golden Dataset
# --------------------------------------------------------------------------- #
def evals_dir(iaw_dir: Path) -> Path:
    return iaw_dir / "evals"


def skill_evals_dir(iaw_dir: Path, skill: str) -> Path:
    return evals_dir(iaw_dir) / skill


def load_cases(iaw_dir: Path, skill: str) -> list[EvalCase]:
    """Carrega os casos de eval de uma skill."""
    base = skill_evals_dir(iaw_dir, skill)
    if not base.is_dir():
        return []
    cases: list[EvalCase] = []
    for case_dir in sorted(base.iterdir()):
        if not case_dir.is_dir():
            continue
        input_path = case_dir / "input.md"
        expected_path = case_dir / "expected.md"
        if input_path.is_file() and expected_path.is_file():
            cases.append(
                EvalCase(skill=skill, name=case_dir.name, input_path=input_path, expected_path=expected_path)
            )
    return cases


def skills_with_evals(iaw_dir: Path) -> list[str]:
    """Lista as skills que possuem Golden Dataset definido."""
    base = evals_dir(iaw_dir)
    if not base.is_dir():
        return []
    return sorted(
        d.name
        for d in base.iterdir()
        if d.is_dir() and load_cases(iaw_dir, d.name)
    )


def load_baseline(iaw_dir: Path, skill: str) -> float | None:
    """Lê o score de referência de uma skill (se existir)."""
    path = evals_dir(iaw_dir) / BASELINE_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data.get(skill)


def save_baseline(iaw_dir: Path, skill: str, score: float) -> None:
    """Grava/atualiza o score de referência de uma skill."""
    path = evals_dir(iaw_dir) / BASELINE_FILE
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data[skill] = round(score, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Execução
# --------------------------------------------------------------------------- #
def build_skill_prompt(iaw_dir: Path, skill: str, case: EvalCase) -> str:
    """Monta o prompt: instruções da skill + cenário do caso."""
    skill_file = iaw_dir / "skills" / skill / "SKILL.md"
    instructions = (
        skill_file.read_text(encoding="utf-8")
        if skill_file.is_file()
        else f"Skill: {skill}"
    )
    scenario = case.input_path.read_text(encoding="utf-8")
    return (
        f"{instructions}\n\n"
        "## Tarefa\n"
        "Aplique a skill acima ao cenário abaixo e produza o resultado esperado.\n\n"
        f"## Cenário\n{scenario}"
    )


def _parse_verdict(text: str) -> str:
    """Extrai PASS/FAIL da resposta do juiz (conservador: FAIL se ambíguo)."""
    verdict = text.strip().upper()
    if re.search(r"\bPASS\b", verdict) and not re.search(r"\bFAIL\b", verdict):
        return "PASS"
    if re.search(r"\bFAIL\b", verdict):
        return "FAIL"
    return "FAIL"  # fail-safe


def _run_engine(engine, prompt: str) -> str:
    result = engine.generate(prompt)
    return result.output if result.success else ""


def eval_skill(
    iaw_dir: Path,
    skill: str,
    *,
    engine=None,
    update_baseline: bool = False,
    no_block: bool = False,
) -> EvalReport:
    """Roda os evals de uma skill e compara com o baseline.

    :param no_block: se True, apenas reporta (não marca regressão).
    """
    engine = engine or build_engine()
    cases = load_cases(iaw_dir, skill)
    report = EvalReport(skill=skill, baseline=load_baseline(iaw_dir, skill))

    if not cases:
        return report

    for case in cases:
        skill_prompt = build_skill_prompt(iaw_dir, skill, case)
        skill_output = _run_engine(engine, skill_prompt)

        judge_prompt = JUDGE_PROMPT.format(
            expected=case.expected_path.read_text(encoding="utf-8"),
            output=skill_output or "(sem saída)",
        )
        verdict = _parse_verdict(_run_engine(engine, judge_prompt))

        report.results.append(
            EvalResult(
                case=case.name,
                passed=(verdict == "PASS"),
                skill_output=skill_output,
                judge_verdict=verdict,
            )
        )

    # Atualização do baseline.
    if update_baseline or report.baseline is None:
        save_baseline(iaw_dir, skill, report.score)
        report.baseline = report.score
    elif no_block:
        # Apenas reporta, sem aplicar a trava de regressão.
        pass

    return report


def eval_all(iaw_dir: Path, *, engine=None, update_baseline: bool = False) -> list[EvalReport]:
    """Roda os evals de todas as skills com Golden Dataset."""
    return [
        eval_skill(iaw_dir, skill, engine=engine, update_baseline=update_baseline)
        for skill in skills_with_evals(iaw_dir)
    ]
