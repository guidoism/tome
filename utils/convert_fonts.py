#!/usr/bin/env python3
"""Convert MLModern Type1 (.pfb) fonts to WOFF2 for web use."""

import os
import subprocess
from fontTools.t1Lib import T1Font
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.fontBuilder import FontBuilder
from fontTools.agl import AGL2UV

SRC_DIR = '/Library/TeX/Root/texmf-dist/fonts/type1/public/mlmodern'
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'viewer', 'fonts')
WOFF2_COMPRESS = '/Users/guido/homebrew/bin/woff2_compress'

FONTS = [
    ('mlmr10',   'MLModern',      'Regular'),
    ('mlmri10',  'MLModern',      'Italic'),
    ('mlmbx10',  'MLModern',      'Bold'),
    ('mlmbxi10', 'MLModern',      'Bold Italic'),
    ('mlmtt10',  'MLModern Mono', 'Regular'),
]


def convert_font(name, family, style):
    pfb_path = os.path.join(SRC_DIR, f'{name}.pfb')
    otf_path = os.path.join(OUT_DIR, f'{name}.otf')
    woff2_path = os.path.join(OUT_DIR, f'{name}.woff2')

    print(f'Converting {name} ({family} {style})...')

    t1 = T1Font(pfb_path)
    t1.parse()
    gs = t1.getGlyphSet()
    font_dict = t1.font

    # Collect glyph names
    glyph_order = ['.notdef']
    for gname in sorted(gs.keys()):
        if gname != '.notdef':
            glyph_order.append(gname)

    # Build cmap (glyph name → Unicode via AGL)
    cmap = {}
    for gname in glyph_order:
        if gname in AGL2UV:
            cmap[AGL2UV[gname]] = gname

    # Convert charstrings and collect metrics
    charstrings = {}
    metrics = {}
    for gname in glyph_order:
        rec = RecordingPen()
        gs[gname].draw(rec)
        width = gs[gname].width

        t2pen = T2CharStringPen(width, glyphSet=None)
        rec.replay(t2pen)
        charstrings[gname] = t2pen.getCharString()
        metrics[gname] = (width, 0)

    # Font metadata
    bbox = font_dict.get('FontBBox', [-200, -300, 1200, 1000])
    font_info = font_dict.get('FontInfo', {})
    ascent = bbox[3]
    descent = bbox[1]
    ps_name = font_dict.get('FontName', f'{family}-{style}'.replace(' ', ''))

    # Build OTF
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)
    fb.setupNameTable({
        'familyName': family,
        'styleName': style,
    })
    fb.setupOS2(
        sTypoAscender=ascent,
        sTypoDescender=descent,
        sxHeight=int(ascent * 0.45),
        sCapHeight=int(ascent * 0.68),
        fsSelection=(
            (1 if 'Italic' in style else 0) |    # bit 0: italic
            (0x20 if 'Bold' in style else 0x40)   # bit 5: bold, bit 6: regular
        ),
    )
    fb.setupPost(isFixedPitch=('Mono' in family or 'tt' in name))
    fb.setupCFF(
        psName=ps_name,
        fontInfo={
            'FullName': font_info.get('FullName', f'{family} {style}'),
            'FamilyName': font_info.get('FamilyName', family),
        },
        charStringsDict=charstrings,
        privateDict={},
    )

    fb.font.save(otf_path)
    print(f'  OTF: {os.path.getsize(otf_path):,} bytes')

    # Convert to WOFF2
    subprocess.run([WOFF2_COMPRESS, otf_path], check=True,
                   capture_output=True, text=True)
    print(f'  WOFF2: {os.path.getsize(woff2_path):,} bytes')

    # Remove intermediate OTF
    os.remove(otf_path)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, family, style in FONTS:
        convert_font(name, family, style)
    print('\nDone! WOFF2 files in', OUT_DIR)


if __name__ == '__main__':
    main()
