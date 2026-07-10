#!/usr/bin/env python3

from typing import List
from pathlib import Path

SKEL_GRAMMAR_JS = """
/// <reference types="tree-sitter-cli/dsl" />
// @ts-check

export default grammar({
	name: "__NAME__",

	externals: ($) => [
		__SYMS__
		$._pad0,
		$._err
	],

	rules: {
		__NAME_TITLE__: $ => repeat(seq(
			optional($._pad0),
			choice(
				__SYMS__
			),
		))
	}
});
"""

SKEL_SCANNER_TOKENS_H = """
typedef enum {
    __SYMS_UPPERCASE__
    PAD0,
    ERR
} TokenType;
"""


def grammar(name: str, syms: List[str]):
    fmt_syms: str = "\n".join(map(lambda x: f"$.{x},", syms))
    txt = SKEL_GRAMMAR_JS.replace("__NAME__", name.lower())
    txt = txt.replace("__NAME_TITLE__", name.title())
    txt = txt.replace("__SYMS__", fmt_syms)

    path = Path(f"generated/{name.lower()}/grammar.js")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(txt)


def scanner(name: str, syms: List[str]):
    fmt_syms: str = "\n".join(map(lambda x: f"{x},", syms))
    txt = SKEL_SCANNER_TOKENS_H.replace("__SYMS_UPPERCASE__", fmt_syms.upper())

    path = Path(f"generated/{name.lower()}/src/scanner_tokens.h")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(txt)

    path_in = Path(f"examples/src/scanner.c")
    path = Path(f"generated/{name.lower()}/src/scanner.c")
    with open(path_in, "r") as f_in, open(path, "w") as f:
        f.write(f_in.read().replace("__NAME__", name.lower()))


HIGHLIGHTS = [
    "constant",
    "function",
    "keyword",
    "number.float",
    "punctuation",
    "type",
]


def highlights(name: str, syms: List[str]):
    path = Path(f"generated/{name.lower()}/queries/highlights.scm")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for i, sym in enumerate(syms):
            if sym == "pad":
                continue
            # f.write(f"({sym}) @{HIGHLIGHTS[i % len(HIGHLIGHTS)]}\n")
            f.write(f"({sym}) @bs{i % 5}\n")
