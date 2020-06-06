---
layout: default
title: Tome File Format
---

This format represents a typeset document, like a book (scanned or not),
article, or blog post. It is meant as a replacement for **HTML/CSS** and **PDF**
for for browsing the internet and reading -- Neither of these formats are
optimized for this overwhelmingly common use-case.

**HTML/CSS** -- So complex that only a few layout engines exist and noboby could
imagine trying to write one from scratch. The complexities of layout are forced
onto the client, which might be energy-constrained, and certainly adds to the
latency. The downsides have been written about ad-nauseum so I will refrain from
repeating them here.

**PDF** -- Honestly not as bad of a format as people make it out to be -- Most
problems are tooling related. It's very possible to make a **PDF** that works
well for reading documents over the internet -- You just need to get the width
just right and you need to use the progressive format and for scanned documents
you should use **JBIG2** compression.

Files are either optimized for archival -- It's meant to preserve as much as
possible and live in source control -- Or optimized for viewing.

## Viewing Regime

The viewing regime is optimized for compactness and speed. The metric we measure
is latecy to first page. 

Most importantly, and uniquely, it is typeset for a number of popular screen
or paper widths.

Navigation should *not* be part of the content, it should be provided by the
reading software.

The serialization format -- [Cap'N Proto](https://capnproto.org) -- Was chosen
because we didn't want yet another custom serialization format and Cap'N Proto
allows to use without decoding before use.

## Archival Regime

We have a goal of being iosmorphic with **PDF/A**.

