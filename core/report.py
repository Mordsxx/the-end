"""Validation report shared by both engines (data structure only - no engine logic lives here)."""
from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    level: str = "error"   # error | warn | info


@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)

    def add(self, name, ok, detail="", level="error"):
        self.checks.append(Check(name, bool(ok), detail, level))

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks if c.level == "error")

    def text(self) -> str:
        lines = []
        for c in self.checks:
            mark = "✔" if c.ok else ("✖" if c.level == "error" else "!")
            lines.append(f"{mark} {c.name}" + (f" — {c.detail}" if c.detail else ""))
        lines.append("")
        lines.append("RESULT: " + ("ALL CHECKS PASSED" if self.passed else "VALIDATION FAILED"))
        return "\n".join(lines)
