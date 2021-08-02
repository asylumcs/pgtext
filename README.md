# pgtext

A text analysis program used before/during upload to Project Gutenberg

## Overview

This is a Python program used to analyze a UTF-8 text file. It accepts
a UTF-8 source file and produces a report file in HTML for display in
a browser, where color-coding may be used.

Examples of tests it makes:

- curly quote checks
- other punctuation checks (i.e. punctuation after the word "the")
- character case issues
- rare word starting characters, ending characters
- disjointed contractions (i.e. “they ’re not here.”)
- unusual characters
- long lines, short lines

## Usage

### Standalone

As a standalone program use this command line:

    `python3 pgtext.py -i sourcefile.txt -o report.htm`

You may also include "-v" to get verbose reports.

### In the UWB

This is one of the tests available in the
[UWB](https://uwb.pglaf.org).
Currently it runs there in 'verbose' mode, providing all reports.

## Requirements

This program requires these Python packages:

- regex (pip3 install regex)
