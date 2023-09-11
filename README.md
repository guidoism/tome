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
* The read-to-write ratio is potentially very high therefore we should optimize for the reading experience.
* Rendering a document under normal circumstances should be not much more than the following commands for each character: 1. Move the drawing cursor to the next location (relative), 2. Draw the glyph for the current character.
* Given the previous point, under normal circumstances, the client should *not* have to do any fancy layout. It should just follow commands. Layout should have happened beforehand on the server when the document was published.
* We shouldn't optimize for the possibility of super-wide or super-narrow layouts. Normal documents have a width of xxx-xxx characters (Bringhurst) therefore it might make sense to prerender a few common widths in a way in which the author intended and declare defeat for everything else. They will still get the content but it should be throught of more as a stream of characters rather than something properly laid out.
* Plain-text with a fixed-width font should always be a valid document. In fact, the generated form of this style document should be identical to one produced by-hand in a text editor.
* The DVI format is a good starting place to replace HTML for hypertext documents. It's compact, simple, and already very close to the ideal of being able to produce a docuemnt with a fixed-width font in a text editor. (See Section 2.2 of https://tug.org/pracjourn/2007-1/cho/cho.pdf for how to create a DVI document from scratch)
* Improvements to DVI would be: native UTF-8, hyperlinks (I think people currently use "specials" for this), no need for preamble or postable for plain-text documents, always include the unicode code points even if referring to different glyphs and other semantic improvements needed for accessibility)
* TeX's standard fonts are a good default, though maybe using the ones optimized for screens rather than printing. The unifont is a good fallback for the rest of the unicode glyphs.
