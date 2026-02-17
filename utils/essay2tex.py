#!/usr/bin/env python3
"""Convert the 'Machines of Loving Grace' essay HTML into a LaTeX document.

Generates LaTeX suitable for compilation with `latex` to produce DVI output.
Embeds \\special{tome:...} commands for the DVI-to-tome converter.

Usage:
    python3 essay2tex.py [--width CSS_PX] [--output FILE]

Default width: 470 CSS pixels.  Default output: stdout.
"""

import argparse
import os
import re
import sys
import urllib.request
from bs4 import BeautifulSoup, NavigableString

ESSAY_URL = 'https://www.darioamodei.com/essay/machines-of-loving-grace'
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          '.machines_cache.html')

# ── Helpers ──────────────────────────────────────────────────────────

LATEX_SPECIAL = str.maketrans({
    '&': r'\&',
    '%': r'\%',
    '#': r'\#',
    '$': r'\$',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
})


def _sanitize(text):
    """Collapse whitespace and remove control characters."""
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
    text = re.sub(r'  +', ' ', text)
    return text


def _latex_escape(text):
    """Escape LaTeX special characters and convert typographic entities."""
    # Unicode replacements BEFORE escaping (so TeX ligatures survive)
    text = text.replace('\u2014', '---')     # em dash
    text = text.replace('\u2013', '--')      # en dash
    text = text.replace('\u201c', '``')      # left double quote
    text = text.replace('\u201d', "''")      # right double quote
    text = text.replace('\u2018', '`')       # left single quote
    text = text.replace('\u2019', "'")       # right single quote
    text = text.translate(LATEX_SPECIAL)
    return text


# ── HTML Fetching ────────────────────────────────────────────────────

def fetch_essay():
    """Read cached HTML or fetch from the web."""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            return f.read()
    print(f'Fetching {ESSAY_URL} ...', file=sys.stderr)
    html = urllib.request.urlopen(ESSAY_URL).read().decode('utf-8')
    with open(CACHE_PATH, 'w') as f:
        f.write(html)
    return html


# ── HTML → LaTeX Conversion ─────────────────────────────────────────

class EssayConverter:
    """Stateful converter that collects links and emits LaTeX."""

    def __init__(self):
        self.links = []          # [(url, id), ...]
        self.link_url_to_id = {} # url → id (dedup)

    def _get_link_id(self, url):
        """Return a numeric ID for *url*, reusing if already seen."""
        if url in self.link_url_to_id:
            return self.link_url_to_id[url]
        lid = len(self.links)
        self.links.append(url)
        self.link_url_to_id[url] = lid
        return lid

    # ── inline conversion ────────────────────────────────────────

    def convert_inline(self, element):
        """Convert inline HTML content to a LaTeX string.

        Handles NavigableString, <em>, <strong>, <a>, <sup>, <br>, and
        falls through to plain text for anything else.
        """
        parts = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = _sanitize(str(child))
                if text:
                    parts.append(_latex_escape(text))

            elif child.name == 'sup':
                # Footnote markers — skip entirely
                continue

            elif child.name == 'br':
                parts.append(r'\\')

            elif child.name == 'em':
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(r'\textit{' + inner + '}')

            elif child.name == 'strong':
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(r'\textbf{' + inner + '}')

            elif child.name == 'a':
                # Render link text without link markup
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(inner)

            else:
                # Unknown inline element — just convert its text
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(inner)

        return ''.join(parts)

    def _convert_inline_recursive(self, element):
        """Recursively convert children, handling nested em/strong/a/sup."""
        parts = []
        for child in element.children:
            if isinstance(child, NavigableString):
                text = _sanitize(str(child))
                if text:
                    parts.append(_latex_escape(text))
            elif child.name == 'sup':
                continue
            elif child.name == 'br':
                parts.append(r'\\')
            elif child.name == 'em':
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(r'\textit{' + inner + '}')
            elif child.name == 'strong':
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(r'\textbf{' + inner + '}')
            elif child.name == 'a':
                # Render link text without link markup
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(inner)
            else:
                inner = self._convert_inline_recursive(child)
                if inner:
                    parts.append(inner)
        return ''.join(parts)

    # ── block conversion ─────────────────────────────────────────

    def convert_block(self, element):
        """Convert a block-level element to LaTeX lines (list of str)."""
        lines = []
        tag = element.name

        if tag == 'h2':
            heading = _latex_escape(_sanitize(element.get_text()))
            lines.append(r'\special{tome:section 2}')
            lines.append(r'{\large\ctSmallcaps{' + heading.lower() + r'}}\par\medskip')

        elif tag == 'p':
            text = self.convert_inline(element)
            if text.strip():
                lines.append(text + r'\par\medskip')

        elif tag == 'ul':
            lines.append(r'\begin{itemize}[nosep,leftmargin=2em]')
            for li in element.find_all('li', recursive=False):
                item_text = self.convert_inline(li)
                if item_text.strip():
                    lines.append(r'\item ' + item_text)
            lines.append(r'\end{itemize}')

        elif tag == 'ol':
            lines.append(r'\begin{enumerate}[nosep,leftmargin=2em]')
            for li in element.find_all('li', recursive=False):
                item_text = self.convert_inline(li)
                if item_text.strip():
                    lines.append(r'\item ' + item_text)
            lines.append(r'\end{enumerate}')

        elif tag == 'hr':
            lines.append(r'\medskip\hrule\medskip')

        return lines

    # ── full document ────────────────────────────────────────────

    def convert(self, html, css_px_width):
        """Convert the full essay HTML to a complete LaTeX document string."""
        tex_pt_width = css_px_width * 72.27 / 96.0
        tome_width = css_px_width * 64  # tome units

        soup = BeautifulSoup(html, 'html.parser')
        article = soup.find('article')
        main_section = article.find_all('section')[0]

        title_el = main_section.find('h1')
        subtitle_el = main_section.find('div', class_='post-subtitle')
        date_el = main_section.find('div', class_='post-date')

        title = title_el.get_text().strip() if title_el else 'Machines of Loving Grace'
        subtitle = subtitle_el.get_text().strip() if subtitle_el else ''
        date = date_el.get_text().strip() if date_el else 'October 2024'

        rich_texts = main_section.find_all('div', class_='rich-text')
        rich_text_main = rich_texts[0]

        # --- First pass: convert all blocks (this populates self.links) ---
        body_lines = []

        for child in rich_text_main.children:
            if not hasattr(child, 'name') or not child.name:
                continue
            block_lines = self.convert_block(child)
            body_lines.extend(block_lines)

        # Acknowledgments from second rich-text div
        if len(rich_texts) > 1:
            body_lines.append(r'\medskip\hrule\medskip')
            ack_rt = rich_texts[1]
            for child in ack_rt.children:
                if hasattr(child, 'name') and child.name:
                    block_lines = self.convert_block(child)
                    body_lines.extend(block_lines)

        # --- Build preamble ---
        preamble = []
        preamble.append(r'\documentclass[10pt]{scrartcl}')
        preamble.append(r'\usepackage[T1]{fontenc}')
        preamble.append(r'\usepackage{tgpagella}')
        preamble.append(r'\usepackage[nochapters]{classicthesis}')
        preamble.append(r'\usepackage{soul}')
        preamble.append(r'\usepackage{enumitem}')
        # Use maximum page height to avoid page breaks. The viewer normalizes
        # coordinates, so large DVI coordinates are fine.
        preamble.append(r'\usepackage[textwidth=%.4fpt,textheight=16383pt]{geometry}'
                        % tex_pt_width)
        preamble.append(r'\pagestyle{empty}')
        preamble.append(r'\setlength{\parindent}{0pt}')
        # classicthesis disables spacedallcaps/spacedlowsmallcaps in DVI mode.
        # Re-implement with soul for DVI letterspacing.
        preamble.append(r'\sodef\ctAllcaps{}{0.15em}{0.65em}{0.6em}')
        preamble.append(r'\sodef\ctSmallcaps{\scshape}{0.075em}{0.5em}{0.6em}')

        doc = []
        doc.extend(preamble)
        doc.append(r'\begin{document}')
        doc.append('')

        # Tome metadata specials
        doc.append(r'\special{tome:meta title Machines of Loving Grace}')
        doc.append(r'\special{tome:meta author Dario Amodei}')
        doc.append(r'\special{tome:meta date October 2024}')
        doc.append(r'\special{tome:meta lang en}')
        doc.append(r'\special{tome:meta width %d}' % tome_width)
        doc.append('')

        # Title block — uppercase in Python, letterspace with soul
        doc.append(r'{\Large\ctAllcaps{' + _latex_escape(title).upper() + r'}}\par\bigskip')
        if subtitle:
            doc.append(r'{\large\itshape ' + _latex_escape(subtitle) + r'}\par')
        doc.append(r'{\small Dario Amodei --- ' + _latex_escape(date) + r'}\par\bigskip')
        doc.append('')

        # Body
        doc.extend(body_lines)

        doc.append('')
        doc.append(r'\end{document}')

        return '\n'.join(doc) + '\n'


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert Machines of Loving Grace essay to LaTeX/DVI-ready .tex')
    parser.add_argument('--width', type=float, default=470,
                        help='Text width in CSS pixels (default: 470)')
    parser.add_argument('--output', type=str, default=None,
                        help='Output file (default: stdout)')
    args = parser.parse_args()

    html = fetch_essay()
    converter = EssayConverter()
    tex = converter.convert(html, args.width)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(tex)
        print(f'Wrote {args.output} ({len(tex):,} bytes, '
              f'{len(converter.links)} links)',
              file=sys.stderr)
    else:
        sys.stdout.write(tex)


if __name__ == '__main__':
    main()
