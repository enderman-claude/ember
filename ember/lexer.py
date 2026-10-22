"""Indentation-aware lexer. Emits NEWLINE, INDENT and DEDENT tokens."""
from dataclasses import dataclass
from .errors import CompileError

KEYWORDS = {
    "def", "extern", "return", "if", "elif", "else", "while", "for", "in",
    "break", "continue", "mut", "true", "false", "and", "or", "not",
}
OPS2 = ("==", "!=", "<=", ">=", "->")
OPS1 = set("+-*/%<>=():,[]")


@dataclass
class Token:
    kind: str       # keyword text, "NAME", "INT", an operator, or NEWLINE/INDENT/DEDENT/EOF
    value: str
    line: int
    col: int


def tokenize(src: str) -> list:
    tokens = []
    indents = [0]
    lineno = 0
    src = src.replace("\r\n", "\n")
    for lineno, raw in enumerate(src.split("\n"), 1):
        code = raw.split("#", 1)[0].rstrip()          # `#` starts a comment
        if not code.strip():
            continue                                  # blank or comment-only line
        indent = len(code) - len(code.lstrip(" "))
        if "\t" in code[:indent]:
            raise CompileError(lineno, "tabs are not allowed in indentation")

        if indent > indents[-1]:
            indents.append(indent)
            tokens.append(Token("INDENT", "", lineno, 1))
        while indent < indents[-1]:
            indents.pop()
            tokens.append(Token("DEDENT", "", lineno, 1))
        if indent != indents[-1]:
            raise CompileError(lineno, "inconsistent indentation")

        body = code[indent:]
        i = 0
        while i < len(body):
            c = body[i]
            col = indent + i + 1
            if c == " ":
                i += 1
            elif c.isdigit():
                j = i
                while j < len(body) and body[j].isdigit():
                    j += 1
                tokens.append(Token("INT", body[i:j], lineno, col))
                i = j
            elif c.isalpha() or c == "_":
                j = i
                while j < len(body) and (body[j].isalnum() or body[j] == "_"):
                    j += 1
                word = body[i:j]
                kind = word if word in KEYWORDS else "NAME"
                tokens.append(Token(kind, word, lineno, col))
                i = j
            elif body[i:i + 2] in OPS2:
                tokens.append(Token(body[i:i + 2], body[i:i + 2], lineno, col))
                i += 2
            elif c in OPS1:
                tokens.append(Token(c, c, lineno, col))
                i += 1
            else:
                raise CompileError(lineno, f"unexpected character {c!r}", col)
        tokens.append(Token("NEWLINE", "\n", lineno, len(code) + 1))

    while len(indents) > 1:
        indents.pop()
        tokens.append(Token("DEDENT", "", lineno, 1))
    tokens.append(Token("EOF", "", lineno + 1, 1))
    return tokens
