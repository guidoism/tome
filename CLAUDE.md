# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tome is a proposed binary document format for the web, designed to replace HTML for document-centric content. It's inspired by TeX's DVI (DeVice Independent) format but simplified for web delivery. The goal is minimal latency from HTTP GET to first rendered screen, with good typography and tiny file sizes.

The README.md is the primary specification document. The format uses ASCII control characters (0x01-0x1F) as opcodes and renders printable characters (0x20-0x7F) directly. Font references use hashes, numbers use variable-width integers (LEB128).

## Key Commands

The example DVI file was generated with LuaTeX:
```bash
luatex example1.tex           # produces example1.dvi
dvitype example1.dvi          # inspect DVI opcodes (output in example1.dvitype)
```

Python utilities (require `freetype-py`, `Pillow`, `leb128`):
```bash
python utils/dumpdvi.py example1.dvi    # hex dump of DVI bytes
python utils/render.py                  # render a glyph to PNG using freetype
python utils/varints.py                 # LEB128 varint encoding experiments
```

The site is served via Jekyll (GitHub Pages). The layout is in `_layouts/default.html`.

## Architecture

- `README.md` — The format specification, including proposed opcodes, encoding scheme, and design rationale
- `example1.*` — A single example ("effin effin") in multiple formats: `.tex` source, `.dvi` binary, `.dvitype` disassembly, `.org` annotated byte-level walkthrough, `.pdf` and `.png` rendered output
- `utils/` — Python scripts for exploring DVI internals and font rendering
- `_layouts/` — Jekyll template using Equity and Concourse fonts

## Format Design Decisions

- Opcodes 0x10-0x15 are proposed tome commands: set_scale (0x10), right (0x11), down (0x12), load_font (0x13), set_font (0x14), ligature (0x15)
- Font slots are local identifiers; fonts are identified by 4-byte hashes
- Default fonts are MLModern (mlmtt10 for monospace, mlmr10 for roman) from TeX Live at `/Library/TeX/Root/texmf-dist/fonts/`
- Plain UTF-8 text is a valid tome document (rendered in MLModern typewriter)
