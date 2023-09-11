# The .tome file format

![XKCD Standards](https://imgs.xkcd.com/comics/standards.png)

# Motivations

The web — circa 2023 — is optimized for webapps. The public
needs a document-centric hypertext document format that prioritizes
legibility, accessibility, and latency to first complete screen rendering.

This is my quixotic attempt to put forth something better, 
get an official RFC published, 
and get this adopted by the document-centric web.

# Assumptions

* The current web is a cacophyony of bad taste
* Various people advotated for a "small web" have been experiementing with the use of Gopher and Gemini. We should learn from these experiments but we don't believe that a protocol incompatible with the web will further our goals.
* The format should be optimized for latency from the start of the first HTTP GET to being finished drawing the first screenful of text in the intended fonts.
* The read-to-write ratio is potentially very high therefore we should optimize for the reading experience.
* Good typography is important. A blog entry in 2023 should look no worse than a CS research paper from 1988.
* Rendering a document under normal circumstances should be not much more than the following commands for each character: 1. Move the drawing cursor to the next location (relative), 2. Draw the glyph for the current character.
* Given the previous point, under normal circumstances, the client should *not* have to do any fancy layout. It should just follow commands. Layout should have happened beforehand on the server when the document was published.
* We shouldn't optimize for the possibility of super-wide or super-narrow layouts. Normal documents have a width of xxx-xxx characters (Bringhurst) therefore it might make sense to prerender a few common widths in a way in which the author intended and declare defeat for everything else. They will still get the content but it should be throught of more as a stream of characters rather than something properly laid out.
* Plain-text with a fixed-width font should always be a valid document. In fact, the generated form of this style document should be identical to one produced by-hand in a text editor.
* The DVI format is a good starting place to replace HTML for hypertext documents. It's compact, simple, and already very close to the ideal of being able to produce a docuemnt with a fixed-width font in a text editor. (See Section 2.2 of https://tug.org/pracjourn/2007-1/cho/cho.pdf for how to create a DVI document from scratch)
* Improvements to DVI would be: native UTF-8, hyperlinks (I think people currently use "specials" for this), no need for preamble or postable for plain-text documents, always include the unicode code points even if referring to different glyphs and other semantic improvements needed for accessibility)
* The standard fonts should be standard and distributed to everyone. We don't want to display different fonts to different people because their OS vendor chose to buy fonts from a particular foundary.
* TeX's standard fonts are a good default, though maybe using the ones optimized for screens rather than printing. The unifont is a good fallback for the rest of the unicode glyphs.
* It's not entirely clear in my head whether navigation controls around the document or website should be provided by the docuemnt or the reader.
  
# Proposal

* A plain-text UFT-8 document is valid and should be rendered as is with MLModern-typewriter with word-wrapping being client-configurable (given this is a monospaced font clients should also make it easy to swap out with your desired monospaced font)
* Use the first 31 characters (excluding null) of ASCII (and UTF-8) as the control characters they were intended to be. We don't need to follow them exactly, but it would be nice to be a little bit consistent so if we open up a document in a text editor we can understand some of it.
* Numbers are encoded as [LEB128](https://en.wikipedia.org/wiki/LEB128)

`
    if ch >= 32
        if ch < 128:
            draw(ch)
            moveright(width(ch))
    else:
        if ch == 9:               # ASCII Horizontal Tab
            x = readint(input)
            moveright(x)
        elif ch == 11:            # ASCII Vertical Tab
            y = readint(input)
            movedown(y)
        
`

### Original ASCII Control Character Semantics

- 01 Start of Heading
- 02 Start of Text
- 03 End of Text
- 04 End of Transmission
- 05 Enquiry
- 06 Acknowledgement
- 07 Bell
- 08 Backspace
- 09 Horizontal Tab
- 10 Line Feed
- 11 Vertical Tab
- 12 Form Feed
- 13 Carriage Return
- 14 Shift Out
- 15 Shift In
- 16 Data Link Escape
- 17 Device Control 1 (often XON)
- 18 Device Control 2
- 19 Device Control 3 (often XOFF)
- 20 Device Control 4
- 21 Negative Acknowledgement
- 22 Synchronous Idle
- 23 End of Transmission Block
- 24 Cancel
- 25 End of Medium
- 26 Substitute
- 27 Escape
- 28 File Separator
- 29 Group Separator
- 30 Record Separator
- 31 Unit Separator
