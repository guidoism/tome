This format represents a typeset doc, like a book, article, or blog post. 
It's optimized for compactness and speed. The doc can be displayed before
it's been entirely downloaded.

Most importantly, and uniquely, it is typeset for a number of popular screen
or paper widths.

The serialization format is [Cap'N Proto](https://capnproto.org).

We have a goal of being iosmorphic with PDF/A.

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
