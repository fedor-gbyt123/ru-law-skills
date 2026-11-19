#!/usr/bin/env python3
"""Проверка скиллов ru-law.

    python scripts/check.py            # проверка, заготовки допускаются
    python scripts/check.py --fix      # вписать общие правила из shared/core-rules.md во все SKILL.md
    python scripts/check.py --release  # строгая проверка перед релизом: ни одной заготовки, нормы сверены

Только стандартная библиотека Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
CORE = ROOT / "shared" / "core-rules.md"
START, END = "<!-- CORE-RULES:START -->", "<!-- CORE-RULES:END -->"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
URL_RE = re.compile(r"https?://([^/\s)\]]+)")
OFFICIAL = ("pravo.gov.ru", "consultant.ru", "garant.ru", "vsrf.ru", "cbr.ru", "rkn.gov.ru",
            "fas.gov.ru", "rospatent.gov.ru", "fips.ru", "nalog.gov.ru", "rostrud.gov.ru",
            "arbitr.ru", "government.ru", "kremlin.ru", "sozd.duma.gov.ru")
NORMS_HEADER = ["норма", "суть", "источник", "редакция", "проверено"]
STALE_DAYS = 90          # правило 3: старше 3 месяцев — перепроверять
SOON_DAYS = 90           # будущие изменения в ближайшие 3 месяца — предупреждать
FUTURE_RE = re.compile(r"будущие изм[^|]*", re.I)
RU_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

errors: list[str] = []
warnings: list[str] = []


def err(skill: str, msg: str) -> None:
    errors.append(f"[{skill}] {msg}")


def warn(skill: str, msg: str) -> None:
    warnings.append(f"[{skill}] {msg}")


def frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            return None
        value = value.strip()
        quoted = len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
        if not quoted and ": " in value:
            data["__yaml_error__"] = key
        data[key.strip()] = value[1:-1] if quoted else value
    return data


def sync_rules(text: str, rules: str) -> str:
    block = f"{START}\n{rules.strip()}\n{END}"
    return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)


def check_norms(skill: str, path: Path, release: bool) -> int:
    if not path.exists():
        (err if release else warn)(skill, "нет references/norms.md")
        return 0
    rows = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip().startswith("|")]
    if len(rows) < 2:
        err(skill, "norms.md: нет таблицы норм")
        return 0
    header = [c.strip().lower() for c in rows[0].strip("|").split("|")]
    if header[:5] != NORMS_HEADER:
        err(skill, f"norms.md: заголовок таблицы должен быть {NORMS_HEADER}, сейчас {header}")
        return 0
    today = dt.date.today()
    count = 0
    for i, row in enumerate(rows[2:], start=1):
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) < 5 or not cells[0]:
            err(skill, f"norms.md, строка {i}: не хватает колонок")
            continue
        count += 1
        hosts = URL_RE.findall(cells[2])
        if not hosts:
            err(skill, f"norms.md, «{cells[0]}»: нет ссылки на источник")
        elif not any(h.endswith(o) for h in hosts for o in OFFICIAL):
            warn(skill, f"norms.md, «{cells[0]}»: источник не из списка официальных ({', '.join(hosts)})")
        m = DATE_RE.search(cells[4])
        if not m:
            err(skill, f"norms.md, «{cells[0]}»: в колонке «Проверено» нужна дата ГГГГ-ММ-ДД")
            continue
        try:
            checked = dt.date.fromisoformat(m.group(1))
        except ValueError:
            err(skill, f"norms.md, «{cells[0]}»: неверная дата {m.group(1)}")
            continue
        if checked > today:
            err(skill, f"norms.md, «{cells[0]}»: дата проверки в будущем")
        elif (today - checked).days > STALE_DAYS:
            warn(skill, f"{path.name}, «{cells[0]}»: проверено больше {STALE_DAYS} дней назад, пересверить")
        future = FUTURE_RE.search(cells[3])
        if future:
            for d, m_, y in RU_DATE_RE.findall(future.group(0)):
                try:
                    when = dt.date(int(y), int(m_), int(d))
                except ValueError:
                    continue
                if when <= today and checked < when:
                    warn(skill, f"{path.name}, «{cells[0]}»: изменения с {when} уже вступили, а сверено {checked} — пересверить")
                elif today < when <= today + dt.timedelta(days=SOON_DAYS):
                    warn(skill, f"{path.name}, «{cells[0]}»: изменения вступают {when} — пересверить после этой даты")
    if count == 0:
        err(skill, "norms.md: таблица пустая")
    return count


LAW_ID_RE = re.compile(r"cons_doc_LAW_(\d+)")
NORM_HEAD_RE = re.compile(r"^(.+?)\s+ст\.\s*(.+)$")


def _law_key(norm: str) -> tuple[str, ...]:
    """Группа «один закон» для проверки единого номера документа."""
    m = NORM_HEAD_RE.match(norm)
    if not m:
        return (norm.strip(),)
    law = m.group(1).strip()
    rest = m.group(2)
    if law == "ГК РФ":
        num = re.match(r"^([\d.]+)", rest)
        if num:
            n = float(num.group(1))
            part = "ч.1" if n < 454 else "ч.2" if n < 1110 else "ч.3" if n < 1225 else "ч.4"
            return ("ГК РФ", part)
    return (law,)


def cross_check() -> None:
    """Одна норма в разных справочниках — одинаковые ссылки; в одном файле
    статьи одного закона — один номер документа КонсультантПлюс."""
    per_norm: dict[str, dict[str, set[str]]] = {}   # norm -> skill -> set(first URLs)
    per_file: dict[tuple[str, tuple[str, ...]], set[str]] = {}  # (skill, law_key) -> docids
    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        path = skill_dir / "references" / "norms.md"
        if not path.exists():
            continue
        skill = skill_dir.name
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|") or line.strip("|").split("|")[0].strip() in ("", "Норма"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            norm, urls_cell = cells[0], cells[2]
            first = urls_cell.split()[0] if urls_cell.split() else ""
            if not first.startswith("http"):
                continue
            per_norm.setdefault(norm, {}).setdefault(skill, set()).add(first)
            doc_ids = set()
            first_doc = LAW_ID_RE.search(urls_cell)
            if first_doc:
                doc_ids = {first_doc.group(1)}
            if doc_ids:
                per_file.setdefault((skill, _law_key(norm)), set()).update(doc_ids)
    for norm, by_skill in sorted(per_norm.items()):
        all_urls: set[str] = set()
        for urls in by_skill.values():
            all_urls.update(urls)
        if len(all_urls) > 1:
            where = ", ".join(f"{s}: {sorted(u)}" for s, u in sorted(by_skill.items()))
            err("cross", f"норма «{norm}» ссылается на разные источники — {where}")
    for (skill, law_key), doc_ids in sorted(per_file.items()):
        if len(doc_ids) > 1:
            warn(skill, f"norms.md, «{' / '.join(law_key)}»: статьи одного закона ссылаются на разные документы КонсультантПлюс (LAW_{', LAW_'.join(sorted(doc_ids))})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()

    rules = CORE.read_text(encoding="utf-8")
    report = []
    for skill_dir in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        skill = skill_dir.name
        md = skill_dir / "SKILL.md"
        if not md.exists():
            err(skill, "нет SKILL.md")
            continue
        text = md.read_text(encoding="utf-8")

        if START not in text or END not in text:
            err(skill, "нет блока общих правил (маркеры CORE-RULES)")
        else:
            synced = sync_rules(text, rules)
            if synced != text:
                if args.fix:
                    md.write_text(synced, encoding="utf-8", newline="\n")
                    text = synced
                else:
                    err(skill, "общие правила не совпадают с shared/core-rules.md (запусти с --fix)")

        fm = frontmatter(text)
        if fm is None:
            err(skill, "нет или испорчен frontmatter")
            continue
        if "__yaml_error__" in fm:
            err(skill, f"поле «{fm['__yaml_error__']}» содержит «: » без кавычек — YAML сломается")
        if fm.get("name") != skill:
            err(skill, f"name «{fm.get('name')}» должен совпадать с именем папки")
        if not NAME_RE.match(skill) or len(skill) > 64:
            err(skill, "имя папки: только a-z, 0-9 и дефисы, до 64 символов")
        desc = fm.get("description", "")
        if not desc:
            err(skill, "нет description")
        elif len(desc) > 1024:
            err(skill, f"description длиннее 1024 символов ({len(desc)})")

        body = re.sub(re.escape(START) + r".*?" + re.escape(END), "", text, flags=re.S)
        for ref in set(re.findall(r"`((?:references|assets|scripts)/[^`\s]+)`", body)):
            if not (skill_dir / ref).exists() and "TODO" not in text:
                err(skill, f"ссылка на несуществующий файл {ref}")

        lines = text.count("\n")
        if lines > 500:
            warn(skill, f"SKILL.md {lines} строк — вынеси детали в references/")

        draft = "TODO" in text or "ТЗ для разработчика" in text or "СТАТУС: заготовка" in text
        if draft and args.release:
            err(skill, "заготовка: остались TODO / ТЗ / пометка статуса")
        norms = 0
        if skill != "ru-law":
            norms = check_norms(skill, skill_dir / "references" / "norms.md", args.release and not draft)
            practice = skill_dir / "references" / "practice.md"
            if practice.exists():
                check_norms(skill, practice, True)
        report.append((skill, "заготовка" if draft else "готов", norms, lines))

    cross_check()

    print(f"{'скилл':<22}{'статус':<12}{'норм':>6}{'строк':>7}")
    for skill, status, norms, lines in report:
        print(f"{skill:<22}{status:<12}{norms:>6}{lines:>7}")
    for w in warnings:
        print("ПРЕДУПРЕЖДЕНИЕ", w)
    for e in errors:
        print("ОШИБКА", e)
    print("ИТОГ:", "есть ошибки" if errors else "ок")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
