import re
from compiler.token import Token, TokenType, KEYWORDS


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 0
        self.tokens: list[Token] = []
        self.indent_stack = [0]

    def error(self, message: str):
        raise SyntaxError(f"{message} at line {self.line}, column {self.col}")

    def peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.source[idx] if idx < len(self.source) else "\0"

    def advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 0
        else:
            self.col += 1
        return ch

    def skip_whitespace(self):
        while self.pos < len(self.source) and self.peek() in " \t\r":
            self.advance()

    def skip_comment(self):
        while self.pos < len(self.source) and self.peek() != "\n":
            self.advance()

    def read_string(self):
        self.advance()
        result = []
        while self.pos < len(self.source) and self.peek() != '"':
            result.append(self.advance())
        if self.pos >= len(self.source):
            self.error("Unterminated string")
        self.advance()
        return "".join(result)

    def read_number(self):
        result = []
        is_float = False
        while self.pos < len(self.source) and (self.peek().isdigit() or self.peek() == "."):
            if self.peek() == ".":
                if is_float:
                    break
                is_float = True
            result.append(self.advance())
        num_str = "".join(result)
        if is_float:
            return TokenType.FLOAT, float(num_str)
        return TokenType.NUMBER, int(num_str)

    def read_identifier(self):
        result = []
        while self.pos < len(self.source) and (self.peek().isalnum() or self.peek() == "_"):
            result.append(self.advance())
        word = "".join(result)
        if word in KEYWORDS:
            return TokenType.KEYWORD, word
        return TokenType.IDENTIFIER, word

    def handle_indent(self):
        col = 0
        while self.pos < len(self.source) and self.peek() in " \t":
            ch = self.advance()
            col += 4 if ch == "\t" else 1

        current = self.indent_stack[-1]
        if col > current:
            self.indent_stack.append(col)
            self.tokens.append(Token(TokenType.INDENT, col, self.line, col))
        elif col < current:
            while self.indent_stack and self.indent_stack[-1] > col:
                self.indent_stack.pop()
                self.tokens.append(Token(TokenType.DEDENT, col, self.line, col))
            if self.indent_stack and self.indent_stack[-1] != col:
                self.error(f"Inconsistent indentation")

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.source):
            ch = self.peek()

            if ch == "\n":
                self.advance()
                self.tokens.append(Token(TokenType.NEWLINE, "\n", self.line - 1, 0))
                self.skip_whitespace()
                if self.pos < len(self.source) and self.peek() != "\n":
                    self.handle_indent()
                continue

            if ch in " \t\r":
                self.skip_whitespace()
                continue

            if ch == "/" and self.peek(1) == "/":
                self.skip_comment()
                continue

            if ch == '"':
                value = self.read_string()
                self.tokens.append(Token(TokenType.STRING, value, self.line, self.col))
                continue

            if ch.isdigit():
                typ, value = self.read_number()
                self.tokens.append(Token(typ, value, self.line, self.col))
                continue

            if ch.isalpha() or ch == "_":
                typ, value = self.read_identifier()
                self.tokens.append(Token(typ, value, self.line, self.col))
                continue

            multi = {
                "->": TokenType.ARROW,
                "=>": TokenType.FAT_ARROW,
            }
            two = self.peek(1)
            if two and ch + two in multi:
                self.advance()
                self.advance()
                self.tokens.append(Token(multi[ch + two], ch + two, self.line, self.col))
                continue

            single = {
                "{": TokenType.LBRACE, "}": TokenType.RBRACE,
                "(": TokenType.LPAREN, ")": TokenType.RPAREN,
                "[": TokenType.LBRACKET, "]": TokenType.RBRACKET,
                ":": TokenType.COLON, ";": TokenType.SEMICOLON,
                ",": TokenType.COMMA, ".": TokenType.DOT,
                "=": TokenType.EQUALS, "+": TokenType.PLUS,
                "-": TokenType.MINUS, "*": TokenType.STAR,
                "/": TokenType.SLASH, "%": TokenType.PERCENT,
                "|": TokenType.PIPE, "&": TokenType.AMPERSAND,
                "<": TokenType.LESS, ">": TokenType.GREATER,
            }
            if ch in single:
                self.advance()
                self.tokens.append(Token(single[ch], ch, self.line, self.col))
                continue

            self.error(f"Unexpected character '{ch}'")

        while len(self.indent_stack) > 1:
            self.indent_stack.pop()
            self.tokens.append(Token(TokenType.DEDENT, 0, self.line, self.col))

        self.tokens.append(Token(TokenType.EOF, None, self.line, self.col))
        return self.tokens
