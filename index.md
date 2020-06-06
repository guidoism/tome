---
layout: default
title: Tome File Format
---

This format represents a typeset document, like a book, article, or blog post.
It is meant as a replacement for **HTML/CSS** and **PDF** for those contexts.

Files are either optimized for archival -- It's meant to preserve as much as
possible and live in source control -- Or optimized for viewing.

## Viewing Regime

The viewing regime is optimized for compactness and speed. The metric we measure
is latecy to first page. 

Most importantly, and uniquely, it is typeset for a number of popular screen
or paper widths.

The serialization format -- [Cap'N Proto](https://capnproto.org) -- Was chosen
because we didn't want yet another custom serialization format and Cap'N Proto
allows to use without decoding before use.

## Archival Regime

We have a goal of being iosmorphic with **PDF/A**.

