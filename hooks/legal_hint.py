#!/usr/bin/env python3
"""Хук UserPromptSubmit для Claude Code.

Если вопрос похож на юридический по праву РФ, добавляет модели напоминание вызвать
скилл ru-law. Ничего не пишет на диск и не обращается к сети. При любой ошибке тихо
завершается с кодом 0, чтобы не мешать работе.

Работает только в Claude Code. В чате (claude.ai) и в других агентах хуков нет:
там используйте строку-триггер из INSTALL.md.
"""
import json
import re
import sys

PATTERNS = [
    r"\bдоговор", r"\bоферт", r"\bштраф", r"\bнеустойк", r"\bпретензи", r"\bпошлин",
    r"\bувол", r"\bсамозанят", r"\bгпх\b", r"\bтрудов",
    r"\bперсональн", r"\b152-?фз", r"\bроскомнадзор", r"\bут[её]к", r"\bутечк",
    r"\bреклам", r"\bмаркировк", r"\bрассылк",
    r"\bавторск", r"\bтоварн\w* знак", r"\bлицензи",
    r"\bарбитраж", r"\bсудебн", r"\bиск(а|у|ом|и|е)?\b", r"\bв суд(е|а|у)?\b",
    r"\bзаконн", r"\bюрист",
    r"\bсотрудник", r"\bработодател", r"\bзарплат", r"\bне плат(ит|ят|ил|или)\b", r"\bдолг",
    r"\bкартинк\w* из интернет", r"\bфото\w* из интернет", r"\bскопиров", r"\bплагиат",
]
RE = re.compile("|".join(PATTERNS), re.IGNORECASE)

HINT = (
    "[ru-law] Вопрос похож на юридический по праву РФ. Перед ответом вызови скилл "
    "ru-law:ru-law (если он доступен под коротким именем — ru-law) и работай по нему. "
    "Не отвечай по памяти про суммы штрафов, пошлины и сроки: бери их из справочников скиллов."
)


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        data = json.load(sys.stdin)
        prompt = str(data.get("prompt", ""))
    except Exception:
        return
    if not prompt or prompt.lstrip().startswith("/") or "ru-law" in prompt.lower():
        return
    if RE.search(prompt):
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": HINT}}
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
