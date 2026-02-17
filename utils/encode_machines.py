#!/usr/bin/env python3
"""Encode Dario Amodei's 'Machines of Loving Grace' essay as .tome files.

Fetches the full essay HTML, parses it with inline formatting (italic,
bold, links), and generates width-specific .tome files per the Approach E
convention from PROPOSAL.md:

  machines.tome       66 chars wide (default)
  machines.45.tome    45 chars wide (mobile portrait)
  machines.90.tome    90 chars wide (wide screen)
"""

import os
import sys
import urllib.request
from bs4 import BeautifulSoup, NavigableString

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from encode_tome import (
    get_metrics, px,
    op_meta, op_font_def, op_font, op_section, op_para, op_moveto,
    op_right, op_lf_down, op_link_def, op_link_start, op_link_end,
    op_color, op_rule, op_end, op_list_item,
    encode_prefixvarint,
)

ESSAY_URL = 'https://www.darioamodei.com/essay/machines-of-loving-grace'
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.machines_cache.html')
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'samples')

# --- Font slots ---
ROMAN    = 0
BOLD     = 1
ITALIC   = 2
BOLD_IT  = 3
MONO     = 4
H1_BOLD  = 5
H2_BOLD  = 6

FONT_NAMES = {
    ROMAN:   'mlmr10',
    BOLD:    'mlmbx10',
    ITALIC:  'mlmri10',
    BOLD_IT: 'mlmbxi10',
    MONO:    'mlmtt10',
    H1_BOLD: 'mlmbx10',
    H2_BOLD: 'mlmbx10',
}

# --- Width profiles ---
# (name_suffix, content_width_px, left_margin_px, body_size_px, h1_size_px, h2_size_px, mono_size_px)
WIDTH_PROFILES = {
    '45': dict(content_w=320, margin=30, body=14, h1=24, h2=18, mono=12),
    '66': dict(content_w=470, margin=50, body=15, h1=28, h2=20, mono=13),
    '90': dict(content_w=640, margin=60, body=15, h1=28, h2=20, mono=13),
}


# ── HTML parsing ──────────────────────────────────────────────────────

def fetch_essay():
    """Fetch essay HTML, with local caching."""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return f.read()
    print(f'Fetching {ESSAY_URL} ...')
    html = urllib.request.urlopen(ESSAY_URL).read().decode('utf-8')
    with open(CACHE_PATH, 'w') as f:
        f.write(html)
    return html


# Content model: a document is a list of blocks.
# Block types:
#   ('h2', text_str)
#   ('para', [span, ...])           where span = (text, font_slot)
#   ('ul', [ [span, ...], ... ])    unordered list
#   ('ol', [ [span, ...], ... ])    ordered list
#   ('rule',)

def _sanitize(text):
    """Remove control characters that would be interpreted as tome opcodes.

    Bytes 0x01-0x1F are opcodes in the tome format, so any such characters
    in text content must be replaced. Newlines/tabs become spaces; others
    are stripped.
    """
    import re
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    return text


def parse_inline(element, links_out):
    """Parse inline content of a <p>, <li>, etc. into spans.

    Returns list of (text, font_slot) tuples.
    links_out: list to append (link_id, url) pairs to as we encounter <a> tags.
    """
    spans = []
    for child in element.children:
        if isinstance(child, NavigableString):
            text = _sanitize(str(child))
            if text:
                spans.append((text, ROMAN))
        elif child.name == 'em':
            text = _sanitize(child.get_text())
            if text:
                spans.append((text, ITALIC))
        elif child.name == 'strong':
            text = _sanitize(child.get_text())
            if text:
                spans.append((text, BOLD))
        elif child.name == 'a':
            href = child.get('href', '')
            text = _sanitize(child.get_text())
            if text and href:
                link_id = len(links_out)
                links_out.append((link_id, href))
                spans.append(('__LINK_START__' + str(link_id), ROMAN))
                # Parse inline children of the link (may contain em/strong)
                for sub in child.children:
                    if isinstance(sub, NavigableString):
                        t = _sanitize(str(sub))
                        if t:
                            spans.append((t, ROMAN))
                    elif sub.name == 'em':
                        spans.append((_sanitize(sub.get_text()), ITALIC))
                    elif sub.name == 'strong':
                        spans.append((_sanitize(sub.get_text()), BOLD))
                    else:
                        spans.append((_sanitize(sub.get_text()), ROMAN))
                spans.append(('__LINK_END__', ROMAN))
            elif text:
                spans.append((text, ROMAN))
        elif child.name == 'sup':
            # Footnote reference — skip (we don't render footnotes inline)
            pass
        elif child.name == 'br':
            spans.append(('\n', ROMAN))
        else:
            # Unknown inline element — just get text
            text = _sanitize(child.get_text())
            if text:
                spans.append((text, ROMAN))
    return spans


def parse_essay(html):
    """Parse essay HTML into structured content blocks."""
    soup = BeautifulSoup(html, 'html.parser')
    article = soup.find('article')
    main_section = article.find_all('section')[0]
    rich_text = main_section.find_all('div', class_='rich-text')[0]

    # Get title, subtitle, date from sibling elements
    title_el = main_section.find('h1')
    subtitle_el = main_section.find('div', class_='post-subtitle')
    date_el = main_section.find('div', class_='post-date')

    title = title_el.get_text().strip() if title_el else 'Machines of Loving Grace'
    subtitle = subtitle_el.get_text().strip() if subtitle_el else ''
    date = date_el.get_text().strip() if date_el else 'October 2024'

    blocks = []
    links = []

    for child in rich_text.children:
        if not hasattr(child, 'name') or not child.name:
            continue

        if child.name == 'h2':
            blocks.append(('h2', child.get_text().strip()))

        elif child.name == 'p':
            spans = parse_inline(child, links)
            if spans:
                blocks.append(('para', spans))

        elif child.name == 'ul':
            items = []
            for li in child.find_all('li', recursive=False):
                item_spans = parse_inline(li, links)
                if item_spans:
                    items.append(item_spans)
            if items:
                blocks.append(('ul', items))

        elif child.name == 'ol':
            items = []
            for li in child.find_all('li', recursive=False):
                item_spans = parse_inline(li, links)
                if item_spans:
                    items.append(item_spans)
            if items:
                blocks.append(('ol', items))

        elif child.name == 'hr':
            blocks.append(('rule',))

    # Get acknowledgments from second rich-text
    rich_texts = main_section.find_all('div', class_='rich-text')
    if len(rich_texts) > 1:
        ack_rt = rich_texts[1]
        for child in ack_rt.children:
            if hasattr(child, 'name') and child.name == 'p':
                spans = parse_inline(child, links)
                if spans:
                    blocks.append(('para', spans))

    return title, subtitle, date, blocks, links


# ── Rich text word wrapper ────────────────────────────────────────────

def _word_width(word, font_slot, font_sizes):
    m = get_metrics(FONT_NAMES[font_slot])
    return m.string_width(word, font_sizes[font_slot])

def _space_width(font_slot, font_sizes):
    m = get_metrics(FONT_NAMES[font_slot])
    return m.char_width(' ', font_sizes[font_slot])


def wrap_rich(spans, max_width, font_sizes):
    """Word-wrap rich text spans, preserving link markers.

    Returns list of lines, where each line is a list of tokens:
      (word, font_slot)           — a word to render
      ('__LINK_START__N', ROMAN)  — link start marker
      ('__LINK_END__', ROMAN)     — link end marker
    """
    # Tokenize: split text spans into words, keeping markers intact
    tokens = []
    for text, font in spans:
        if text.startswith('__LINK_'):
            tokens.append((text, font))
            continue
        # Split on spaces, preserving words
        parts = text.split(' ')
        for i, part in enumerate(parts):
            if part:
                tokens.append((part, font))

    # Greedy line wrap
    lines = []
    current_line = []
    current_width = 0

    for token, font in tokens:
        if token.startswith('__LINK_'):
            current_line.append((token, font))
            continue

        ww = _word_width(token, font, font_sizes)
        sw = _space_width(font, font_sizes) if any(
            not t.startswith('__LINK_') for t, _ in current_line
        ) else 0

        if current_width + sw + ww > max_width and any(
            not t.startswith('__LINK_') for t, _ in current_line
        ):
            lines.append(current_line)
            current_line = [(token, font)]
            current_width = ww
        else:
            current_line.append((token, font))
            current_width += sw + ww

    if current_line:
        lines.append(current_line)

    return lines


# ── Tome encoder ──────────────────────────────────────────────────────

def _encode_justified_line(line, justify, max_width, font_sizes, current_font):
    """Encode a single line of tokens, optionally justified.

    justify: if True, distribute extra space evenly between words.
    Returns (bytes, current_font).
    """
    buf = bytearray()

    # Separate real words from markers
    words = [(t, f) for t, f in line if not t.startswith('__LINK_')]
    markers = {i: (t, f) for i, (t, f) in enumerate(line)}

    if justify and len(words) > 1:
        # Calculate total word width
        total_word_w = sum(_word_width(w, f, font_sizes) for w, f in words)
        remaining = max_width - total_word_w
        num_gaps = len(words) - 1
        base_gap = remaining // num_gaps
        extra = remaining - base_gap * num_gaps  # distribute 1 extra tu to first `extra` gaps
    else:
        base_gap = None

    word_idx = 0
    for token, font in line:
        if token.startswith('__LINK_START__'):
            link_id = int(token[len('__LINK_START__'):])
            buf += op_link_start(link_id)
            buf += op_color(0x2255AAFF)
            continue
        if token == '__LINK_END__':
            buf += op_color(0x333333FF)
            buf += op_link_end()
            continue

        if font != current_font:
            buf += op_font(font)
            current_font = font

        if word_idx > 0:
            if base_gap is not None:
                gap = base_gap + (1 if word_idx - 1 < extra else 0)
                buf += op_right(gap)
            else:
                buf += b' '

        buf += token.encode('utf-8')
        word_idx += 1

    return bytes(buf), current_font


def encode_rich_paragraph(spans, y, layout, font_sizes, in_link=False):
    """Encode a rich-text paragraph with justified text. Returns (bytes, new_y)."""
    buf = bytearray()
    buf += op_para()

    lines = wrap_rich(spans, layout['content_w_tu'], font_sizes)
    current_font = None

    for i, line in enumerate(lines):
        buf += op_moveto(layout['left_margin_tu'], y)
        is_last = (i == len(lines) - 1)
        chunk, current_font = _encode_justified_line(
            line, justify=not is_last,
            max_width=layout['content_w_tu'],
            font_sizes=font_sizes, current_font=current_font,
        )
        buf += chunk
        y += layout['line_height_tu']

    return bytes(buf), y


def encode_list(items, y, layout, font_sizes, ordered=False):
    """Encode a list (ul or ol) with justified text. Returns (bytes, new_y)."""
    buf = bytearray()
    indent = px(20)
    list_width = layout['content_w_tu'] - indent

    for idx, item_spans in enumerate(items):
        buf += op_list_item()

        # Add bullet or number prefix
        if ordered:
            prefix = f'{idx + 1}. '
        else:
            prefix = '\u2022 '
        prefixed_spans = [(prefix, ROMAN)] + item_spans

        lines = wrap_rich(prefixed_spans, list_width, font_sizes)
        current_font = None

        for line_idx, line in enumerate(lines):
            margin = layout['left_margin_tu'] + indent
            buf += op_moveto(margin, y)
            is_last = (line_idx == len(lines) - 1)
            chunk, current_font = _encode_justified_line(
                line, justify=not is_last,
                max_width=list_width,
                font_sizes=font_sizes, current_font=current_font,
            )
            buf += chunk
            y += layout['line_height_tu']

        y += layout['list_item_skip_tu']

    return bytes(buf), y


def encode_heading(text, level, y, layout, font_sizes):
    """Encode a section heading. Returns (bytes, new_y)."""
    buf = bytearray()
    buf += op_section(level)
    font_slot = H1_BOLD if level == 1 else H2_BOLD
    buf += op_font(font_slot)

    # Word-wrap long headings
    m = get_metrics(FONT_NAMES[font_slot])
    words = text.split(' ')
    lines = []
    current_line = []
    current_width = 0
    for word in words:
        ww = m.string_width(word, font_sizes[font_slot])
        sw = m.char_width(' ', font_sizes[font_slot]) if current_line else 0
        if current_width + sw + ww > layout['content_w_tu'] and current_line:
            lines.append(' '.join(current_line))
            current_line = [word]
            current_width = ww
        else:
            current_line.append(word)
            current_width += sw + ww
    if current_line:
        lines.append(' '.join(current_line))

    line_h = layout['h1_line_tu'] if level == 1 else layout['h2_line_tu']
    for line in lines:
        buf += op_moveto(layout['left_margin_tu'], y)
        buf += line.encode('utf-8')
        y += line_h

    return bytes(buf), y


def encode_rule(y, layout):
    """Encode a horizontal rule. Returns (bytes, new_y)."""
    buf = bytearray()
    buf += op_moveto(layout['left_margin_tu'], y)
    buf += op_rule(layout['content_w_tu'], px(0.5))
    y += px(12)
    return bytes(buf), y


def generate_tome(title, subtitle, date, blocks, links, profile_name):
    """Generate a .tome file for the given width profile."""
    prof = WIDTH_PROFILES[profile_name]

    content_w = px(prof['content_w'])
    margin = px(prof['margin'])
    body_size = px(prof['body'])
    h1_size = px(prof['h1'])
    h2_size = px(prof['h2'])
    mono_size = px(prof['mono'])

    font_sizes = {
        ROMAN:   body_size,
        BOLD:    body_size,
        ITALIC:  body_size,
        BOLD_IT: body_size,
        MONO:    mono_size,
        H1_BOLD: h1_size,
        H2_BOLD: h2_size,
    }

    line_height = px(prof['body'] * 1.53)
    h1_line = px(prof['h1'] * 1.35)
    h2_line = px(prof['h2'] * 1.4)
    para_skip = px(prof['body'] * 0.67)
    section_skip = px(prof['body'] * 2.0)
    list_item_skip = px(prof['body'] * 0.33)

    layout = dict(
        content_w_tu=content_w,
        left_margin_tu=margin,
        line_height_tu=line_height,
        h1_line_tu=h1_line,
        h2_line_tu=h2_line,
        para_skip_tu=para_skip,
        section_skip_tu=section_skip,
        list_item_skip_tu=list_item_skip,
    )

    total_width = content_w + 2 * margin

    buf = bytearray()

    # --- Preamble ---
    buf += op_meta('title', title)
    buf += op_meta('author', 'Dario Amodei')
    buf += op_meta('date', date)
    buf += op_meta('lang', 'en')
    buf += op_meta('width', str(total_width))

    # Font definitions
    buf += op_font_def(ROMAN,   0, 1, body_size, 'mlmr10')
    buf += op_font_def(BOLD,    0, 2, body_size, 'mlmbx10')
    buf += op_font_def(ITALIC,  0, 3, body_size, 'mlmri10')
    buf += op_font_def(BOLD_IT, 0, 4, body_size, 'mlmbxi10')
    buf += op_font_def(MONO,    0, 5, mono_size, 'mlmtt10')
    buf += op_font_def(H1_BOLD, 0, 6, h1_size,   'mlmbx10')
    buf += op_font_def(H2_BOLD, 0, 7, h2_size,   'mlmbx10')

    # Link definitions
    for link_id, url in links:
        buf += op_link_def(link_id, url)

    y = margin + h1_size

    # === Title ===
    chunk, y = encode_heading(title, 1, y, layout, font_sizes)
    buf += chunk

    # Subtitle
    if subtitle:
        buf += op_font(H2_BOLD)
        # Word-wrap subtitle
        m = get_metrics(FONT_NAMES[H2_BOLD])
        words = subtitle.split(' ')
        sub_lines = []
        cur = []
        cw = 0
        for w in words:
            ww = m.string_width(w, h2_size)
            sw = m.char_width(' ', h2_size) if cur else 0
            if cw + sw + ww > content_w and cur:
                sub_lines.append(' '.join(cur))
                cur = [w]
                cw = ww
            else:
                cur.append(w)
                cw += sw + ww
        if cur:
            sub_lines.append(' '.join(cur))
        for line in sub_lines:
            buf += op_moveto(margin, y)
            buf += line.encode('utf-8')
            y += h2_line

    # Author + date
    y += para_skip
    buf += op_font(ITALIC)
    author_line = f'Dario Amodei \u2014 {date}'
    buf += op_moveto(margin, y)
    buf += author_line.encode('utf-8')
    y += line_height + section_skip

    # --- Rule ---
    chunk, y = encode_rule(y, layout)
    buf += chunk
    y += para_skip

    # === Content blocks ===
    for block in blocks:
        btype = block[0]

        if btype == 'h2':
            y += section_skip
            chunk, y = encode_heading(block[1], 2, y, layout, font_sizes)
            buf += chunk
            y += para_skip

        elif btype == 'para':
            chunk, y = encode_rich_paragraph(block[1], y, layout, font_sizes)
            buf += chunk
            y += para_skip

        elif btype in ('ul', 'ol'):
            chunk, y = encode_list(block[1], y, layout, font_sizes,
                                   ordered=(btype == 'ol'))
            buf += chunk

        elif btype == 'rule':
            y += para_skip
            chunk, y = encode_rule(y, layout)
            buf += chunk
            y += para_skip

    buf += op_end()
    return bytes(buf)


def main():
    html = fetch_essay()
    title, subtitle, date, blocks, links = parse_essay(html)

    print(f'Parsed: {len(blocks)} blocks, {len(links)} links')

    os.makedirs(OUT_DIR, exist_ok=True)

    for profile_name in ('66', '45', '90'):
        data = generate_tome(title, subtitle, date, blocks, links, profile_name)
        if profile_name == '66':
            filename = 'machines.tome'
        else:
            filename = f'machines.{profile_name}.tome'
        path = os.path.join(OUT_DIR, filename)
        with open(path, 'wb') as f:
            f.write(data)
        print(f'  {filename}: {len(data):,} bytes')


if __name__ == '__main__':
    main()
