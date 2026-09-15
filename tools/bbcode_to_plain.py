#!/usr/bin/env python3
"""Generate the Paradox Mods descriptions from the Steam BBCode ones.

Paradox Mods takes plain text, so the two versions would drift apart if both
were maintained by hand. Steam is the source, this is the derivative.

Usage: tools/bbcode_to_plain.py
"""
import pathlib
import re

WS = pathlib.Path(__file__).resolve().parent.parent / "steam-workshop"


def convert(text):
    text = re.sub(r"\[h1\](.*?)\[/h1\]", r"\1", text)
    text = re.sub(r"\[h2\](.*?)\[/h2\]", lambda m: m.group(1).upper(), text)
    text = re.sub(r"\[url=(.*?)\](.*?)\[/url\]", r"\1", text)
    text = re.sub(r"\[/?(b|i|code)\]", "", text)
    text = re.sub(r"^\[/?list\]\n", "", text, flags=re.M)
    text = re.sub(r"^\[\*\]", "- ", text, flags=re.M)
    return text


def main():
    for lang in ("en", "ru"):
        src = WS / f"description-{lang}.txt"
        dst = WS / f"description-paradoxmods-{lang}.txt"
        dst.write_text(convert(src.read_text()))
        print(f"{dst.name} <- {src.name}")


if __name__ == "__main__":
    main()
