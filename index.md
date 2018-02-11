---
layout: default
title: Tome File Format
---

This format represents a typeset doc, like a book, article, or blog post. 
It's optimized for compactness and speed. The doc can be displayed before
it's been entirely downloaded.

Most importantly, and uniquely, it is typeset for a number of popular screen
or paper widths.

The serialization format is [Cap'N Proto](https://capnproto.org).

We have a goal of being iosmorphic with **PDF/A**.

## Schema

    struct Tome {
      glyph_dictionary @0 :Int64;
      lines @1 :List(Line);
      
      struct Line {
        glyphs @0 :List(PositionedGlyph);
        relative_position @1 :int8;
      }
      
      struct PositionedGlyph {
        glyph_id @0 :UInt32;
        relative_position @1 :int8;
      }
    }

We use low-bit relative offsets since in most cases the next glyph is very
close by. If it's not then we use an empty glyph for the next glyph.

A glyph dictionary not only contains the common letters but also contains 
strings of letters and even entire words or phrases.
