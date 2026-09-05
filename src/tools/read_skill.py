from pathlib import Path

from langchain_core.tools import tool

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = (PROJECT_ROOT / "skills").resolve()


@tool
def read_skill(skill: str) -> str:
    """Read instructions for a specialised skill from the repo skills folder."""
    skill_path = (SKILLS_ROOT / skill / "SKILL.md").resolve()

    if not skill_path.is_relative_to(SKILLS_ROOT):
        raise ValueError("Invalid skill path")

    if not skill_path.is_file():
        available_skills = sorted(
            path.name
            for path in SKILLS_ROOT.iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
        raise FileNotFoundError(
            f"Skill not found: {skill}. Available skills: {available_skills}"
        )

    content = skill_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(
            f"Skill '{skill}' has an empty SKILL.md. Add concrete instructions "
            f"to {skill_path.relative_to(PROJECT_ROOT)} before using this skill."
        )

    return content
