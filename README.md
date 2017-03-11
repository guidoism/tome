# The .tome file format

## Requirments
* Single file
* Contains metadata, text, and scans
* Meant to represent one canonical Author-Title books comprised of one or more editions
* Might contain multiple scans and multiple OCR runs
* Annotations and corrections by humans
* Easy to be worked on with standard tools
* History of changes are kept
* Flow of text as a DAG with breaks, footnotes, and images appearing inline or as a branch in the DAG
* Lists are represented inline with special unicode characters representing an entry in the list and how far it's indented
* Everything is UTF-8

