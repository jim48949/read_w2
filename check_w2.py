#!/usr/bin/env python3
"""Check 2026 W-2 updates in a local Strategy/MicroStrategy HTML export."""
import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

BASIC_RULES = [
    {"name": "OMB number", "required": r"\bOMB\s*(?:NO\.?\s*)?[:#]?\s*1545\s*[-–—]\s*0029\b",
     "forbidden": r"\bOMB\s*(?:NO\.?\s*)?[:#]?\s*(?!1545\s*[-–—]\s*0029\b)\d{4}\s*[-–—]\s*\d{4}\b"},
    {"name": "Box 14a Other", "required": r"\b14\s*a\s*[.:-]?\s*Other\b",
     "forbidden": r"\b14\s*[.:-]?\s*Other\b"},
]


YEAR_RULE = {"name": "Tax year 2026", "required": r"\b2026\b",
             "forbidden": r"\b(?!2026\b)\d{4}\b"}
DEFAULT_RULES = [dict(rule, scope="form") for rule in BASIC_RULES] + [
    {"scope": "form", "name": "W-2 Form Page 1 of 1",
     "required": r"W\s*[-–—]\s*2\s+Form\s+Page\s+1\s+of\s+1\b",
     "forbidden": r"W\s*[-–—]\s*2\s+Form\s+Copy\b"},
    dict(YEAR_RULE, scope="form", year_context="form"),
    dict(YEAR_RULE, scope="notice", year_context="notice"),
    {"scope": "notice", "name": "Multiple employers social security limit",
     "required": r"If you had more than one employer in 2026 and more than\s+\$11,439\.00\s+in social security",
     "forbidden": r"\$10,918\.20"},
    {"scope": "notice", "name": "Railroad employer limit",
     "required": r"If you had more than one railroad employer and more than\s+\$6,717\.90\s+in\s+(?:social security|Tier\s+2\s+RRTA)",
     "forbidden": r"\$6,409\.20"},
    dict(YEAR_RULE, scope="instructions", year_context="instructions"),
    {"scope": "instructions", "name": "Box 12 elective deferral limits",
     "required": r"\bBox\s+12\b.{0,4000}?Elective deferrals.{0,600}?limited to a total of\s+\$24,500\b.{0,400}?\$27,500\b.{0,300}?Deferrals under code G are limited to\s+\$24,500\b",
     "forbidden": r"\$(?:23,500|26,500)\b"},
]
SECTION_HEADING = re.compile(
    r"(?<!also )(?P<notice>Notice\s+to\s+Employee)\b|"
    r"(?P<instructions>Instructions?\s+for\s+Employee(?:s)?)\b", re.IGNORECASE)


def section_texts(text):
    """Split a region at section headings; repeated sections are checked independently."""
    text = " ".join(text.split())
    headings = list(SECTION_HEADING.finditer(text))
    sections = []
    prefix = text[:headings[0].start()] if headings else text
    if prefix.strip():
        sections.append(("form", prefix))
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append((heading.lastgroup, text[heading.start():end]))
    return sections


def load_rules(path):
    rules = json.loads(Path(path).read_text()) if path else DEFAULT_RULES
    if not isinstance(rules, list) or not rules:
        raise ValueError("Rules must be a nonempty JSON array")
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("name"), str):
            raise ValueError("Each rule needs a name")
        if not isinstance(rule.get("required"), str) or not rule["required"]:
            raise ValueError("Each rule needs a nonempty required regex")
        if rule.get("scope", "all") not in {"all", "form", "notice", "instructions"}:
            raise ValueError("Unknown rule scope")
        if "year_context" in rule and rule["year_context"] not in {"form", "notice", "instructions"}:
            raise ValueError("Unknown year context")
        for field in ("required", "forbidden"):
            if field in rule:
                re.compile(rule[field], re.IGNORECASE)
    return rules


FORM_YEAR = re.compile(
    r"\b(?:Wage\s+and\s+Tax\s+Statement|Tax\s+year|Calendar\s+year)\s*[:–—-]?\s*(\d{4})\b", re.I)
NARRATIVE_YEAR = re.compile(
    r"\b(?:EITC\s+for|specified\s+amount\s+for|"
    r"For(?=\s+\d{4}\s+income\s+limits)|one\s+employer\s+in|"
    r"age\s+\d+(?:\s+through\s+\d+)?\s+in|December\s+31,?|"
    r"tax\s+year|calendar\s+year)\s*[:–—-]?\s*(\d{4})\b", re.I)


def inspect_text(text, rules, form_year_text=None):
    # Normalize HTML typography and whitespace, without emitting employee data.
    text = " ".join(text.split())
    results = []
    for rule in rules:
        target = text
        if rule.get("year_context"):
            pattern = FORM_YEAR if rule["year_context"] == "form" else NARRATIVE_YEAR
            # Inspect only years attached to known tax-year labels/references.
            # Unrelated address, account, and amount numbers are excluded.
            source = form_year_text if rule["year_context"] == "form" and form_year_text is not None else text
            target = " ".join(m.group(1) for m in pattern.finditer(source))
        required = len(list(re.finditer(rule["required"], target, re.IGNORECASE)))
        forbidden = len(list(re.finditer(rule["forbidden"], target, re.IGNORECASE))) if rule.get("forbidden") else 0
        results.append({"rule": rule["name"], "passed": required > 0 and forbidden == 0,
                        "required_matches": required, "forbidden_matches": forbidden})
    return results


def css_styles(soup):
    # Exported reports use simple generated class selectors with pixel positions.
    styles = {}
    for sheet in soup.find_all("style"):
        for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet.get_text()):
            for part in selector.split(","):
                match = re.fullmatch(r"\.([\w-]+)", part.strip())
                if match:
                    styles.setdefault(match[1], {}).update(parse_style(declarations))
    return styles


def parse_style(text):
    return {key.strip().lower(): value.strip().lower() for key, value in
            (item.split(":", 1) for item in text.split(";") if ":" in item)}


def element_style(node, styles):
    result = {}
    for name in node.get("class", []):
        result.update(styles.get(name, {}))
    result.update(parse_style(node.get("style", "")))
    return result


def hidden(node, styles):
    for ancestor in [node, *node.parents]:
        if not getattr(ancestor, "attrs", None):
            continue
        style = element_style(ancestor, styles)
        if ancestor.has_attr("hidden") or style.get("display") == "none" or style.get("visibility") in {"hidden", "collapse"}:
            return True
    return False


def pixel_top(node, styles):
    top = element_style(node, styles).get("top", "")
    if not re.fullmatch(r"-?[\d.]+px", top):
        raise ValueError("Section labels need exported pixel top coordinates")
    return float(top[:-2])


def html_sections(block, styles):
    explicit = block.get("data-w2-scope")
    if explicit:
        if explicit not in {"form", "notice", "instructions"}:
            raise ValueError("Unknown data-w2-scope")
        return [(explicit, block.get_text(" ", strip=True))]
    labels = [n for n in block.find_all("span") if not n.find_parent("span") and not hidden(n, styles)]
    headings = []
    for node in labels:
        text = " ".join(node.get_text(" ", strip=True).split())
        if re.fullmatch(r"Notice to Employee", text, re.I):
            headings.append((pixel_top(node, styles), "notice"))
        elif re.match(r"Instructions? for Employees?\b", text, re.I):
            headings.append((pixel_top(node, styles), "instructions"))
    if headings:
        headings.sort()
        grouped = {scope: [] for _, scope in headings}
        for node in labels:
            top = pixel_top(node, styles)
            # Columns in the sample differ by a few pixels at a section boundary.
            candidates = [(y, scope) for y, scope in headings if top >= y - 8]
            if candidates:
                grouped[candidates[-1][1]].append(node.get_text(" ", strip=True))
        return [(scope, " ".join(parts)) for scope, parts in grouped.items()]
    text = block.get_text(" ", strip=True)
    if re.search(r"\bOMB\b|W\s*[-–—]\s*2\s+Form\b|\b14\s*a?\s+Other\b", text, re.I):
        return [("form", text)]
    return []  # Address/cover blocks are not W-2 form copies.


def html_form_year_text(block, styles):
    """Read the positioned year field even when DOM order differs from display."""
    labels = [n for n in block.find_all("span") if not n.find_parent("span")]
    anchors = [n for n in labels if re.fullmatch(r"Wage\s+and\s+Tax\s+Statement", n.get_text(" ", strip=True), re.I)]
    if not anchors:
        return block.get_text(" ", strip=True)  # Explicit tax-year labels in other templates.
    fields = []
    for anchor in anchors:
        try:
            top = pixel_top(anchor, styles)
            left = float(element_style(anchor, styles)["left"].removesuffix("px"))
            candidates = []
            for node in labels:
                value = node.get_text(" ", strip=True)
                if not re.fullmatch(r"\d{4}", value):
                    continue
                node_left = float(element_style(node, styles)["left"].removesuffix("px"))
                if abs(pixel_top(node, styles) - top) <= 8 and node_left > left:
                    candidates.append((node_left, value))
            if candidates:
                fields.append("Wage and Tax Statement " + min(candidates)[1])
        except (KeyError, ValueError):
            continue  # Unlocatable fields fail as missing, rather than using unrelated numbers.
    return " ".join(fields)


def group_employees(regions, forms_per_employee, rules):
    """Group consecutive export packets, without reading employee identities."""
    groups = []
    current = []
    form_count = 0
    for region in regions:
        if region["section"] == "form" and current and (
            form_count >= forms_per_employee or any(r["section"] != "form" for r in current)):
            groups.append(current)
            current, form_count = [], 0
        current.append(region)
        form_count += region["section"] == "form"
    if current:
        groups.append(current)
    required = {r.get("scope", "all") for r in rules} - {"all"}
    if not required:
        required = {"form", "notice", "instructions"}
    employees = []
    for number, results in enumerate(groups, 1):
        errors = []
        for scope in sorted(required):
            count = sum(r["section"] == scope for r in results)
            expected = forms_per_employee if scope == "form" else 1
            if count != expected:
                errors.append(f"Expected {expected} {scope} section(s); found {count}")
        # Export packets must start with forms, followed by Notice and Instructions.
        order = {"form": 0, "notice": 1, "instructions": 2}
        positions = [order[r["section"]] for r in results]
        if positions != sorted(positions):
            errors.append("Sections are out of order; expected forms, notice, instructions")
        employees.append({"employee": number, "passed": not errors and all(r["passed"] for r in results),
                          "errors": errors, "results": results})
    return employees


def print_report(report):
    for employee in report["employees"]:
        number = employee["employee"]
        print(f"{'PASS' if employee['passed'] else 'FAIL'}: Employee {number}")
        for error in employee["errors"]:
            print(f"  FAIL: {error}")
        form_number = 0
        for result in employee["results"]:
            if result["section"] == "form":
                form_number += 1
            if result["passed"]:
                continue
            label = f"form {form_number}" if result["section"] == "form" else result["section"]
            location = f"{label}, HTML block {result['block']}"
            if not result["text_available"]:
                print(f"  FAIL: {location}: No extractable HTML text")
            for check in result["checks"]:
                if not check["passed"]:
                    print(f"  FAIL: {location}: {check['rule']} "
                          f"(required matches={check['required_matches']}, forbidden matches={check['forbidden_matches']})")
    if not report["employees"]:
        print("FAIL: No employee sections were checked")
    passed = sum(e["passed"] for e in report["employees"])
    print(f"Summary: {len(report['employees'])} employee(s), {passed} passed, "
          f"{len(report['employees']) - passed} failed")


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def check_document(path, rules, block_selector=None, forms_per_employee=3):
    if forms_per_employee < 1:
        raise ValueError("forms_per_employee must be positive")
    soup = BeautifulSoup(Path(path).read_bytes(), "html.parser")
    styles = css_styles(soup)
    for node in list(soup.find_all(True)):
        if node.attrs is not None and hidden(node, styles):
            node.decompose()
    for node in soup.select("script, style, template, noscript, head"):
        node.decompose()
    selector = block_selector or "[data-w2-scope], .mstrDocSubSection > div"
    blocks = [b for b in soup.select(selector) if not hidden(b, styles)]
    if not blocks:
        raise ValueError("No report blocks found; use --block-selector for a different template")
    if any(parent in blocks for block in blocks for parent in block.parents):
        raise ValueError("Overlapping block selection; select disjoint form/section containers")
    regions, seen_scopes = [], set()
    ignored = 0
    for index, block in enumerate(blocks, 1):
        sections = html_sections(block, styles)
        if not sections:
            ignored += 1
        for scope, text in sections:
            seen_scopes.add(scope)
            selected = [r for r in rules if r.get("scope", "all") in {"all", scope}]
            checks = inspect_text(text, selected,
                                      form_year_text=html_form_year_text(block, styles) if scope == "form" else None)
            if not checks:
                continue
            regions.append({"block": index, "section": scope, "passed": bool(text.strip()) and all(c["passed"] for c in checks),
                            "text_available": bool(text.strip()), "checks": checks})
    missing = sorted({r["scope"] for r in rules if r.get("scope", "all") != "all"} - seen_scopes)
    employees = group_employees(regions, forms_per_employee, rules)
    return {"employees": employees, "employees_checked": len(employees),
            "passed": bool(employees) and not missing and all(e["passed"] for e in employees),
            "missing_sections": missing, "regions_checked": len(regions), "ignored_blocks": ignored, "results": regions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--rules", type=Path, help="JSON array of name/required/forbidden regex rules")
    parser.add_argument("--json", type=Path, help="Write a report without extracted employee text")
    parser.add_argument("--block-selector", help="CSS selector for disjoint report containers")
    parser.add_argument("--forms-per-employee", type=positive_int, default=3,
                        help="Expected consecutive form copies per employee (default: 3)")
    args = parser.parse_args()
    try:
        report = check_document(args.html, load_rules(args.rules), args.block_selector, args.forms_per_employee)
        if args.json:
            args.json.write_text(json.dumps(report, indent=2) + "\n")
    except Exception as exc:
        # Some parser exceptions include HTML content; don't echo arbitrary error text.
        print(f"ERROR ({type(exc).__name__}): unable to check HTML or configuration. Check paths, rules, and report block structure.", file=sys.stderr)
        return 2
    print_report(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
