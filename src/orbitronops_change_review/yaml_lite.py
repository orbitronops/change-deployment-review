"""A tiny YAML-subset parser for the demo manifests.

The demo has no dependencies, so it cannot use PyYAML. This parser handles
only the subset used in examples/: multi-document files separated by ``---``,
nested mappings, lists of scalars or mappings, and plain/quoted scalars
(strings, ints, floats, booleans, null). Anything outside that subset raises
``ValueError`` with a clear message instead of silently mis-parsing.
"""
from __future__ import annotations


def _strip_comment(line: str) -> str:
    """Remove a `` # comment`` that is not inside quotes."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and i > 0 and line[i - 1] == " ":
            return line[:i].rstrip()
    return line.rstrip()


def _scalar(text: str):
    text = text.strip()
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


class _Parser:
    def __init__(self, lines: list[tuple[int, str]]):
        self.lines = lines
        self.pos = 0

    def _peek(self):
        if self.pos < len(self.lines):
            return self.lines[self.pos]
        return None

    def parse_node(self, indent: int):
        peek = self._peek()
        if peek is None or peek[0] < indent:
            return None
        if peek[1] == "-" or peek[1].startswith("- "):
            return self._parse_list(indent)
        return self._parse_mapping(indent)

    def _parse_mapping(self, indent: int) -> dict:
        result: dict = {}
        while True:
            peek = self._peek()
            if peek is None or peek[0] != indent:
                return result
            content = peek[1]
            if content == "-" or content.startswith("- "):
                return result
            if ": " not in content and not content.endswith(":"):
                raise ValueError(f"cannot parse line as mapping entry: {content!r}")
            key, _, rest = content.partition(":")
            key = key.strip()
            rest = rest.strip()
            self.pos += 1
            if rest == "":
                nxt = self._peek()
                if nxt is not None and nxt[0] > indent:
                    result[key] = self.parse_node(nxt[0])
                else:
                    result[key] = None
            else:
                result[key] = _scalar(rest)
        return result

    def _parse_list(self, indent: int) -> list:
        result: list = []
        while True:
            peek = self._peek()
            if peek is None or peek[0] != indent:
                return result
            content = peek[1]
            if not (content == "-" or content.startswith("- ")):
                return result
            item_text = content[1:].strip()
            self.pos += 1
            if item_text == "":
                nxt = self._peek()
                if nxt is not None and nxt[0] > indent:
                    result.append(self.parse_node(nxt[0]))
                else:
                    result.append(None)
            elif ": " in item_text or item_text.endswith(":"):
                # "- key: value" starts a mapping whose other keys sit at
                # indent + 2. Rewrite the first line as a mapping line.
                child_indent = indent + 2
                self.lines.insert(self.pos, (child_indent, item_text))
                result.append(self._parse_mapping(child_indent))
            else:
                result.append(_scalar(item_text))
        return result


def parse_documents(text: str) -> list[dict]:
    """Parse a YAML-subset document into a list of top-level mappings."""
    docs: list[dict] = []
    current: list[str] = []

    def flush():
        if not current:
            return
        lines: list[tuple[int, str]] = []
        for raw in current:
            stripped = _strip_comment(raw)
            if not stripped.strip() or stripped.strip().startswith("#"):
                continue
            indent = len(stripped) - len(stripped.lstrip(" "))
            if "\t" in stripped[:indent]:
                raise ValueError("tabs are not allowed for indentation")
            lines.append((indent, stripped.strip()))
        if lines:
            parser = _Parser(lines)
            docs.append(parser.parse_node(lines[0][0]) or {})
        current.clear()

    for raw in text.splitlines():
        if raw.strip() in ("---", "..."):
            flush()
        else:
            current.append(raw)
    flush()
    return docs


def parse_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return parse_documents(handle.read())
