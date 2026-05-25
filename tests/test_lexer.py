#!/usr/bin/env python3
"""Tests for the Million lexer."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compiler.lexer import Lexer
from compiler.token import TokenType


def test_basic_tokens():
    source = "neuron DNA { }"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    assert tokens[0].type == TokenType.KEYWORD and tokens[0].value == "neuron"
    assert tokens[1].type == TokenType.IDENTIFIER and tokens[1].value == "DNA"
    assert tokens[2].type == TokenType.LBRACE
    assert tokens[3].type == TokenType.RBRACE
    assert tokens[4].type == TokenType.EOF
    print("  [ok] test_basic_tokens")


def test_numbers():
    source = "42 3.14"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    assert tokens[0].type == TokenType.NUMBER and tokens[0].value == 42
    assert tokens[1].type == TokenType.FLOAT and tokens[1].value == 3.14
    print("  [ok] test_numbers")


def test_string():
    source = '"hello world"'
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    assert tokens[0].type == TokenType.STRING and tokens[0].value == "hello world"
    print("  [ok] test_string")


def test_comment():
    source = "// this is a comment\nneuron"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    assert tokens[0].type == TokenType.NEWLINE
    assert tokens[1].type == TokenType.KEYWORD and tokens[1].value == "neuron"
    print("  [ok] test_comment")


def test_operators():
    source = "-> => = + - * / { } ( ) [ ] : , ."
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    types = [t.type for t in tokens if t.type != TokenType.EOF]
    expected = [
        TokenType.ARROW, TokenType.FAT_ARROW, TokenType.EQUALS,
        TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
        TokenType.LBRACE, TokenType.RBRACE,
        TokenType.LPAREN, TokenType.RPAREN,
        TokenType.LBRACKET, TokenType.RBRACKET,
        TokenType.COLON, TokenType.COMMA, TokenType.DOT,
    ]
    assert types == expected, f"Expected {expected}, got {types}"
    print("  [ok] test_operators")


def test_keywords():
    source = "neuron region data train infer connect archive state membrane dynamics"
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    for t in tokens:
        if t.type == TokenType.EOF:
            break
        assert t.type == TokenType.KEYWORD, f"Expected KEYWORD, got {t}"
    print("  [ok] test_keywords")


if __name__ == "__main__":
    print("Running lexer tests...")
    test_basic_tokens()
    test_numbers()
    test_string()
    test_comment()
    test_operators()
    test_keywords()
    print("All lexer tests passed!")
