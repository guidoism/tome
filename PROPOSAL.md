# Tome Format Proposal

## 1. Refined Goals

Restating the goals from the README with more precision, ordered by priority:

1. **Latency**: Time from first HTTP response byte to completed first screenful must be lower than an equivalent HTML page. The format must support streaming (render-as-you-receive), not require the full file before painting begins.
2. **Typography**: Output quality must match TeX. Ligatures, kerning, proper line-breaking, hyphenation — all pre-computed by the publisher.
3. **Compactness**: The total transfer size (document + all required assets) must be smaller than a PNG screenshot of the rendered page.
4. **Simplicity**: A plain-text reader must be implementable in an afternoon. A full-featured reader in a weekend.
5. **Web-native**: Served over HTTP/HTTPS. Displayable in existing browsers (initially via a small JS renderer, eventually natively). Uses standard web infrastructure (CDNs, caching, content negotiation).
6. **Accessibility**: The textual content must always be extractable. Screen readers must be able to read the document.
7. **Archival**: A single file must be self-contained enough to be useful decades later.

**Non-goals**: Interactivity. Forms. Scripting. Application-like behavior. Complex multi-column layouts. Real-time collaborative editing.

## 2. What Exactly Is Slow About HTML

The median web page in 2025 is 2.86 MB (HTTP Archive). For a text-centric blog post, the breakdown is roughly:

| Component | Typical Size | Role |
|-----------|-------------|------|
| HTML | 22 KB | Content + structure |
| CSS | 82 KB | Styling |
| JavaScript | 697 KB | Behavior (mostly unwanted) |
| Fonts | 139 KB | Typography |
| Images | 1,059 KB | Illustration |
| **Total** | **~2,000 KB** | |

For a pure text article with no images, the content itself is perhaps 12 KB. The remaining 1,988 KB is overhead. Of that:

- **JavaScript** is the worst offender. It blocks rendering, requires parsing and execution, and most of it is analytics/tracking/ads — not serving the reader.
- **CSS** requires constructing the CSSOM, computing the cascade for every element, then running layout. This is O(elements × rules), and even a modest page has thousands of DOM nodes against hundreds of CSS rules.
- **Fonts** must be fetched before text can be painted (unless `font-display: swap` is used, which causes layout shift). Custom fonts are typically 30-50 KB each.
- **Layout** itself — line-breaking, paragraph shaping, margin collapsing, float clearing — is computed on every client, every time. Identical work repeated billions of times per day across all readers.

Tome eliminates **all** of these: no JavaScript, no CSS cascade, no layout computation, no font fetching (standard fonts assumed). The work is done once by the publisher.

## 3. The Central Design Tension

The DVI philosophy — publisher pre-computes all positions, client just draws — is perfect for print. For screens, there's a problem: screens vary in width.

There are five ways to handle this.

### Approach A: Fixed Width (PDF-like)

Render at one width. Clients scale or scroll.

- **Pro**: Simplest format. Simplest reader. Publisher has total control.
- **Con**: Mobile UX is poor (tiny text or horizontal scroll). This is the PDF experience.
- **Verdict**: Acceptable as a starting point but not a long-term answer.

### Approach B: Multiple Pre-Rendered Widths

Store 2-3 rendering tracks in one file. Client picks the closest.

- **Pro**: Publisher retains typographic control. No client-side layout. Covers the practical range of reading widths (Bringhurst: 45-75 chars).
- **Con**: File is 2-3x larger. Complexity in the format. Three renderings is still not truly responsive.
- **Verdict**: Good tradeoff for documents that care about typography.

### Approach C: Semantic Content + Layout Overlay

Store the document as structured text (headings, paragraphs, links). Optionally attach a binary layout overlay with exact positions for one or more widths.

- **Pro**: Best accessibility story. Falls back to plain text. Separates concerns.
- **Con**: Two representations to keep in sync. More complex toolchain.
- **Verdict**: Elegant but may be over-engineered for v1.

### Approach D: Constrained Reflow (HINT-like)

Store enough of TeX's internal state (glue, penalties, box/glue/penalty lists) that the client can do paragraph-level line-breaking but not full layout.

- **Pro**: Truly responsive. Publisher controls paragraph break quality.
- **Con**: Client needs to implement TeX's line-breaking algorithm. Not simple. Tightly coupled to TeX's internals.
- **Verdict**: Conflicts with goal 4 (simplicity).

### Approach E: Two-Track (Recommended)

A single interleaved byte stream containing both **content** and **rendering commands**. The content is always UTF-8 text. The rendering commands are control bytes (0x01-0x1F) with parameters. A simple reader ignores commands; a capable reader follows them.

Additionally: the server can use HTTP `Variant` headers or filename conventions (`.tome`, `.45.tome`, `.66.tome`) to serve width-specific renderings. The format itself is single-width. Width adaptation is an HTTP concern, not a format concern.

- **Pro**: Simplest format. Streaming-friendly (interleaved). Accessible (text is inline). Archival (content is human-visible in a hex dump). Width adaptation uses existing HTTP infrastructure.
- **Con**: Truly narrow or truly wide viewports get a scaled or scrolled experience (like Approach A) if no width-specific variant exists. Publishers who care can generate 2-3 variants.

This is the approach I recommend and detail below.

## 4. Format Design

### 4.1 The Byte Space

The entire byte range 0x00-0xFF is partitioned:

| Range | Role |
|-------|------|
| 0x00 | **NUL**: Padding / no-op (same as DVI's nop) |
| 0x01-0x1F | **Opcodes**: Tome commands, each followed by zero or more parameter bytes |
| 0x20-0x7E | **Printable ASCII**: Rendered as the current glyph for that codepoint |
| 0x7F | **DEL**: Reserved (no-op) |
| 0x80-0xBF | **UTF-8 continuation bytes**: Part of a multi-byte character |
| 0xC0-0xF7 | **UTF-8 lead bytes**: Start of a 2-4 byte UTF-8 character |
| 0xF8-0xFE | **Reserved** for future use |
| 0xFF | **End of stream** |

UTF-8 multi-byte sequences (0xC0+ lead byte followed by 0x80-0xBF continuation bytes) are treated as single characters and rendered as the current glyph for that codepoint, exactly like printable ASCII.

**Key property**: All content bytes are >= 0x20 (or part of a UTF-8 multi-byte sequence starting >= 0xC0). All commands are < 0x20. This partition is unambiguous.

**Plain-text extraction**: A decoder that strips bytes 0x00-0x1F *and their parameters* gets the text. A cruder decoder that strips only single bytes < 0x20 gets mostly-correct text with some garbage from opcode parameters — still readable for casual inspection.

### 4.2 Opcodes

I propose 24 opcodes using the 30 available slots (0x01-0x1E, keeping 0x0A/LF and 0x09/TAB for their traditional meaning in plain-text mode). Each opcode is followed by a deterministic number of parameter bytes.

**Notation**: `v` = unsigned varint. `sv` = signed varint. `s` = varint-length-prefixed UTF-8 string. All varints use PrefixVarint encoding (length determinable from first byte, no continuation-bit chaining).

#### Cursor Movement

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x01 | RIGHT | sv | Move cursor right by sv units (negative = left) |
| 0x02 | DOWN | sv | Move cursor down by sv units (negative = up) |
| 0x03 | MOVETO | sv, sv | Move cursor to absolute (x, y) |
| 0x04 | CR | — | Move cursor to left margin of current line (carriage return) |
| 0x05 | LF_DOWN | v | Carriage return + move down by v units (line feed) |

#### Font Control

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x06 | FONT_DEF | v(slot), v(hash_hi), v(hash_lo), v(size), s(name) | Define a font: assign slot, identify by hash, set size in units, give human name |
| 0x07 | FONT | v(slot) | Set current font to slot |

#### Structure (for accessibility / text extraction)

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x08 | SECTION | v(level) | Marks start of a structural section (1=h1, 2=h2, etc.) |
| 0x0B | PARA | — | Marks a paragraph boundary |
| 0x0E | LIST_ITEM | v(depth) | Marks a list item at given nesting depth |

#### Hyperlinks

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x0F | LINK_DEF | v(id), s(url) | Define a link target |
| 0x10 | LINK_START | v(id) | Begin linked text (references a LINK_DEF) |
| 0x11 | LINK_END | — | End linked text |

#### Typographic Refinements

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x12 | KERN | sv | Fine-tune cursor position by sv units (inline kerning) |
| 0x13 | LIGATURE | v(glyph), v(n) | The next n codepoints are consumed and drawn as the single glyph `glyph` in the current font |
| 0x14 | RULE | v(w), v(h) | Draw a filled rectangle of w x h units at current position |

#### Color and Appearance

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x15 | COLOR | v(rgba) | Set text color as 32-bit RGBA |
| 0x16 | BG_COLOR | v(rgba) | Set background/page color as 32-bit RGBA |

#### Images

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x17 | IMAGE_DEF | v(id), v(w), v(h), s(url_or_data_uri) | Define an image with dimensions |
| 0x18 | IMAGE | v(id) | Draw image at current cursor position |

#### Document Metadata

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x19 | META | s(key), s(value) | Key-value metadata (title, author, lang, date, etc.) |
| 0x1A | ANCHOR | s(name) | Define a named anchor (for internal links) |

#### State Management

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x1B | PUSH | — | Push cursor state onto stack |
| 0x1C | POP | — | Pop cursor state from stack |

#### Special

| Byte | Name | Parameters | Description |
|------|------|------------|-------------|
| 0x09 | TAB | — | In plain-text mode: tab stop. In typeset mode: no-op |
| 0x0A | NEWLINE | — | In plain-text mode: newline. In typeset mode: no-op (use DOWN/CR) |
| 0x0D | — | — | Ignored (for Windows line endings) |
| 0x1E | EXTENSION | v(type), v(len), bytes[len] | Future extensions: type-length-value |

**Reserved**: 0x0C, 0x1D, 0x1F.

### 4.3 Varint Encoding: PrefixVarint

PrefixVarint is preferred over LEB128 for three reasons:

1. **Length from first byte**: Decoding requires no byte-by-byte continuation-bit checking. The first byte tells you how many bytes follow. This is better for branch prediction on modern CPUs.
2. **Same compression ratio as LEB128** for values < 2^56, and more compact for large values (max 9 bytes vs. LEB128's 10 for 64-bit values).
3. **Lexicographic ordering matches numeric ordering**: Useful if we ever need sorted indices.

Encoding (unsigned):

| First byte pattern | Total bytes | Value range |
|---------------------|-------------|-------------|
| 0xxxxxxx | 1 | 0 – 127 |
| 10xxxxxx + 1 byte | 2 | 128 – 16,511 |
| 110xxxxx + 2 bytes | 3 | 16,512 – 2,113,663 |
| 1110xxxx + 3 bytes | 4 | up to ~268M |
| 11110xxx + 4 bytes | 5 | up to ~34B |
| ... | ... | ... |
| 11111111 + 8 bytes | 9 | full 64-bit |

Signed varints use zigzag encoding: `(n << 1) ^ (n >> 63)`, so small negative values are also compact.

**Note**: Single-byte values 0-127 are the common case (font slots, small offsets, link IDs) and encode as a single byte with zero overhead.

### 4.4 Units

**Proposal**: The base unit is **1/64th of a CSS pixel** (a "tome unit", abbreviated "tu").

Rationale:
- CSS pixels are device-independent and familiar to web developers.
- 1/64th gives sub-pixel precision for kerning and positioning (matching TeX's 1/65536 pt resolution in practice).
- At 96 CSS dpi, a 66-character line at 10pt is about 450 CSS px = 28,800 tu. This fits in a 2-byte varint.
- At 2x device pixel ratio (common mobile), 1 tu = 1/32 physical pixel. At 3x, 1 tu = ~1/21 physical pixel. More than enough precision.
- A scale command (like DVI's) is unnecessary: the unit is absolute.

**Default page geometry** (for the "standard" 66-char rendering):
- Content width: 28,800 tu (450 CSS px)
- Left margin: 3,200 tu (50 CSS px)
- Top margin: 3,200 tu (50 CSS px)
- Line height: inferred from font metrics, typically 1.4x font size

### 4.5 File Structure

A tome file is a byte stream with no required header and no postamble. It is read strictly forward, streaming. The first byte determines the mode:

- **If the first byte is >= 0x20**: The file is a plain-text tome. Render as UTF-8 text in MLModern Typewriter, word-wrapping at the client's discretion. No further parsing is needed. (This preserves the property that any UTF-8 text file is valid tome.)
- **If the first byte is < 0x20**: The file is a typeset tome. Parse opcodes and content as described above. Metadata (META commands) and font definitions (FONT_DEF) should appear before the content they apply to.

This means: there is no magic number. A plain text file is valid. A typeset file begins with an opcode (typically META with the document title, or FONT_DEF to declare fonts).

**Recommended ordering** for typeset files:

```
META "title" "My Article"       # Document title
META "lang" "en"                # Language
META "width" "28800"            # Intended rendering width in tu
FONT_DEF 0 ... "rm-mlmr10"     # Roman
FONT_DEF 1 ... "rm-mlmr10-b"   # Bold
FONT_DEF 2 ... "rm-mlmtt10"    # Mono
LINK_DEF 0 "https://..."       # Pre-declare links
LINK_DEF 1 "https://..."
SECTION 1                      # H1
FONT 1                         # Bold for heading
DOWN 3200                      # Top margin
RIGHT 3200                     # Left margin
T h e   T i t l e              # Characters rendered with current font
LF_DOWN 1800                   # Next line
FONT 0                         # Roman for body
PARA                           # Paragraph start
T h e   f i r s t ...          # Body text
...
0xFF                           # End of stream
```

### 4.6 The Plain-Text Guarantee

Any valid UTF-8 text file, including one you write in Notepad, is a valid tome document. When rendered:
- Font: MLModern Typewriter (mlmtt10) or client-preferred monospace
- Word wrapping: at client's discretion
- Tab stops: every 8 characters
- Lines separated by LF (0x0A)
- No special treatment of any character except TAB and LF

This means existing plain-text content (RFCs, source code, READMEs) can be served as `.tome` today.

### 4.7 Standard Font Set

These fonts are considered "installed" on all tome clients. They are never embedded in a tome file:

| Slot | Font | Role |
|------|------|------|
| — | MLModern Roman (mlmr10) | Body text |
| — | MLModern Italic (mlmri10) | Emphasis |
| — | MLModern Bold (mlmbx10) | Headings, strong emphasis |
| — | MLModern Bold Italic (mlmbxi10) | Combined |
| — | MLModern Typewriter (mlmtt10) | Code, monospace |
| — | MLModern Math (mlmmi10, mlmsy10) | Mathematical symbols |
| — | GNU Unifont | Unicode fallback |

Total install size: ~3 MB (one-time cost). These are freely licensed fonts.

Publishers can reference non-standard fonts. When they do, they should embed inline bitmap glyphs for the characters used on the first screen (see 4.8).

### 4.8 Inline Bitmap Fonts (First-Screen Optimization)

For non-standard fonts, the first screenful should not be blocked on font download. The publisher can include low-resolution bitmap glyphs inline using the EXTENSION opcode:

```
EXTENSION type=0x01 len=... data=[glyph_table]
```

The glyph table format:

```
[codepoint: varint] [width: uint8] [height: uint8] [bitmap: width*height bits, padded to byte boundary]
```

At 16x32 pixels per glyph (matching Unifont's double-width resolution), each glyph is 64 bytes. A first screen might use 60-80 unique glyphs = ~4-5 KB. The renderer draws these while the real font downloads in the background, then re-renders with the proper glyphs. Visually this is similar to FOUT (flash of unstyled text) but smoother because the bitmap approximates the real glyph shape.

**For standard fonts, this is unnecessary.** Clients already have the glyphs.

### 4.9 Color and Dark Mode

Colors are specified as 32-bit RGBA values. A tome file may include two color schemes:

```
META "color-scheme" "light"         # Default scheme
COLOR 0x333333FF                    # Dark gray text
BG_COLOR 0xFFFFFAFF                 # Warm white background

META "dark-color" "0xCCCCCCFF"      # Text in dark mode
META "dark-bg-color" "0x1A1A1AFF"   # Background in dark mode
```

Clients choose which scheme to apply. If no colors are specified, the default is black text on white background, with the client free to invert for dark mode (the same freedom readers have with physical books — they don't, but they could).

### 4.10 Images

Images are the biggest threat to compactness. Tome handles them conservatively:

1. **External images** (preferred): `IMAGE_DEF id w h "https://..."`. The reader fetches the image separately. The document renders immediately with a placeholder rectangle of the declared dimensions.
2. **Inline images**: `IMAGE_DEF id w h "data:image/jxl;base64,..."`. Small images (icons, diagrams) can be inlined as data URIs. JPEG XL is preferred for its compression and progressive decoding.
3. **No images**: The purest form. Text only. If the document is smaller than a screenshot, it's certainly smaller without images.

The `IMAGE_DEF` always declares width and height so the layout is stable before the image loads — no layout shift.

### 4.11 Hyperlinks

Links are pre-declared (like font definitions) and referenced by small numeric IDs:

```
LINK_DEF 0 "https://example.com"
LINK_DEF 1 "#section-2"           # Internal anchor

...later in the stream...

LINK_START 0
FONT 1                            # Maybe underlined or colored
t h e   l i n k   t e x t
FONT 0
LINK_END
```

Internal links reference ANCHOR names:
```
ANCHOR "section-2"
SECTION 2
T h e   s e c o n d   s e c t i o n
```

The reader decides how to style links (color, underline, cursor change). The tome file positions the text; the reader adds the interactive affordance.

## 5. What About Responsive Width?

Tome files are single-width. The `META "width"` declaration tells the reader the intended content width.

For different screen sizes, three strategies, in order of increasing effort:

### Strategy 1: Scale (Zero effort)

The reader scales the content to fit. Like PDF zoom. Works for any width ratio. Text may be small on narrow screens or large on wide screens. Good enough for most cases.

### Strategy 2: Center and Margin (Zero effort for publisher)

The reader renders at the declared width and centers the result. Wide screens get generous margins (like a book page). Narrow screens scale down or scroll. This is what most well-designed blogs do anyway (max-width: 700px; margin: 0 auto).

### Strategy 3: Multiple Variants (Publisher effort)

The publisher generates separate files for different widths:

```
article.tome       → 66 chars wide (default)
article.45.tome    → 45 chars wide (mobile portrait)
article.90.tome    → 90 chars wide (wide screen)
```

The server uses HTTP content negotiation (Client Hints, `Sec-CH-Viewport-Width`) or `<link>` elements to serve the right one. The format itself is unchanged — width adaptation is a server/HTTP concern.

For the first version of tome, Strategy 2 is sufficient. Typography purists can use Strategy 3.

## 6. Size Analysis

A 2,000-word blog post (~12,000 characters):

| Component | Size | Notes |
|-----------|------|-------|
| Text content | 12 KB | The actual characters |
| Positioning | ~6 KB | RIGHT/DOWN/CR commands + varint params |
| Font declarations | ~200 B | 3-4 standard fonts, tiny |
| Link definitions | ~500 B | 10 links with URLs |
| Structure markers | ~100 B | Headings, paragraphs |
| Metadata | ~200 B | Title, author, lang |
| **Total** | **~19 KB** | |

With Brotli compression over HTTP: **~8 KB**.

Compare:
- Same article as HTML/CSS/JS: ~2,000 KB (median)
- Same article as Gemini: ~12 KB (no formatting)
- Same article as a PNG screenshot: ~300-500 KB

A PNG screenshot of a 2,000-word article at 1920px wide is at least 300 KB. The tome file at 19 KB is **16x smaller** than its own screenshot — comfortably meeting the "smaller than a screenshot" goal.

## 7. Deployment Path

### Phase 1: Specification + Reference Tooling

- Finalize the format specification
- Build a TeX-to-tome converter (Python, using DVI as an intermediate)
- Build a Markdown-to-tome converter (using a good line-breaking algorithm like Knuth-Plass)
- Build a command-line tome reader (renders to terminal using half-block characters or plain text fallback)

### Phase 2: Web Deployment

- Build a JavaScript tome renderer (~5 KB minified) that draws to Canvas
- Create a thin HTML wrapper: `<script src="tome.js"></script><script>tome.render("article.tome")</script>`
- Total page weight: 5 KB renderer + 19 KB content = **24 KB** (vs. 2 MB for typical HTML)
- Build a Wikipedia-to-tome converter as a proof of concept

### Phase 3: Native Readers

- Browser extension that intercepts `.tome` responses
- Native iOS/macOS reader (Core Text rendering)
- Native terminal reader (sixel graphics or Kitty protocol for high-fidelity; plain text fallback)

### Phase 4: Standardization

- Publish as an Internet-Draft
- Register MIME type: `application/tome` (typeset) / `text/tome` (plain-text subset)
- File extension: `.tome`
- Propose for browser implementation

## 8. Answers to Open Questions from README

**What should the default unit be?**
→ 1/64th of a CSS pixel ("tome unit"). See section 4.4.

**What size should the inline bitmap fonts be?**
→ 16x32 pixels per glyph (matching Unifont's resolution). This gives readable glyphs at typical screen sizes while keeping the bitmap table under 5 KB for a screenful of text. See section 4.8.

**Navigation: document or reader?**
→ Reader. The document provides structural markers (SECTION, ANCHOR) that the reader can use to build a table of contents, but the navigation UI is the reader's responsibility. This parallels how PDF readers provide page thumbnails and bookmarks from the document's structure without the document dictating the UI.

**Dark mode?**
→ Documents may suggest two color schemes via META. The reader chooses. See section 4.9.

## 9. Remaining Open Questions

1. **Should the font hash be a proper cryptographic hash or a shorter checksum?** The current proposal uses 4-byte hashes. That's only 32 bits — collisions are probable across all fonts in existence. Consider using 8 bytes (half of SHA-256) for uniqueness while staying compact. Or: define a font registry with canonical short IDs for the standard fonts, and only use hashes for non-standard fonts.

2. **Right-to-left text**: The README notes that "RTL languages have negative widths." This works at the glyph level, but what about paragraph-level bidi? Should there be a DIRECTION opcode, or is this implicit from the language metadata?

3. **Math**: TeX's greatest strength. Should tome have first-class math support, or treat mathematical expressions as positioned glyphs (which is how DVI does it)? Positioned glyphs work for rendering but lose the semantic structure of equations.

4. **Tables**: Pre-positioned characters can draw any table, but the semantic structure (rows, columns, cells) is lost. Should there be table-related structure opcodes for accessibility?

5. **Footnotes and margin notes**: How should these be handled? As inline content at the point of reference? As content at the bottom of a "page" (but tome is not page-oriented)? As links to anchors?

6. **Embedded metadata for search engines**: Should META support OpenGraph / Schema.org conventions so that link previews work?

7. **Signature / integrity**: Should tome files support signing? A publisher could include a cryptographic signature so readers can verify the content hasn't been modified. This would be valuable for archival.

8. **The JavaScript renderer's relationship to Canvas vs. DOM**: Canvas rendering is faster but loses text selectability and accessibility. DOM rendering preserves these but is slower. A hybrid (invisible DOM for accessibility + Canvas for display) might be optimal.
