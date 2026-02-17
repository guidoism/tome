#!/usr/bin/env python3
"""Convert DVI files to .tome binary format.

Usage: python3 dvi2tome.py input.dvi output.tome

Parses a TeX DVI file, translates OT1 or T1 (Cork) encoded characters to
Unicode, and emits the equivalent tome binary stream using the encode_tome
helpers. Font encoding is detected automatically from the font name:
  - ec- prefix  -> T1 (Cork / EC) encoding (256 slots)
  - tt in name  -> OT1-TT (original TeX typewriter, ASCII-like)
  - otherwise   -> OT1 (original TeX text, smart quotes/dashes)
"""

import sys
import os

# Make sure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encode_tome import (
    px, encode_prefixvarint, encode_signed_varint, encode_string,
    op_meta, op_font_def, op_font, op_section, op_para, op_moveto,
    op_right, op_down, op_lf_down, op_link_def, op_link_start, op_link_end,
    op_color, op_rule, op_end, op_push, op_pop,
)


# ---------------------------------------------------------------------------
# T1 (Cork / EC) encoding -> Unicode mapping (all 256 slots)
# ---------------------------------------------------------------------------
# References:
#   - LaTeX T1 encoding table (fontenc package)
#   - The Cork encoding (TUGboat, Vol. 11, No. 4)
#   - EC fonts documentation
# ---------------------------------------------------------------------------

T1_TO_UNICODE = {
    # 0x00-0x07: accents used as standalone characters
    0x00: 0x0060,  # grave accent `
    0x01: 0x00B4,  # acute accent (spacing)
    0x02: 0x02C6,  # circumflex (modifier letter)
    0x03: 0x02DC,  # tilde (small)
    0x04: 0x00A8,  # dieresis
    0x05: 0x02DD,  # hungarumlaut (double acute)
    0x06: 0x02DA,  # ring above
    0x07: 0x02C7,  # caron

    # 0x08-0x0F: more accents and special characters
    0x08: 0x02D8,  # breve
    0x09: 0x00AF,  # macron
    0x0A: 0x02D9,  # dot above
    0x0B: 0x00B8,  # cedilla
    0x0C: 0x02DB,  # ogonek
    0x0D: 0x201A,  # quotesinglbase (single low-9 quotation mark)
    0x0E: 0x2039,  # guilsinglleft (single left-pointing angle quotation mark)
    0x0F: 0x203A,  # guilsinglright (single right-pointing angle quotation mark)

    # 0x10-0x17: quotation marks and dashes
    0x10: 0x201C,  # quotedblleft (left double quotation mark)
    0x11: 0x201D,  # quotedblright (right double quotation mark)
    0x12: 0x201E,  # quotedblbase (double low-9 quotation mark)
    0x13: 0x00AB,  # guillemotleft (left-pointing double angle quotation mark)
    0x14: 0x00BB,  # guillemotright (right-pointing double angle quotation mark)
    0x15: 0x2013,  # endash
    0x16: 0x2014,  # emdash
    0x17: 0x200C,  # compwordmark (zero-width non-joiner, ZWNJ)

    # 0x18-0x1F: miscellaneous
    0x18: 0x2030,  # perthousandzero -- actually this is perthousand in some refs;
                    # but in T1 encoding slot 0x18 is the "perthousand zero" (visually
                    # a zero used in per-mille sign). We map to the perthousand symbol.
                    # Some implementations map to 0x2030 (per mille sign).
    0x19: 0x0131,  # dotlessi
    0x1A: 0x0237,  # dotlessj
    0x1B: 0xFB00,  # ff ligature
    0x1C: 0xFB01,  # fi ligature
    0x1D: 0xFB02,  # fl ligature
    0x1E: 0xFB03,  # ffi ligature
    0x1F: 0xFB04,  # ffl ligature

    # 0x20-0x7E: ASCII printable range (mostly identity mapping with a few overrides)
    0x20: 0x0020,  # space
    0x21: 0x0021,  # exclam
    0x22: 0x0022,  # quotedbl
    0x23: 0x0023,  # numbersign
    0x24: 0x0024,  # dollar
    0x25: 0x0025,  # percent
    0x26: 0x0026,  # ampersand
    0x27: 0x2019,  # quoteright (right single quotation mark) -- NOT ASCII apostrophe
    0x28: 0x0028,  # parenleft
    0x29: 0x0029,  # parenright
    0x2A: 0x002A,  # asterisk
    0x2B: 0x002B,  # plus
    0x2C: 0x002C,  # comma
    0x2D: 0x002D,  # hyphen
    0x2E: 0x002E,  # period
    0x2F: 0x002F,  # slash

    0x30: 0x0030,  # zero
    0x31: 0x0031,  # one
    0x32: 0x0032,  # two
    0x33: 0x0033,  # three
    0x34: 0x0034,  # four
    0x35: 0x0035,  # five
    0x36: 0x0036,  # six
    0x37: 0x0037,  # seven
    0x38: 0x0038,  # eight
    0x39: 0x0039,  # nine
    0x3A: 0x003A,  # colon
    0x3B: 0x003B,  # semicolon
    0x3C: 0x003C,  # less
    0x3D: 0x003D,  # equal
    0x3E: 0x003E,  # greater
    0x3F: 0x003F,  # question

    0x40: 0x0040,  # at
    0x41: 0x0041,  # A
    0x42: 0x0042,  # B
    0x43: 0x0043,  # C
    0x44: 0x0044,  # D
    0x45: 0x0045,  # E
    0x46: 0x0046,  # F
    0x47: 0x0047,  # G
    0x48: 0x0048,  # H
    0x49: 0x0049,  # I
    0x4A: 0x004A,  # J
    0x4B: 0x004B,  # K
    0x4C: 0x004C,  # L
    0x4D: 0x004D,  # M
    0x4E: 0x004E,  # N
    0x4F: 0x004F,  # O
    0x50: 0x0050,  # P
    0x51: 0x0051,  # Q
    0x52: 0x0052,  # R
    0x53: 0x0053,  # S
    0x54: 0x0054,  # T
    0x55: 0x0055,  # U
    0x56: 0x0056,  # V
    0x57: 0x0057,  # W
    0x58: 0x0058,  # X
    0x59: 0x0059,  # Y
    0x5A: 0x005A,  # Z
    0x5B: 0x005B,  # bracketleft
    0x5C: 0x005C,  # backslash
    0x5D: 0x005D,  # bracketright
    0x5E: 0x005E,  # asciicircum
    0x5F: 0x005F,  # underscore

    0x60: 0x2018,  # quoteleft (left single quotation mark) -- NOT ASCII grave
    0x61: 0x0061,  # a
    0x62: 0x0062,  # b
    0x63: 0x0063,  # c
    0x64: 0x0064,  # d
    0x65: 0x0065,  # e
    0x66: 0x0066,  # f
    0x67: 0x0067,  # g
    0x68: 0x0068,  # h
    0x69: 0x0069,  # i
    0x6A: 0x006A,  # j
    0x6B: 0x006B,  # k
    0x6C: 0x006C,  # l
    0x6D: 0x006D,  # m
    0x6E: 0x006E,  # n
    0x6F: 0x006F,  # o
    0x70: 0x0070,  # p
    0x71: 0x0071,  # q
    0x72: 0x0072,  # r
    0x73: 0x0073,  # s
    0x74: 0x0074,  # t
    0x75: 0x0075,  # u
    0x76: 0x0076,  # v
    0x77: 0x0077,  # w
    0x78: 0x0078,  # x
    0x79: 0x0079,  # y
    0x7A: 0x007A,  # z
    0x7B: 0x007B,  # braceleft
    0x7C: 0x007C,  # bar
    0x7D: 0x007D,  # braceright
    0x7E: 0x007E,  # asciitilde

    0x7F: 0x002D,  # hyphen (same as 0x2D)

    # 0x80-0xFF: Accented and special Latin characters
    # Row 0x80-0x8F
    0x80: 0x0102,  # Abreve
    0x81: 0x0104,  # Aogonek
    0x82: 0x0106,  # Cacute
    0x83: 0x010C,  # Ccaron
    0x84: 0x010E,  # Dcaron
    0x85: 0x011A,  # Ecaron
    0x86: 0x0118,  # Eogonek
    0x87: 0x011E,  # Gbreve
    0x88: 0x0139,  # Lacute
    0x89: 0x013D,  # Lcaron
    0x8A: 0x0141,  # Lslash
    0x8B: 0x0143,  # Nacute
    0x8C: 0x0147,  # Ncaron
    0x8D: 0x014A,  # Eng
    0x8E: 0x0150,  # Ohungarumlaut
    0x8F: 0x0154,  # Racute

    # Row 0x90-0x9F
    0x90: 0x0158,  # Rcaron
    0x91: 0x015A,  # Sacute
    0x92: 0x0160,  # Scaron
    0x93: 0x015E,  # Scedilla
    0x94: 0x0164,  # Tcaron
    0x95: 0x0162,  # Tcedilla
    0x96: 0x0170,  # Uhungarumlaut
    0x97: 0x016E,  # Uring
    0x98: 0x0178,  # Ydieresis
    0x99: 0x0179,  # Zacute
    0x9A: 0x017D,  # Zcaron
    0x9B: 0x017B,  # Zdotaccent
    0x9C: 0x0132,  # IJ
    0x9D: 0x0130,  # Idotaccent
    0x9E: 0x0111,  # dcroat (d with stroke -- lowercase, but T1 puts it here)
    0x9F: 0x00A7,  # section sign

    # Row 0xA0-0xAF
    0xA0: 0x0103,  # abreve
    0xA1: 0x0105,  # aogonek
    0xA2: 0x0107,  # cacute
    0xA3: 0x010D,  # ccaron
    0xA4: 0x010F,  # dcaron
    0xA5: 0x011B,  # ecaron
    0xA6: 0x0119,  # eogonek
    0xA7: 0x011F,  # gbreve
    0xA8: 0x013A,  # lacute
    0xA9: 0x013E,  # lcaron
    0xAA: 0x0142,  # lslash
    0xAB: 0x0144,  # nacute
    0xAC: 0x0148,  # ncaron
    0xAD: 0x014B,  # eng
    0xAE: 0x0151,  # ohungarumlaut
    0xAF: 0x0155,  # racute

    # Row 0xB0-0xBF
    0xB0: 0x0159,  # rcaron
    0xB1: 0x015B,  # sacute
    0xB2: 0x0161,  # scaron
    0xB3: 0x015F,  # scedilla
    0xB4: 0x0165,  # tcaron
    0xB5: 0x0163,  # tcedilla
    0xB6: 0x0171,  # uhungarumlaut
    0xB7: 0x016F,  # uring
    0xB8: 0x00FF,  # ydieresis
    0xB9: 0x017A,  # zacute
    0xBA: 0x017E,  # zcaron
    0xBB: 0x017C,  # zdotaccent
    0xBC: 0x00A1,  # exclamdown
    0xBD: 0x00BF,  # questiondown
    0xBE: 0x00A3,  # sterling
    0xBF: 0x00C6,  # AE

    # 0xC0-0xFF: see _T1_UPPER_ACCENTED below (Latin-1-like block)
}

# Override 0xBF-0xFF with the standard T1 encoding for accented characters
# The T1 encoding in 0xC0-0xFF matches Latin-1 (ISO 8859-1) for the most part
_T1_UPPER_ACCENTED = {
    0xC0: 0x00C0,  # Agrave
    0xC1: 0x00C1,  # Aacute
    0xC2: 0x00C2,  # Acircumflex
    0xC3: 0x00C3,  # Atilde
    0xC4: 0x00C4,  # Adieresis
    0xC5: 0x00C5,  # Aring
    0xC6: 0x00C6,  # AE
    0xC7: 0x00C7,  # Ccedilla
    0xC8: 0x00C8,  # Egrave
    0xC9: 0x00C9,  # Eacute
    0xCA: 0x00CA,  # Ecircumflex
    0xCB: 0x00CB,  # Edieresis
    0xCC: 0x00CC,  # Igrave
    0xCD: 0x00CD,  # Iacute
    0xCE: 0x00CE,  # Icircumflex
    0xCF: 0x00CF,  # Idieresis

    0xD0: 0x00D0,  # Eth
    0xD1: 0x00D1,  # Ntilde
    0xD2: 0x00D2,  # Ograve
    0xD3: 0x00D3,  # Oacute
    0xD4: 0x00D4,  # Ocircumflex
    0xD5: 0x00D5,  # Otilde
    0xD6: 0x00D6,  # Odieresis
    0xD7: 0x0152,  # OE ligature (T1 differs from Latin-1 here; Latin-1 has multiply sign)
    0xD8: 0x00D8,  # Oslash
    0xD9: 0x00D9,  # Ugrave
    0xDA: 0x00DA,  # Uacute
    0xDB: 0x00DB,  # Ucircumflex
    0xDC: 0x00DC,  # Udieresis
    0xDD: 0x00DD,  # Yacute
    0xDE: 0x00DE,  # Thorn
    0xDF: 0x1E9E,  # Germandbls (capital sharp S, U+1E9E)

    0xE0: 0x00E0,  # agrave
    0xE1: 0x00E1,  # aacute
    0xE2: 0x00E2,  # acircumflex
    0xE3: 0x00E3,  # atilde
    0xE4: 0x00E4,  # adieresis
    0xE5: 0x00E5,  # aring
    0xE6: 0x00E6,  # ae
    0xE7: 0x00E7,  # ccedilla
    0xE8: 0x00E8,  # egrave
    0xE9: 0x00E9,  # eacute
    0xEA: 0x00EA,  # ecircumflex
    0xEB: 0x00EB,  # edieresis
    0xEC: 0x00EC,  # igrave
    0xED: 0x00ED,  # iacute
    0xEE: 0x00EE,  # icircumflex
    0xEF: 0x00EF,  # idieresis

    0xF0: 0x00F0,  # eth
    0xF1: 0x00F1,  # ntilde
    0xF2: 0x00F2,  # ograve
    0xF3: 0x00F3,  # oacute
    0xF4: 0x00F4,  # ocircumflex
    0xF5: 0x00F5,  # otilde
    0xF6: 0x00F6,  # odieresis
    0xF7: 0x0153,  # oe ligature (T1 differs from Latin-1; Latin-1 has division sign)
    0xF8: 0x00F8,  # oslash
    0xF9: 0x00F9,  # ugrave
    0xFA: 0x00FA,  # uacute
    0xFB: 0x00FB,  # ucircumflex
    0xFC: 0x00FC,  # udieresis
    0xFD: 0x00FD,  # yacute
    0xFE: 0x00FE,  # thorn
    0xFF: 0x00DF,  # germandbls (sharp S)
}

T1_TO_UNICODE.update(_T1_UPPER_ACCENTED)

# Also fix BF — in T1, 0xBF is AE (uppercase); we already have it above but
# the authoritative source says 0xBF = 0x00C6 (AE). Let's keep what we have.
# Actually, looking more carefully: the standard T1 layout has:
#   0xBF = AE (U+00C6) -- but we also have 0xC6 = AE from Latin-1 block.
# The official T1 encoding table:
#   0xBF = AE, 0xC6 = AE -- these overlap. The "correct" T1 has 0xC6 as AE in the
#   Latin-1-like block. 0xBF in T1 is actually AE as well. This is intentional:
#   the EC fonts encode AE in both slots for compatibility.

# Validate: every slot 0x00-0xFF should be present
for i in range(256):
    if i not in T1_TO_UNICODE:
        # This should not happen with the complete table above.
        # Fall back to Latin-1 identity for any missing slots.
        T1_TO_UNICODE[i] = i


# ---------------------------------------------------------------------------
# OT1 (Original TeX) encoding -> Unicode mapping
# ---------------------------------------------------------------------------
# OT1 is the classic 7-bit TeX encoding (Computer Modern / MLModern without
# the ec- prefix). Only slots 0x00-0x7F are used. Fonts loaded without
# \usepackage[T1]{fontenc} or without the ec- prefix use this encoding.
# ---------------------------------------------------------------------------

OT1_TO_UNICODE = {}

# 0x00-0x09: uppercase Greek
OT1_TO_UNICODE[0x00] = 0x0393  # Gamma
OT1_TO_UNICODE[0x01] = 0x0394  # Delta
OT1_TO_UNICODE[0x02] = 0x0398  # Theta
OT1_TO_UNICODE[0x03] = 0x039B  # Lambda
OT1_TO_UNICODE[0x04] = 0x039E  # Xi
OT1_TO_UNICODE[0x05] = 0x03A0  # Pi
OT1_TO_UNICODE[0x06] = 0x03A3  # Sigma
OT1_TO_UNICODE[0x07] = 0x03A5  # Upsilon
OT1_TO_UNICODE[0x08] = 0x03A6  # Phi
OT1_TO_UNICODE[0x09] = 0x03A8  # Psi
OT1_TO_UNICODE[0x0A] = 0x03A9  # Omega

# 0x0B-0x0F: ligatures and special
OT1_TO_UNICODE[0x0B] = 0xFB00  # ff ligature
OT1_TO_UNICODE[0x0C] = 0xFB01  # fi ligature
OT1_TO_UNICODE[0x0D] = 0xFB02  # fl ligature
OT1_TO_UNICODE[0x0E] = 0xFB03  # ffi ligature
OT1_TO_UNICODE[0x0F] = 0xFB04  # ffl ligature

# 0x10-0x11: dotlessi, dotlessj
OT1_TO_UNICODE[0x10] = 0x0131  # dotlessi
OT1_TO_UNICODE[0x11] = 0x0237  # dotlessj

# 0x12-0x13: grave and acute accents
OT1_TO_UNICODE[0x12] = 0x0060  # grave accent
OT1_TO_UNICODE[0x13] = 0x00B4  # acute accent

# 0x14-0x15: caron and breve
OT1_TO_UNICODE[0x14] = 0x02C7  # caron (hacek)
OT1_TO_UNICODE[0x15] = 0x02D8  # breve

# 0x16-0x17: macron and ring
OT1_TO_UNICODE[0x16] = 0x00AF  # macron
OT1_TO_UNICODE[0x17] = 0x00B8  # cedilla

# 0x18-0x19: germandbls and special
OT1_TO_UNICODE[0x18] = 0x00DF  # germandbls (sharp S)
OT1_TO_UNICODE[0x19] = 0x00E6  # ae

# 0x1A-0x1B: oe and oslash
OT1_TO_UNICODE[0x1A] = 0x0153  # oe
OT1_TO_UNICODE[0x1B] = 0x00F8  # oslash

# 0x1C-0x1D: AE and OE
OT1_TO_UNICODE[0x1C] = 0x00C6  # AE
OT1_TO_UNICODE[0x1D] = 0x0152  # OE

# 0x1E: Oslash (or sometimes used as empty set/null)
OT1_TO_UNICODE[0x1E] = 0x00D8  # Oslash

# 0x1F: special (varies; some fonts use it for dotted I, others for exclamdown)
# In CMR/MLModern it's typically unused or a special character
OT1_TO_UNICODE[0x1F] = 0x0020  # fallback to space

# 0x20: space (in some OT1 fonts this might be a visible space mark)
# For typewriter fonts, 0x20 is a space; for text fonts, it might be
# a special character. We map it to space universally.
OT1_TO_UNICODE[0x20] = 0x0020  # space

# 0x21-0x7E: mostly ASCII, with some OT1-specific overrides
for i in range(0x21, 0x7F):
    OT1_TO_UNICODE[i] = i  # identity for most ASCII printable

# OT1 overrides in the ASCII range:
OT1_TO_UNICODE[0x22] = 0x201D  # quotedblright (") -- not ASCII double quote
OT1_TO_UNICODE[0x27] = 0x2019  # quoteright (') -- not ASCII apostrophe
OT1_TO_UNICODE[0x3C] = 0x00A1  # exclamdown (in CMR; < in CMTT)
OT1_TO_UNICODE[0x3E] = 0x00BF  # questiondown (in CMR; > in CMTT)
OT1_TO_UNICODE[0x5C] = 0x201C  # quotedblleft (\) -- in CMR text fonts
OT1_TO_UNICODE[0x5F] = 0x02D9  # dotaccent (_) -- in CMR
OT1_TO_UNICODE[0x60] = 0x2018  # quoteleft (`)
OT1_TO_UNICODE[0x7B] = 0x2013  # endash ({) -- in CMR text fonts
OT1_TO_UNICODE[0x7C] = 0x2014  # emdash (|) -- in CMR text fonts
OT1_TO_UNICODE[0x7D] = 0x02DD  # hungarumlaut (}) -- in CMR text fonts
OT1_TO_UNICODE[0x7E] = 0x02DC  # tilde (~) -- in CMR text fonts

# 0x7F: hyphen in OT1 (same as 0x2D)
OT1_TO_UNICODE[0x7F] = 0x002D  # hyphen

# 0x80-0xFF: not used in standard OT1 (7-bit encoding)
for i in range(0x80, 0x100):
    OT1_TO_UNICODE[i] = i  # identity fallback for any out-of-range chars

# OT1 overrides for typewriter fonts (cmtt/mlmtt):
# In typewriter OT1 fonts, some slots differ from text fonts:
#   0x22 = " (ASCII double quote), not smart quote
#   0x27 = ' (ASCII apostrophe), not smart quote
#   0x3C = < (less-than), not exclamdown
#   0x3E = > (greater-than), not questiondown
#   0x5C = \ (backslash), not quotedblleft
#   0x5F = _ (underscore), not dotaccent
#   0x60 = ` (grave), not quoteleft
#   0x7B = { (braceleft), not endash
#   0x7C = | (bar), not emdash
#   0x7D = } (braceright), not hungarumlaut
#   0x7E = ~ (tilde), not spacing tilde

OT1_TT_TO_UNICODE = dict(OT1_TO_UNICODE)
OT1_TT_TO_UNICODE[0x22] = 0x0022  # ASCII double quote
OT1_TT_TO_UNICODE[0x27] = 0x0027  # ASCII apostrophe
OT1_TT_TO_UNICODE[0x3C] = 0x003C  # less-than
OT1_TT_TO_UNICODE[0x3E] = 0x003E  # greater-than
OT1_TT_TO_UNICODE[0x5C] = 0x005C  # backslash
OT1_TT_TO_UNICODE[0x5F] = 0x005F  # underscore
OT1_TT_TO_UNICODE[0x60] = 0x0060  # grave accent
OT1_TT_TO_UNICODE[0x7B] = 0x007B  # braceleft
OT1_TT_TO_UNICODE[0x7C] = 0x007C  # bar
OT1_TT_TO_UNICODE[0x7D] = 0x007D  # braceright
OT1_TT_TO_UNICODE[0x7E] = 0x007E  # tilde



# ---------------------------------------------------------------------------
# TS1 — Text Companion encoding (used by ts1-* fonts for symbols)
# Only the most commonly used slots. Others fall through to Unicode code point.
# ---------------------------------------------------------------------------

TS1_TO_UNICODE = {}
# Most slots map to themselves (ASCII range), but key overrides:
TS1_TO_UNICODE[0x00] = 0x0060  # grave
TS1_TO_UNICODE[0x01] = 0x00B4  # acute
TS1_TO_UNICODE[0x02] = 0x02C6  # circumflex
TS1_TO_UNICODE[0x03] = 0x02DC  # tilde
TS1_TO_UNICODE[0x04] = 0x00A8  # dieresis
TS1_TO_UNICODE[0x05] = 0x02DD  # double acute
TS1_TO_UNICODE[0x06] = 0x02DA  # ring above
TS1_TO_UNICODE[0x07] = 0x02C7  # caron
TS1_TO_UNICODE[0x08] = 0x02D8  # breve
TS1_TO_UNICODE[0x09] = 0x00AF  # macron
TS1_TO_UNICODE[0x0A] = 0x02D9  # dot above
TS1_TO_UNICODE[0x0B] = 0x00B8  # cedilla
TS1_TO_UNICODE[0x0C] = 0x02DB  # ogonek
TS1_TO_UNICODE[0x0D] = 0x2018  # left single quotation mark (quotesinglbase in TS1 = comma-like)
TS1_TO_UNICODE[0x0E] = 0x2039  # single left-pointing angle quotation
TS1_TO_UNICODE[0x0F] = 0x203A  # single right-pointing angle quotation
TS1_TO_UNICODE[0x10] = 0x201C  # left double quotation
TS1_TO_UNICODE[0x11] = 0x201D  # right double quotation
TS1_TO_UNICODE[0x12] = 0x201E  # double low-9 quotation
TS1_TO_UNICODE[0x13] = 0x00AB  # left-pointing double angle quotation
TS1_TO_UNICODE[0x14] = 0x00BB  # right-pointing double angle quotation
TS1_TO_UNICODE[0x15] = 0x2022  # bullet
TS1_TO_UNICODE[0x16] = 0x2013  # en dash
TS1_TO_UNICODE[0x17] = 0x2014  # em dash
TS1_TO_UNICODE[0x18] = 0x200C  # zero width non-joiner (compound word mark)
TS1_TO_UNICODE[0x19] = 0x0000  # perthousand (skip)
TS1_TO_UNICODE[0x1A] = 0x0131  # dotless i
TS1_TO_UNICODE[0x1B] = 0x0237  # dotless j
TS1_TO_UNICODE[0x1C] = 0xFB00  # ff ligature
TS1_TO_UNICODE[0x1D] = 0xFB01  # fi ligature
TS1_TO_UNICODE[0x1E] = 0xFB02  # fl ligature
TS1_TO_UNICODE[0x1F] = 0xFB03  # ffi ligature
TS1_TO_UNICODE[0x24] = 0x0024  # dollar sign
TS1_TO_UNICODE[0x27] = 0x2019  # right single quotation
TS1_TO_UNICODE[0x2A] = 0x2217  # asterisk operator
TS1_TO_UNICODE[0x2C] = 0x002C  # comma
TS1_TO_UNICODE[0x2D] = 0x2010  # hyphen
TS1_TO_UNICODE[0x2E] = 0x002E  # period
TS1_TO_UNICODE[0x2F] = 0x2044  # fraction slash
TS1_TO_UNICODE[0x30] = 0x0030  # zero (oldstyle in some fonts)
for i in range(0x31, 0x3A):
    TS1_TO_UNICODE[i] = i       # digits 1-9
TS1_TO_UNICODE[0x60] = 0x2018  # left single quotation
TS1_TO_UNICODE[0x7E] = 0x007E  # tilde
TS1_TO_UNICODE[0x80] = 0x02D8  # breve
TS1_TO_UNICODE[0x81] = 0x02C7  # caron
TS1_TO_UNICODE[0x82] = 0x02DD  # double acute
TS1_TO_UNICODE[0x83] = 0x02DB  # ogonek
TS1_TO_UNICODE[0x84] = 0x02DA  # ring above
TS1_TO_UNICODE[0x86] = 0x2020  # dagger
TS1_TO_UNICODE[0x87] = 0x2021  # double dagger
TS1_TO_UNICODE[0x89] = 0x2030  # per mille
TS1_TO_UNICODE[0x8B] = 0xFB04  # ffl ligature
TS1_TO_UNICODE[0x8C] = 0x2026  # horizontal ellipsis
TS1_TO_UNICODE[0x8D] = 0x2120  # service mark
TS1_TO_UNICODE[0x8E] = 0x2211  # N-ary summation (unlikely in text)
TS1_TO_UNICODE[0x8F] = 0x220F  # N-ary product (unlikely in text)
TS1_TO_UNICODE[0x91] = 0x2190  # leftwards arrow
TS1_TO_UNICODE[0x92] = 0x2192  # rightwards arrow
TS1_TO_UNICODE[0x94] = 0x274D  # shadowed white circle
TS1_TO_UNICODE[0x95] = 0x2666  # black diamond suit
TS1_TO_UNICODE[0x96] = 0x2665  # black heart suit
TS1_TO_UNICODE[0x97] = 0x2663  # black club suit
TS1_TO_UNICODE[0x98] = 0x2660  # black spade suit
TS1_TO_UNICODE[0x99] = 0x2669  # quarter note
TS1_TO_UNICODE[0x9A] = 0x266A  # eighth note
TS1_TO_UNICODE[0x9C] = 0x2122  # trademark
TS1_TO_UNICODE[0x9D] = 0x2039  # single left-pointing angle quotation
TS1_TO_UNICODE[0x9E] = 0x203A  # single right-pointing angle quotation
TS1_TO_UNICODE[0xA2] = 0x00A2  # cent sign
TS1_TO_UNICODE[0xA3] = 0x00A3  # pound sign
TS1_TO_UNICODE[0xA4] = 0x00A4  # currency sign
TS1_TO_UNICODE[0xA5] = 0x00A5  # yen sign
TS1_TO_UNICODE[0xA6] = 0x00A6  # broken bar
TS1_TO_UNICODE[0xA7] = 0x00A7  # section sign
TS1_TO_UNICODE[0xA9] = 0x00A9  # copyright
TS1_TO_UNICODE[0xAA] = 0x00AA  # feminine ordinal
TS1_TO_UNICODE[0xAC] = 0x00AC  # not sign
TS1_TO_UNICODE[0xAE] = 0x00AE  # registered
TS1_TO_UNICODE[0xB0] = 0x00B0  # degree sign
TS1_TO_UNICODE[0xB1] = 0x00B1  # plus-minus sign
TS1_TO_UNICODE[0xB2] = 0x00B2  # superscript two
TS1_TO_UNICODE[0xB3] = 0x00B3  # superscript three
TS1_TO_UNICODE[0xB5] = 0x00B5  # micro sign
TS1_TO_UNICODE[0xB6] = 0x00B6  # pilcrow sign
TS1_TO_UNICODE[0xB7] = 0x00B7  # middle dot
TS1_TO_UNICODE[0xB9] = 0x00B9  # superscript one
TS1_TO_UNICODE[0xBA] = 0x00BA  # masculine ordinal
TS1_TO_UNICODE[0xBF] = 0x20AC  # euro sign
TS1_TO_UNICODE[0xD7] = 0x00D7  # multiplication sign
TS1_TO_UNICODE[0xF7] = 0x00F7  # division sign


_tftopl_cache = {}  # font_name -> tftopl output string

def _get_tftopl_output(font_name):
    """Get tftopl output for a font, caching results."""
    if font_name in _tftopl_cache:
        return _tftopl_cache[font_name]
    import subprocess
    try:
        result = subprocess.run(['kpsewhich', f'{font_name}.tfm'],
                                capture_output=True, text=True, timeout=5)
        tfm_path = result.stdout.strip()
        if not tfm_path:
            _tftopl_cache[font_name] = None
            return None
        result = subprocess.run(['tftopl', tfm_path],
                                capture_output=True, text=True, timeout=10)
        _tftopl_cache[font_name] = result.stdout
        return result.stdout
    except Exception:
        _tftopl_cache[font_name] = None
        return None


def _read_tfm_coding_scheme(font_name):
    """Read the CODINGSCHEME from a font's TFM file via kpsewhich + tftopl."""
    output = _get_tftopl_output(font_name)
    if output:
        for line in output.splitlines():
            if 'CODINGSCHEME' in line:
                return line.strip()
    return None


def _load_tfm_widths(font_name):
    """Load character widths from a font's TFM file.

    Returns a dict mapping character code (0-255) to width as a fraction
    of the design size (a fix_word float). Returns None if TFM not found.
    """
    output = _get_tftopl_output(font_name)
    if not output:
        return None
    widths = {}
    current_char = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('(CHARACTER '):
            parts = line.split()
            if len(parts) >= 3:
                char_type = parts[1]
                char_val = parts[2]
                try:
                    if char_type == 'C':
                        current_char = ord(char_val)
                    elif char_type == 'O':
                        current_char = int(char_val, 8)
                    elif char_type == 'D':
                        current_char = int(char_val)
                except (ValueError, TypeError):
                    current_char = None
        elif line.startswith('(CHARWD ') and current_char is not None:
            parts = line.split()
            if len(parts) >= 3:
                try:
                    width = float(parts[2].rstrip(')'))
                    widths[current_char] = width
                except ValueError:
                    pass
        elif line == ')':
            current_char = None
    return widths if widths else None


def font_encoding(font_name):
    """Determine the encoding of a font by its name and TFM metadata.

    Returns 'T1' for EC/Cork-encoded fonts, 'TS1' for text companion fonts,
    'OT1' for standard TeX fonts, 'OT1-TT' for OT1 typewriter fonts.
    """
    # Quick checks by name prefix
    if font_name.startswith('ec-'):
        return 'T1'
    if font_name.startswith('ts1-'):
        return 'TS1'

    # Try reading the TFM coding scheme for non-standard font names
    scheme = _read_tfm_coding_scheme(font_name)
    if scheme:
        upper = scheme.upper()
        if 'TEX TEXT COMPANION' in upper or 'TS1' in upper:
            return 'TS1'
        if 'EXTENDED TEX FONT ENCODING' in upper or 'CORK' in upper or 'T1' in upper:
            return 'T1'
        if 'TEX TYPEWRITER TEXT' in upper:
            return 'OT1-TT'

    # Fallback: heuristics by name
    base = font_name
    if base.startswith('rm-'):
        base = base[3:]
    if 'tt' in base:
        return 'OT1-TT'
    return 'OT1'


def char_to_unicode(code, encoding='T1'):
    """Convert a character code to a Unicode character, using the given encoding."""
    if encoding == 'T1':
        table = T1_TO_UNICODE
    elif encoding == 'TS1':
        table = TS1_TO_UNICODE
    elif encoding == 'OT1-TT':
        table = OT1_TT_TO_UNICODE
    else:  # OT1
        table = OT1_TO_UNICODE
    cp = table.get(code, code)
    return chr(cp)


# ---------------------------------------------------------------------------
# DVI unit conversion
# ---------------------------------------------------------------------------

def sp_to_tome(sp):
    """Convert scaled points (sp) to tome units (1/64 CSS px).

    1 DVI unit = 1 sp = 1/65536 TeX points.
    1 TeX point = 1/72.27 inches.
    1 CSS px = 1/96 inches.
    1 tome unit = 1/64 CSS px.

    tome_units = sp * (1/65536) * (1/72.27) * 96 * 64
               = sp * 96 * 64 / (65536 * 72.27)
               = sp * 6144 / 4736839.68
    """
    return round(sp * 6144 / (65536 * 72.27))


# ---------------------------------------------------------------------------
# DVI parser
# ---------------------------------------------------------------------------

class DVIFont:
    """Represents a font definition from the DVI file."""
    __slots__ = ('number', 'checksum', 'scale', 'design_size', 'name',
                 'tome_slot', 'encoding', 'tfm_widths')

    def __init__(self, number, checksum, scale, design_size, name):
        self.number = number
        self.checksum = checksum
        self.scale = scale          # in sp
        self.design_size = design_size  # in sp
        self.name = name
        self.tome_slot = None       # assigned during conversion
        self.encoding = font_encoding(name)
        self.tfm_widths = _load_tfm_widths(name)  # char_code -> fix_word

    def char_width_sp(self, code):
        """Get the advance width of character `code` in scaled points."""
        if self.tfm_widths and code in self.tfm_widths:
            return round(self.tfm_widths[code] * self.scale)
        return 0


class DVIParser:
    """Parse a DVI file into an internal representation."""

    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.fonts = {}         # DVI font number -> DVIFont
        self.pages = []         # list of pages, each a list of (opcode, args)
        self.preamble_comment = ''
        self.numerator = 0
        self.denominator = 0
        self.magnification = 0

    def read_byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bytes(self, n):
        bs = self.data[self.pos:self.pos + n]
        self.pos += n
        return bs

    def read_unsigned(self, n):
        """Read an n-byte big-endian unsigned integer."""
        bs = self.read_bytes(n)
        val = 0
        for b in bs:
            val = (val << 8) | b
        return val

    def read_signed(self, n):
        """Read an n-byte big-endian signed integer (two's complement)."""
        val = self.read_unsigned(n)
        if val >= (1 << (8 * n - 1)):
            val -= (1 << (8 * n))
        return val

    def parse_fnt_def(self, k_bytes):
        """Parse a fnt_def command. k_bytes is the number of bytes for the font number."""
        k = self.read_unsigned(k_bytes)  # font number
        c = self.read_unsigned(4)        # checksum
        s = self.read_unsigned(4)        # scale (sp)
        d = self.read_unsigned(4)        # design size (sp)
        a = self.read_unsigned(1)        # directory path length
        l = self.read_unsigned(1)        # filename length
        name = self.read_bytes(a + l).decode('ascii')
        font = DVIFont(k, c, s, d, name)
        self.fonts[k] = font
        return font

    def parse(self):
        """Parse the entire DVI file."""
        # --- Preamble ---
        opcode = self.read_byte()
        if opcode != 247:
            raise ValueError(f'Expected preamble (247), got {opcode}')
        dvi_version = self.read_byte()
        if dvi_version != 2:
            print(f'Warning: DVI version {dvi_version} (expected 2)', file=sys.stderr)
        self.numerator = self.read_unsigned(4)
        self.denominator = self.read_unsigned(4)
        self.magnification = self.read_unsigned(4)
        comment_len = self.read_byte()
        self.preamble_comment = self.read_bytes(comment_len).decode('ascii', errors='replace')

        # --- Pages and font definitions ---
        while self.pos < len(self.data):
            opcode = self.data[self.pos]

            if opcode == 248:  # post
                break  # stop at postamble

            if opcode == 139:  # bop (begin page)
                self.pos += 1
                page = self._parse_page()
                self.pages.append(page)
            elif opcode == 138:  # nop
                self.pos += 1
            elif 243 <= opcode <= 246:  # fnt_def1..fnt_def4
                self.pos += 1
                k_bytes = opcode - 242
                self.parse_fnt_def(k_bytes)
            else:
                raise ValueError(
                    f'Unexpected opcode {opcode} (0x{opcode:02x}) at byte {self.pos} '
                    f'outside of page'
                )

    def _parse_page(self):
        """Parse a single page (after bop opcode has been consumed).

        Returns a list of (command_name, args_dict) tuples.
        """
        # Read 10 count registers (4 bytes each) + previous bop pointer (4 bytes)
        counts = [self.read_signed(4) for _ in range(10)]
        prev_bop = self.read_signed(4)

        commands = []
        commands.append(('bop', {'counts': counts, 'prev_bop': prev_bop}))

        while self.pos < len(self.data):
            opcode = self.read_byte()

            # --- setchar_i (0-127) ---
            if opcode <= 127:
                commands.append(('setchar', {'code': opcode}))

            # --- set1..set4 (128-131) ---
            elif 128 <= opcode <= 131:
                n = opcode - 127  # 1..4
                c = self.read_unsigned(n)
                commands.append(('setchar', {'code': c}))

            # --- set_rule (132) ---
            elif opcode == 132:
                a = self.read_signed(4)  # height
                b = self.read_signed(4)  # width
                commands.append(('set_rule', {'height': a, 'width': b}))

            # --- put1..put4 (133-136) ---
            elif 133 <= opcode <= 136:
                n = opcode - 132  # 1..4
                c = self.read_unsigned(n)
                commands.append(('putchar', {'code': c}))

            # --- put_rule (137) ---
            elif opcode == 137:
                a = self.read_signed(4)
                b = self.read_signed(4)
                commands.append(('put_rule', {'height': a, 'width': b}))

            # --- nop (138) ---
            elif opcode == 138:
                pass  # skip

            # --- bop (139) --- should not appear inside a page
            elif opcode == 139:
                raise ValueError(f'Nested bop at byte {self.pos - 1}')

            # --- eop (140) ---
            elif opcode == 140:
                commands.append(('eop', {}))
                break

            # --- push (141) ---
            elif opcode == 141:
                commands.append(('push', {}))

            # --- pop (142) ---
            elif opcode == 142:
                commands.append(('pop', {}))

            # --- right1..right4 (143-146) ---
            elif 143 <= opcode <= 146:
                n = opcode - 142  # 1..4
                b = self.read_signed(n)
                commands.append(('right', {'value': b}))

            # --- w0 (147) ---
            elif opcode == 147:
                commands.append(('w0', {}))

            # --- w1..w4 (148-151) ---
            elif 148 <= opcode <= 151:
                n = opcode - 147  # 1..4
                b = self.read_signed(n)
                commands.append(('w', {'value': b}))

            # --- x0 (152) ---
            elif opcode == 152:
                commands.append(('x0', {}))

            # --- x1..x4 (153-156) ---
            elif 153 <= opcode <= 156:
                n = opcode - 152  # 1..4
                b = self.read_signed(n)
                commands.append(('x', {'value': b}))

            # --- down1..down4 (157-160) ---
            elif 157 <= opcode <= 160:
                n = opcode - 156  # 1..4
                a = self.read_signed(n)
                commands.append(('down', {'value': a}))

            # --- y0 (161) ---
            elif opcode == 161:
                commands.append(('y0', {}))

            # --- y1..y4 (162-165) ---
            elif 162 <= opcode <= 165:
                n = opcode - 161  # 1..4
                a = self.read_signed(n)
                commands.append(('y', {'value': a}))

            # --- z0 (166) ---
            elif opcode == 166:
                commands.append(('z0', {}))

            # --- z1..z4 (167-170) ---
            elif 167 <= opcode <= 170:
                n = opcode - 166  # 1..4
                a = self.read_signed(n)
                commands.append(('z', {'value': a}))

            # --- fnt_num_i (171-234): set current font to i ---
            elif 171 <= opcode <= 234:
                fnt_num = opcode - 171
                commands.append(('fnt', {'number': fnt_num}))

            # --- fnt1..fnt4 (235-238) ---
            elif 235 <= opcode <= 238:
                n = opcode - 234  # 1..4
                k = self.read_unsigned(n)
                commands.append(('fnt', {'number': k}))

            # --- xxx1..xxx4 (239-242): specials ---
            elif 239 <= opcode <= 242:
                n = opcode - 238  # 1..4
                k = self.read_unsigned(n)
                data = self.read_bytes(k)
                try:
                    text = data.decode('ascii')
                except UnicodeDecodeError:
                    text = data.decode('latin-1')
                commands.append(('special', {'text': text}))

            # --- fnt_def1..fnt_def4 (243-246) ---
            elif 243 <= opcode <= 246:
                k_bytes = opcode - 242
                self.parse_fnt_def(k_bytes)
                # Font definitions inside pages are allowed; we just register them.

            # --- post (248) --- shouldn't appear inside a page
            elif opcode == 248:
                # We hit the postamble; back up and let the outer loop handle it.
                self.pos -= 1
                commands.append(('eop', {}))
                break

            else:
                print(f'Warning: Unknown DVI opcode {opcode} (0x{opcode:02x}) '
                      f'at byte {self.pos - 1}, skipping', file=sys.stderr)

        return commands


# ---------------------------------------------------------------------------
# DVI -> Tome converter
# ---------------------------------------------------------------------------

class DVI2Tome:
    """Convert parsed DVI data to tome binary format."""

    def __init__(self, parser):
        self.parser = parser
        self.buf = bytearray()
        self.command_count = 0

        # DVI state variables
        self.h = 0   # horizontal position (sp)
        self.v = 0   # vertical position (sp)
        self.w = 0   # horizontal spacing register
        self.x = 0   # horizontal spacing register
        self.y = 0   # vertical spacing register
        self.z = 0   # vertical spacing register
        self.stack = []

        # Font tracking
        self.current_dvi_font = None
        self.current_tome_font = None
        self.current_encoding = 'OT1'  # default encoding
        self.tome_font_slots = {}   # DVI font number -> tome slot
        self.next_tome_slot = 0

    def _assign_font_slots(self):
        """Assign sequential tome font slots to all DVI fonts."""
        for fnt_num in sorted(self.parser.fonts.keys()):
            font = self.parser.fonts[fnt_num]
            font.tome_slot = self.next_tome_slot
            self.tome_font_slots[fnt_num] = self.next_tome_slot
            self.next_tome_slot += 1

    def _strip_font_name(self, name):
        """Strip common prefixes from DVI font names.

        e.g., 'rm-mlmr10' -> 'mlmr10', 'ec-mlmtt10' -> 'mlmtt10'
        """
        # Strip 'ec-' prefix
        if name.startswith('ec-'):
            name = name[3:]
        # Strip 'rm-' prefix (LuaTeX adds this for regular fonts)
        if name.startswith('rm-'):
            name = name[3:]
        return name

    def _emit_font_defs(self):
        """Emit op_font_def for all fonts."""
        for fnt_num in sorted(self.parser.fonts.keys()):
            font = self.parser.fonts[fnt_num]
            slot = font.tome_slot
            name = self._strip_font_name(font.name)
            size_tu = sp_to_tome(font.scale)
            # Use the checksum as a hash (split into hi/lo 16-bit halves)
            hash_hi = (font.checksum >> 16) & 0xFFFF
            hash_lo = font.checksum & 0xFFFF
            self.buf += op_font_def(slot, hash_hi, hash_lo, size_tu, name)
            self.command_count += 1

    def _is_smallcaps_font(self):
        """Check if the current DVI font is a small-caps virtual font."""
        font = self.parser.fonts.get(self.current_dvi_font)
        if font:
            # Palatino/Palladio small caps: pplrc9d, pplrc9t, etc.
            # MLModern small caps: ec-mlmcsc10, etc.
            name = font.name
            if 'rc' in name or 'csc' in name or 'sc' in name.split('-')[-1]:
                return True
        return False

    def _emit_char(self, code):
        """Emit a character, converting from font encoding to UTF-8.

        For small-caps fonts, lowercase letters are uppercased since the DVI
        references small-cap glyph slots that correspond to lowercase codes
        in the encoding table, but the browser font renders them as lowercase.
        """
        ch = char_to_unicode(code, self.current_encoding)
        if self._is_smallcaps_font() and ch.islower():
            ch = ch.upper()
        utf8 = ch.encode('utf-8')

        # In tome format, bytes 0x01-0x1F are opcodes. If the UTF-8 encoding
        # of a character falls in this range (which can only happen for control
        # characters U+0001-U+001F), we skip them since they conflict with
        # tome opcodes. In practice, both T1 and OT1 encoding maps these slots
        # to accents and special characters that are all above U+001F in Unicode.
        #
        # Also, 0xFF is OP_END in tome, but UTF-8 never produces 0xFF.
        # Similarly, 0x00 (NUL) is a no-op in tome and we skip it.
        for b in utf8:
            if 0x01 <= b <= 0x1F:
                # This byte would be interpreted as a tome opcode.
                # This should not happen with proper encoding->Unicode mapping
                # since all mapped Unicode codepoints produce UTF-8 bytes
                # >= 0x20 or >= 0x80 (multi-byte sequences).
                print(f'Warning: UTF-8 byte 0x{b:02x} in opcode range for '
                      f'char U+{ord(ch):04X}, skipping', file=sys.stderr)
                return
        self.buf += utf8

    def _emit_right(self, sp_val):
        """Emit a horizontal movement in tome units."""
        tu = sp_to_tome(sp_val)
        if tu != 0:
            self.buf += op_right(tu)
            self.command_count += 1

    def _emit_down(self, sp_val):
        """Emit a vertical movement in tome units."""
        tu = sp_to_tome(sp_val)
        if tu != 0:
            self.buf += op_down(tu)
            self.command_count += 1

    def _emit_font(self, dvi_fnt_num):
        """Emit a font change if the font actually changed."""
        tome_slot = self.tome_font_slots.get(dvi_fnt_num)
        if tome_slot is None:
            print(f'Warning: Unknown DVI font number {dvi_fnt_num}', file=sys.stderr)
            return
        if tome_slot != self.current_tome_font:
            self.buf += op_font(tome_slot)
            self.current_tome_font = tome_slot
            self.command_count += 1
        # Always update encoding when font changes
        font = self.parser.fonts.get(dvi_fnt_num)
        if font:
            self.current_encoding = font.encoding

    def _handle_special(self, text):
        """Handle a DVI special command. Only process tome:-prefixed specials."""
        text = text.strip()
        if not text.startswith('tome:'):
            return  # skip non-tome specials (papersize, header, etc.)

        content = text[5:].strip()

        if content.startswith('meta '):
            parts = content[5:].strip().split(None, 1)
            if len(parts) == 2:
                self.buf += op_meta(parts[0], parts[1])
                self.command_count += 1

        elif content.startswith('section '):
            level = int(content[8:].strip())
            self.buf += op_section(level)
            self.command_count += 1

        elif content.startswith('link_def '):
            parts = content[9:].strip().split(None, 1)
            if len(parts) == 2:
                link_id = int(parts[0])
                url = parts[1]
                self.buf += op_link_def(link_id, url)
                self.command_count += 1

        elif content.startswith('link_start '):
            link_id = int(content[11:].strip())
            self.buf += op_link_start(link_id)
            self.buf += op_color(0x2255AAFF)
            self.command_count += 2

        elif content == 'link_end':
            self.buf += op_color(0x333333FF)
            self.buf += op_link_end()
            self.command_count += 2

        elif content.startswith('para'):
            self.buf += op_para()
            self.command_count += 1

        else:
            print(f'Warning: Unknown tome special: {content}', file=sys.stderr)

    def _find_page_bounds(self):
        """Simulate DVI execution to find per-page content bounding boxes.

        Returns a list of (min_h, min_v, max_h, max_v) per page, all in sp.
        """
        page_bounds = []

        for page in self.parser.pages:
            h, v, w, x, y, z = 0, 0, 0, 0, 0, 0
            stack = []
            min_h = float('inf')
            min_v = float('inf')
            max_h = float('-inf')
            max_v = float('-inf')

            current_font = None
            for cmd_name, args in page:
                if cmd_name == 'fnt':
                    current_font = args['number']
                elif cmd_name in ('setchar', 'putchar'):
                    if h < min_h: min_h = h
                    if v < min_v: min_v = v
                    if h > max_h: max_h = h
                    if v > max_v: max_v = v
                    # Track h advance for setchar
                    if cmd_name == 'setchar' and current_font is not None:
                        font = self.parser.fonts.get(current_font)
                        if font:
                            h += font.char_width_sp(args['code'])
                elif cmd_name in ('set_rule', 'put_rule'):
                    if args['height'] > 0 and args['width'] > 0:
                        if h < min_h: min_h = h
                        if v < min_v: min_v = v
                        if v + args['height'] > max_v: max_v = v + args['height']
                elif cmd_name == 'right':
                    h += args['value']
                elif cmd_name == 'w0':
                    h += w
                elif cmd_name == 'w':
                    w = args['value']; h += w
                elif cmd_name == 'x0':
                    h += x
                elif cmd_name == 'x':
                    x = args['value']; h += x
                elif cmd_name == 'down':
                    v += args['value']
                elif cmd_name == 'y0':
                    v += y
                elif cmd_name == 'y':
                    y = args['value']; v += y
                elif cmd_name == 'z0':
                    v += z
                elif cmd_name == 'z':
                    z = args['value']; v += z
                elif cmd_name == 'push':
                    stack.append((h, v, w, x, y, z))
                elif cmd_name == 'pop':
                    if stack:
                        h, v, w, x, y, z = stack.pop()

            if min_h == float('inf'):
                min_h = min_v = max_h = max_v = 0
            page_bounds.append((min_h, min_v, max_h, max_v))

        return page_bounds

    def convert(self):
        """Convert all parsed DVI pages to a tome byte stream."""
        self._assign_font_slots()
        self._emit_font_defs()

        # Find per-page bounding boxes for coordinate normalization
        self.page_bounds = self._find_page_bounds()
        self.page_y_offset_sp = 0  # running Y offset for multi-page stacking

        for page_idx, page in enumerate(self.parser.pages):
            self._convert_page(page, page_idx)
            # After each page, advance the Y offset by the page's content height
            # plus a small gap (equivalent to one line of spacing)
            if page_idx < len(self.parser.pages) - 1:
                _, min_v, _, max_v = self.page_bounds[page_idx]
                page_height = max_v - min_v
                self.page_y_offset_sp += page_height + 655360  # + 10pt gap

        self.buf += op_end()
        self.command_count += 1

        return bytes(self.buf)

    def _convert_page(self, commands, page_idx):
        """Convert a single DVI page to tome commands."""
        # Reset DVI state for each page
        self.h = 0
        self.v = 0
        self.w = 0
        self.x = 0
        self.y = 0
        self.z = 0
        self.stack = []

        # For pages after the first, emit a vertical offset to stack content
        if page_idx > 0 and self.page_y_offset_sp != 0:
            offset_tu = sp_to_tome(self.page_y_offset_sp)
            if offset_tu != 0:
                self.buf += op_down(offset_tu)
                self.command_count += 1

        for cmd_name, args in commands:
            if cmd_name == 'bop':
                # Begin page: nothing special to emit beyond state reset
                pass

            elif cmd_name == 'eop':
                # End page: nothing to emit (multi-page concatenation handled
                # by the fact that subsequent pages continue the stream)
                pass

            elif cmd_name == 'setchar':
                self._emit_char(args['code'])
                # Emit explicit RIGHT for character advance width from TFM.
                # This makes positioning independent of browser measureText.
                font = self.parser.fonts.get(self.current_dvi_font)
                if font:
                    width_sp = font.char_width_sp(args['code'])
                    self.h += width_sp
                    self._emit_right(width_sp)

            elif cmd_name == 'putchar':
                # put character without advancing h
                self._emit_char(args['code'])

            elif cmd_name == 'set_rule':
                height = args['height']
                width = args['width']
                if height > 0 and width > 0:
                    h_tu = sp_to_tome(height)
                    w_tu = sp_to_tome(width)
                    if h_tu > 0 and w_tu > 0:
                        self.buf += op_rule(w_tu, h_tu)
                        self.command_count += 1

            elif cmd_name == 'put_rule':
                height = args['height']
                width = args['width']
                if height > 0 and width > 0:
                    h_tu = sp_to_tome(height)
                    w_tu = sp_to_tome(width)
                    if h_tu > 0 and w_tu > 0:
                        self.buf += op_rule(w_tu, h_tu)
                        self.command_count += 1

            elif cmd_name == 'right':
                self.h += args['value']
                self._emit_right(args['value'])

            elif cmd_name == 'w0':
                self.h += self.w
                self._emit_right(self.w)

            elif cmd_name == 'w':
                self.w = args['value']
                self.h += self.w
                self._emit_right(self.w)

            elif cmd_name == 'x0':
                self.h += self.x
                self._emit_right(self.x)

            elif cmd_name == 'x':
                self.x = args['value']
                self.h += self.x
                self._emit_right(self.x)

            elif cmd_name == 'down':
                self.v += args['value']
                self._emit_down(args['value'])

            elif cmd_name == 'y0':
                self.v += self.y
                self._emit_down(self.y)

            elif cmd_name == 'y':
                self.y = args['value']
                self.v += self.y
                self._emit_down(self.y)

            elif cmd_name == 'z0':
                self.v += self.z
                self._emit_down(self.z)

            elif cmd_name == 'z':
                self.z = args['value']
                self.v += self.z
                self._emit_down(self.z)

            elif cmd_name == 'fnt':
                self.current_dvi_font = args['number']
                self._emit_font(args['number'])

            elif cmd_name == 'push':
                self.stack.append((self.h, self.v, self.w, self.x, self.y, self.z))
                self.buf += op_push()
                self.command_count += 1

            elif cmd_name == 'pop':
                if self.stack:
                    self.h, self.v, self.w, self.x, self.y, self.z = self.stack.pop()
                self.buf += op_pop()
                self.command_count += 1

            elif cmd_name == 'special':
                self._handle_special(args['text'])

            else:
                # Ignore unknown commands
                pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} input.dvi output.tome', file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # Read DVI file
    with open(input_path, 'rb') as f:
        data = f.read()

    # Parse
    parser = DVIParser(data)
    parser.parse()

    # Convert
    converter = DVI2Tome(parser)
    tome_data = converter.convert()

    # Write output
    with open(output_path, 'wb') as f:
        f.write(tome_data)

    # Print summary
    font_count = len(parser.fonts)
    page_count = len(parser.pages)
    dvi_size = len(data)
    tome_size = len(tome_data)

    print(f'DVI file:    {input_path} ({dvi_size} bytes)')
    print(f'Tome file:   {output_path} ({tome_size} bytes)')
    print(f'Pages:       {page_count}')
    print(f'Fonts:       {font_count}')
    for fnum in sorted(parser.fonts.keys()):
        font = parser.fonts[fnum]
        name = converter._strip_font_name(font.name)
        size_tu = sp_to_tome(font.scale)
        print(f'  slot {font.tome_slot}: {name} '
              f'(DVI #{fnum}, size {font.scale} sp = {size_tu} tu, '
              f'encoding {font.encoding})')
    print(f'Commands:    {converter.command_count}')
    print(f'Compression: {tome_size}/{dvi_size} = {tome_size/dvi_size:.1%}')


if __name__ == '__main__':
    main()
