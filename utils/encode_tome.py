#!/usr/bin/env python3
"""Tome binary encoder with real MLModern font metrics."""

import os
import struct
from fontTools.t1Lib import T1Font
from fontTools.pens.basePen import NullPen
from fontTools.agl import UV2AGL

# Opcodes from PROPOSAL.md section 4.2
OP_RIGHT      = 0x01
OP_DOWN       = 0x02
OP_MOVETO     = 0x03
OP_CR         = 0x04
OP_LF_DOWN    = 0x05
OP_FONT_DEF   = 0x06
OP_FONT       = 0x07
OP_SECTION    = 0x08
OP_TAB        = 0x09
OP_NEWLINE    = 0x0A
OP_PARA       = 0x0B
OP_LIST_ITEM  = 0x0E
OP_LINK_DEF   = 0x0F
OP_LINK_START = 0x10
OP_LINK_END   = 0x11
OP_KERN       = 0x12
OP_LIGATURE   = 0x13
OP_RULE       = 0x14
OP_COLOR      = 0x15
OP_BG_COLOR   = 0x16
OP_IMAGE_DEF  = 0x17
OP_IMAGE      = 0x18
OP_META       = 0x19
OP_ANCHOR     = 0x1A
OP_PUSH       = 0x1B
OP_POP        = 0x1C
OP_EXTENSION  = 0x1E
OP_END        = 0xFF

SRC_DIR = '/Library/TeX/Root/texmf-dist/fonts/type1/public/mlmodern'
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'samples')


# --- PrefixVarint encoding ---

def encode_prefixvarint(n):
    """Encode unsigned integer as PrefixVarint.

    | First byte   | Total bytes | Value bits | Range                     |
    |0xxxxxxx      | 1           | 7          | 0 – 127                   |
    |10xxxxxx + 1  | 2           | 14         | 128 – 16,511              |
    |110xxxxx + 2  | 3           | 21         | 16,512 – 2,113,663        |
    |1110xxxx + 3  | 4           | 28         | 2,113,664 – 270,549,119   |
    |11110xxx + 4  | 5           | 35         | 270,549,120 – ~34B        |
    """
    assert n >= 0, f"PrefixVarint requires non-negative: {n}"
    if n < 0x80:  # 128
        return bytes([n])
    n -= 0x80
    if n < 0x4000:  # 16384
        return bytes([0x80 | (n >> 8), n & 0xFF])
    n -= 0x4000
    if n < 0x200000:  # 2097152
        return bytes([0xC0 | (n >> 16), (n >> 8) & 0xFF, n & 0xFF])
    n -= 0x200000
    if n < 0x10000000:  # 268435456
        return bytes([0xE0 | (n >> 24), (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF])
    n -= 0x10000000
    if n < 0x800000000:  # 34359738368
        return bytes([0xF0 | (n >> 32), (n >> 24) & 0xFF, (n >> 16) & 0xFF,
                       (n >> 8) & 0xFF, n & 0xFF])
    raise ValueError(f"Value too large for PrefixVarint: {n}")


def encode_signed_varint(n):
    """Encode signed integer as zigzag + PrefixVarint."""
    zigzag = (n << 1) ^ (n >> 63) if n >= 0 else ((-n - 1) << 1) | 1
    return encode_prefixvarint(zigzag)


def encode_string(s):
    """Encode string as varint length + UTF-8 bytes."""
    data = s.encode('utf-8')
    return encode_prefixvarint(len(data)) + data


# --- Opcode helpers ---

def op_right(sv):
    return bytes([OP_RIGHT]) + encode_signed_varint(sv)

def op_down(sv):
    return bytes([OP_DOWN]) + encode_signed_varint(sv)

def op_moveto(x, y):
    return bytes([OP_MOVETO]) + encode_signed_varint(x) + encode_signed_varint(y)

def op_cr():
    return bytes([OP_CR])

def op_lf_down(v):
    return bytes([OP_LF_DOWN]) + encode_prefixvarint(v)

def op_font_def(slot, hash_hi, hash_lo, size, name):
    return (bytes([OP_FONT_DEF]) + encode_prefixvarint(slot) +
            encode_prefixvarint(hash_hi) + encode_prefixvarint(hash_lo) +
            encode_prefixvarint(size) + encode_string(name))

def op_font(slot):
    return bytes([OP_FONT]) + encode_prefixvarint(slot)

def op_section(level):
    return bytes([OP_SECTION]) + encode_prefixvarint(level)

def op_para():
    return bytes([OP_PARA])

def op_list_item(depth=0):
    return bytes([OP_LIST_ITEM]) + encode_prefixvarint(depth)

def op_link_def(link_id, url):
    return bytes([OP_LINK_DEF]) + encode_prefixvarint(link_id) + encode_string(url)

def op_link_start(link_id):
    return bytes([OP_LINK_START]) + encode_prefixvarint(link_id)

def op_link_end():
    return bytes([OP_LINK_END])

def op_color(rgba):
    return bytes([OP_COLOR]) + encode_prefixvarint(rgba)

def op_bg_color(rgba):
    return bytes([OP_BG_COLOR]) + encode_prefixvarint(rgba)

def op_rule(w, h):
    return bytes([OP_RULE]) + encode_prefixvarint(w) + encode_prefixvarint(h)

def op_meta(key, val):
    return bytes([OP_META]) + encode_string(key) + encode_string(val)

def op_push():
    return bytes([OP_PUSH])

def op_pop():
    return bytes([OP_POP])

def op_end():
    return bytes([OP_END])


# --- Font metrics ---

class FontMetrics:
    """Load glyph widths from a Type1 PFB file."""

    def __init__(self, pfb_path):
        t1 = T1Font(pfb_path)
        t1.parse()
        self.gs = t1.getGlyphSet()
        self._widths = {}  # glyph name → width in Type1 units (UPM=1000)
        for gname in self.gs.keys():
            self.gs[gname].draw(NullPen())
            self._widths[gname] = self.gs[gname].width

    def char_width(self, ch, font_size_tu):
        """Get width of a character in tome units at given font size.

        font_size_tu is the font size in tome units (CSS px * 64).
        """
        # Map character to glyph name via AGL
        cp = ord(ch)
        gname = UV2AGL.get(cp, ch if len(ch) == 1 else None)
        if gname and gname in self._widths:
            w = self._widths[gname]
        elif ch in self._widths:
            w = self._widths[ch]
        else:
            w = self._widths.get('space', 333)
        return int(w * font_size_tu / 1000)

    def string_width(self, s, font_size_tu):
        """Get total width of a string in tome units."""
        return sum(self.char_width(ch, font_size_tu) for ch in s)


# Load metrics for the core fonts
_metrics_cache = {}

def get_metrics(font_name):
    if font_name not in _metrics_cache:
        pfb_path = os.path.join(SRC_DIR, f'{font_name}.pfb')
        _metrics_cache[font_name] = FontMetrics(pfb_path)
    return _metrics_cache[font_name]


# --- Tome unit helpers ---

def px(css_px):
    """Convert CSS pixels to tome units (1 tu = 1/64 CSS px)."""
    return int(css_px * 64)


# --- Text rendering helpers ---

def encode_text_at(text, metrics, font_size_tu, x, y):
    """Encode a text string positioned at (x, y) with cursor advancement.

    Returns (bytes, new_x) where new_x is the cursor position after the text.
    """
    buf = bytearray()
    # Move to position
    buf += op_moveto(x, y)
    # Write characters one by one (UTF-8 bytes are the content)
    buf += text.encode('utf-8')
    new_x = x + metrics.string_width(text, font_size_tu)
    return bytes(buf), new_x


def encode_line(text, metrics, font_size_tu, left_margin):
    """Encode a line of text starting from the left margin.

    Returns bytes (assumes cursor y is already set, uses CR + text).
    """
    buf = bytearray()
    buf += op_cr()
    buf += op_right(left_margin)
    buf += text.encode('utf-8')
    return bytes(buf)


# --- Sample generators ---

def generate_hello():
    """Generate samples/hello.tome — minimal heading + one line."""
    roman = get_metrics('mlmr10')
    bold = get_metrics('mlmbx10')

    body_size = px(16)      # 16 CSS px
    heading_size = px(24)   # 24 CSS px
    left_margin = px(50)    # 50 CSS px
    top_margin = px(50)     # 50 CSS px
    content_width = px(450) # 450 CSS px
    line_height = px(24)    # 24 CSS px (1.5x body)
    heading_line = px(34)   # 34 CSS px (1.4x heading)

    buf = bytearray()

    # Metadata
    buf += op_meta('title', 'Hello, Tome')
    buf += op_meta('lang', 'en')
    buf += op_meta('width', str(content_width + 2 * left_margin))

    # Font definitions (slot, hash_hi, hash_lo, size, name)
    buf += op_font_def(0, 0, 1, body_size, 'mlmr10')
    buf += op_font_def(1, 0, 2, heading_size, 'mlmbx10')

    # Position at top-left
    buf += op_moveto(left_margin, top_margin + heading_size)

    # Heading
    buf += op_section(1)
    buf += op_font(1)
    buf += 'Hello, Tome'.encode('utf-8')

    # Move to body
    buf += op_lf_down(heading_line + px(10))

    # Body text
    buf += op_para()
    buf += op_font(0)
    buf += 'This is a minimal tome document rendered with MLModern fonts.'.encode('utf-8')

    buf += op_end()

    path = os.path.join(OUT_DIR, 'hello.tome')
    with open(path, 'wb') as f:
        f.write(buf)
    print(f'Generated {path} ({len(buf)} bytes)')


def generate_article():
    """Generate samples/article.tome — heading, paragraphs, link, font changes, rule."""
    roman = get_metrics('mlmr10')
    bold = get_metrics('mlmbx10')
    italic = get_metrics('mlmri10')
    mono = get_metrics('mlmtt10')

    body_size = px(16)
    heading_size = px(24)
    h2_size = px(20)
    mono_size = px(14)
    left_margin = px(50)
    top_margin = px(50)
    content_width = px(450)
    line_height = px(24)
    heading_line = px(34)
    h2_line = px(28)
    para_skip = px(12)

    buf = bytearray()

    # --- Preamble ---
    buf += op_meta('title', 'The Tome Format')
    buf += op_meta('author', 'A Typographer')
    buf += op_meta('lang', 'en')
    buf += op_meta('width', str(content_width + 2 * left_margin))

    # Font definitions
    buf += op_font_def(0, 0, 1, body_size, 'mlmr10')      # Roman
    buf += op_font_def(1, 0, 2, heading_size, 'mlmbx10')   # Bold heading
    buf += op_font_def(2, 0, 3, body_size, 'mlmri10')      # Italic
    buf += op_font_def(3, 0, 4, body_size, 'mlmbx10')      # Bold body
    buf += op_font_def(4, 0, 5, mono_size, 'mlmtt10')      # Mono
    buf += op_font_def(5, 0, 6, h2_size, 'mlmbx10')        # H2

    # Link definitions
    buf += op_link_def(0, 'https://en.wikipedia.org/wiki/Device_independent_file_format')

    # --- Title ---
    y = top_margin + heading_size
    buf += op_moveto(left_margin, y)
    buf += op_section(1)
    buf += op_font(1)
    buf += 'The Tome Format'.encode('utf-8')
    y += heading_line + para_skip

    # --- Paragraph 1 ---
    buf += op_para()
    buf += op_font(0)

    p1_lines = wrap_text(
        "Tome is a binary document format for the web, designed to replace "
        "HTML for document-centric content. It is inspired by TeX's DVI format "
        "but simplified for web delivery. The goal is minimal latency from HTTP "
        "GET to first rendered screen, with good typography and tiny file sizes.",
        roman, body_size, content_width
    )
    for line in p1_lines:
        buf += op_moveto(left_margin, y)
        buf += line.encode('utf-8')
        y += line_height

    y += para_skip

    # --- Paragraph 2 with italic and bold ---
    buf += op_para()

    # "The format uses " (roman)
    seg1 = "The format uses "
    buf += op_moveto(left_margin, y)
    buf += op_font(0)
    buf += seg1.encode('utf-8')
    x = left_margin + roman.string_width(seg1, body_size)

    # "ASCII control characters" (italic)
    seg2 = "ASCII control characters"
    buf += op_font(2)
    buf += seg2.encode('utf-8')
    x += italic.string_width(seg2, body_size)

    # " as opcodes and renders " (roman)
    seg3 = " as opcodes and renders "
    buf += op_font(0)
    buf += seg3.encode('utf-8')
    x += roman.string_width(seg3, body_size)

    # "printable characters" (bold)
    seg4 = "printable characters"
    buf += op_font(3)
    buf += seg4.encode('utf-8')
    x += bold.string_width(seg4, body_size)

    # " directly." (roman)
    seg5 = " directly."
    buf += op_font(0)
    buf += seg5.encode('utf-8')
    y += line_height

    p2_rest = wrap_text(
        "Plain UTF-8 text is a valid tome document. Any text file you write "
        "in Notepad is renderable as tome, displayed in MLModern Typewriter.",
        roman, body_size, content_width
    )
    for line in p2_rest:
        buf += op_moveto(left_margin, y)
        buf += line.encode('utf-8')
        y += line_height

    y += para_skip

    # --- Horizontal rule ---
    buf += op_moveto(left_margin, y)
    buf += op_rule(content_width, px(0.5))
    y += px(12)
    y += para_skip

    # --- H2: "Design Goals" ---
    buf += op_section(2)
    buf += op_font(5)
    buf += op_moveto(left_margin, y)
    buf += 'Design Goals'.encode('utf-8')
    y += h2_line + para_skip

    # --- Paragraph 3 with a link ---
    buf += op_para()
    buf += op_font(0)

    seg_a = "The format draws from the "
    buf += op_moveto(left_margin, y)
    buf += seg_a.encode('utf-8')
    x = left_margin + roman.string_width(seg_a, body_size)

    # Link
    buf += op_link_start(0)
    buf += op_color(0x2255AAFF)
    link_text = "DVI file format"
    buf += link_text.encode('utf-8')
    buf += op_color(0x333333FF)
    buf += op_link_end()
    x += roman.string_width(link_text, body_size)

    seg_b = ", pre-computing all"
    buf += seg_b.encode('utf-8')
    y += line_height

    p3_rest = wrap_text(
        "character positions so the reader just draws. No CSS cascade, "
        "no JavaScript, no layout computation. A 2,000-word article "
        "is about 19 KB as tome, versus 2 MB as a typical web page.",
        roman, body_size, content_width
    )
    for line in p3_rest:
        buf += op_moveto(left_margin, y)
        buf += line.encode('utf-8')
        y += line_height

    y += para_skip

    # --- Code sample ---
    buf += op_para()
    buf += op_font(4)  # mono
    code_lines = [
        "META \"title\" \"My Article\"",
        "FONT_DEF 0 ... \"mlmr10\"",
        "Hello, world!",
        "0xFF  # end",
    ]
    for line in code_lines:
        buf += op_moveto(left_margin + px(20), y)
        buf += line.encode('utf-8')
        y += px(20)

    buf += op_end()

    path = os.path.join(OUT_DIR, 'article.tome')
    with open(path, 'wb') as f:
        f.write(buf)
    print(f'Generated {path} ({len(buf)} bytes)')


def wrap_text(text, metrics, font_size_tu, max_width):
    """Simple greedy word-wrap returning list of lines."""
    words = text.split(' ')
    lines = []
    current = ''
    for word in words:
        test = (current + ' ' + word).strip()
        if metrics.string_width(test, font_size_tu) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    generate_hello()
    generate_article()
    print(f'\nSample files in {OUT_DIR}')


if __name__ == '__main__':
    main()
