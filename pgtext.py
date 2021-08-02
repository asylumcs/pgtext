#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
  pgtext.py
  MIT license (c) 2021 Asylum Computer Services LLC
  https://asylumcs.net
"""

# pylint: disable=C0103, R0912, R0915, E1101
# pylint: disable=too-many-instance-attributes, too-many-locals, no-self-use
# pylint: disable=bad-continuation, too-many-lines, too-many-public-methods
# pylint: disable=bare-except, broad-except
# pylint: disable=line-too-long
# pylint: disable=too-many-nested-blocks

# https://golang.org/pkg/unicode/#pkg-constants for regex defs

# not done (compared to gutcheck)
# common typos; gutcheck.typ not used
# get language. if Dutch or French, special handling of dashes, punct.

import os
import sys
import argparse
import tempfile
import datetime
import regex as re
import pprint

theWordlist = set([])  # set of words, contractions from wordlist.txt
reports = {}  # a map of description to list
reports3 = []  # top-level sequential reports

def fatal(msg):
    """ fatal error: print message and exit """
    print(f"FATAL: {msg}")
    sys.exit(1)

def loadWordlist():
    """
    wordlist is English words with contractions
    it must exist in same directory as main program
    """
    loc = os.path.dirname(os.path.realpath(__file__));
    fn = f"{loc}/wordlist.txt"
    if not os.path.isfile(fn):
        fatal(f"wordlist file {fn} not found")
    try:
        wbuf = open(fn, "r", encoding="UTF-8").read()
        t = wbuf.split("\n")
    except Exception as e:
        fatal(f"file failed to load. ({e})")
    # remove any trailing blank lines
    while len(t) > 1 and t[-1] == "":
        t.pop()
    # the wordlist has comments starting with "--"
    # and (some) plural forms listed with trailing "%"
    #   absorbencies%, absorbency
    for item in t:
        if item.startswith("--"):
            continue
        item = item.replace("%", " ")
        theWordlist.add(item)

class P:
    """
    one object of this class for every paragraph in the book

    structure:
      ptext string: the entire paragraph in one string, spaces preserved
      lines []string: each line of this paragraph from the original text
      reports []string: equal-length blank strings for error marks.
    """
    def __init__(self):
        self.ptext = ""  # the paragraph text as one long string, no linebreaks
        self.lines = []  # each line in the original paragraph
        self.reports = [] # one per line of the original paragraph
        self.startline = 0 # line number in wb where paragraph started
        self.wset =  set([]) # all words in this paragraph

class Paragraphs:
    """
    paragraph class
    paragraphs are accessed with:
      for pn, ap in enumerate(paras.parg):
    """

    def __init__(self):
        self.parg = []

    def add(self, p):
        self.parg.append(p)

    def populatePara(self, wb):
        """  msg """
        s = "" # string to hold entire paragraph
        startline = 0 # first line of paragraph in wb
        linelens = []  # line lengths for each line in paragraph
        i = 0
        while i < len(wb):
            if wb[i] == "":
                # skip blank lines
                i += 1
                continue
            # start a paragraph
            # to handle spacing, we need to remember the starting line number
            np = P()
            np.startline = i
            np.lines.append(wb[i])
            np.reports.append(list(" "*len(wb[i])))
            s = wb[i]  # cumulative paragraph text
            i += 1
            while i < len(wb) and wb[i] != "":
                np.lines.append(wb[i]) # more lines in this paragraph
                np.reports.append(list(" "*len(wb[i])))
                s = s + " " + wb[i]  # cumulative paragraph text
                i += 1
            # here we are at EOF or on a blank line. finish the structure
            np.ptext = s
            self.add(np)

    def trlate(self, pn, posn):
        """
        given a paragraph number and a linear position,
        convert to a line within the paragraph and an offset
        """
        i = 0
        while posn >= len(self.parg[pn].lines[i]):
            posn -= (len(self.parg[pn].lines[i]) + 1)
            if posn < 0: # flag may be on the hidden space between lines.
                posn = 0
            i += 1
        return i, posn

    def startline(self, pn):
        """ starting line in text for this paragraph """
        return self.parg[pn].startline

    def npara(self):
        """ how many paragraphs """
        return(len(self.parg))

    def inject(self, m, n, p, z='^'):
        """
        reports an error or warning in paragraph m, line n, position p, symbol z (0-based)
        """
        self.parg[m].reports[n][p] = z

def loadFile(fn):
    """
    load specified UTF-8 file. strips BOM if present
    """
    if not os.path.isfile(fn):
        fatal("file {} not found".format(fn))
    try:
        wbuf = open(fn, "r", encoding="UTF-8").read()
        wbs = wbuf.split("\n")
        # remove BOM on first line if present
        t31 = ":".join("{0:x}".format(ord(c)) for c in wbs[0])
        if t31[0:4] == "feff":
            wbs[0] = wbs[0][1:]
    except Exception as e:
        fatal(f"file failed to load. ({e})")
    while len(wbs) > 1 and wbs[-1] == "":  # no trailing blank lines
        wbs.pop()
    return wbs

"""
main program
"""

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--infile", help="input file", required=True)
parser.add_argument("-o", "--outfile", help="output file", default="report.txt", required=False)
parser.add_argument("-v", "--verbose", help="show all reports", action='store_true')
args = vars(parser.parse_args())

pp = pprint.PrettyPrinter(indent=4)

# load word list, including common English contractions
loadWordlist()

paras = Paragraphs() # new, empty Paragraph class

wb = loadFile(args["infile"])
paras.populatePara(wb)

def report(pn, item, alt='^', offset=0):
    """ the 'alt' argument, if present, replaces the default '^' """
    line, posn = paras.trlate(pn, item.start())
    paras.inject(pn, line, posn, alt)

def report2(pn, item, desc):
    """ paragraph number, where it is (linearly), description """

    # if description already in map, append to reports for that error
    if desc not in reports:
        reports[desc] = []
    line, _ = paras.trlate(pn, item.start())
    theline = paras.startline(pn)+line
    # append only new reports
    if f"{theline} {wb[theline]}" not in reports[desc]:
        reports[desc].append(f"{theline} {wb[theline]}")

def report3(s):
    """ top level reports, not associated with a line number """
    reports3.append(s)

# determine if the text uses straight or curly quotes. use that to
# flag those that are inconsistent later

count_straight = 0
count_curly = 0
for pn, ap in enumerate(paras.parg):
    s = ap.ptext  # get the paragraph
    count_straight += s.count("\"")
    count_straight += s.count("'")
    count_curly += s.count("”")
    count_curly += s.count("“")
    count_curly += s.count("’")
    count_curly += s.count("‘")
if count_curly > 0 and count_straight > 0:
    report3(f"error: mixed quotes found. curly:{count_curly} straight:{count_straight}")

# run tests, paragraph at-a-time
for pn, ap in enumerate(paras.parg):
    s = ap.ptext # get a paragraph as one string

    # allow Illustration, Greek, Music, "Transcriber" or number after '['
    m = re.finditer(r'\[[^IGMT\d]', s)
    for item in m:
        report2(pn, item, "unexpected character after '['")

    # punctuation checks

    # punctuation after "the"
    m = re.finditer(r'(^|[\p{Z}\p{P}])the\p{P}', s)
    for item in m:
        report2(pn, item, "punctuation after 'the'")
    # date format October 8,1948
    m = re.finditer(r",1\p{N}\p{N}\p{N}", s)
    for item in m:
        report2(pn, item, "suspect date punctuation")
    # special cases of contiguous punctuation
    s2 = s.replace("etc.,", "") # allow "etc.,"
    m = re.finditer(r"(,\.)|(\.,)|(,,)|([^\.]\.\.([^\.]|$))", s2)
    for item in m:
        report2(pn, item, "suspect contiguous punctuation")
    # collapsed punctuation
    #m = re.finditer(r"[\p{L}|\p{N}]\p{Z}?[\.:;,][\p{L}|\p{N}]", s)
    m = re.finditer(r"(\p{L})[\.:;,](\p{L})", s)
    for item in m:
        if not (item.group(1).isnumeric() and item.group(2).isnumeric()):
            report2(pn, item, "incorrectly spaced punctuation")

    # mixed case in word (3 checks)

    # first upper followed by upper then lower somewhere in word
    # start of line or space or punctuation
    # two upper case in a row, optionally other characters, then
    # a lower case letter before the word ends
    m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Lu}\p{Lu}\p{L}?\p{Ll}', s)
    for item in m:
        report2(pn, item, "mixed case in word")
    # first upper followed by lower then upper somewhere in word
    m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Lu}[^\p{Z}\p{P}]*?\p{Ll}\p{Lu}', s)
    for item in m:
        report2(pn, item, "mixed case in word")
    # first lower followed by upper anywhere in word
    m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Ll}[^\p{Z}\p{P}]*?\p{Lu}', s)
    for item in m:
        report2(pn, item, "mixed case in word")

    # rare to end word
    m = re.finditer(r'(cb|gb|pb|sb|tb|wh|fr|br|qu|tw|gl|fl|sw|gr|sl|cl|iy)($|[\p{Z}\p{P}])', s)
    for item in m:
        report2(pn, item, "unusual characters ending word")

    # rare to start word
    m = re.finditer(r'(^|[\p{Z}\p{P}])(hr|hl|cb|sb|tb|wb|tl|tn|rn|lt|tj)', s)
    for item in m:
        report2(pn, item, "unusual characters starting word")

    # single character paragraph
    m = re.finditer(r'^.$', s)
    for item in m:
        report2(pn, item, "single character paragraph")

    # hyphenation adjacent to space
    m = re.finditer(r'\p{L}(-\s+|\s+-)\p{L}', s)
    for item in m:
        report2(pn, item, "hyphenation adjacent to space")

    # exclamation point suspect: “You should runI”
    m = re.finditer(r'I”', s)
    for item in m:
        report2(pn, item, 'exclamation point suspect')

    # unexpected period: "this is. not a easy task"
    # do not report common abbreviations that appear with a period,
    # such as "50 per cent. per annum"
    m = re.finditer(r'(\p{L}+)\.\p{Z}\p{Ll}', s)
    for item in m:
        if not item.group(1) in [
            "cent", "cents", "viz", "vol", "vols", "vid", "ed", "al", "etc", "op", "cit",
            "deg", "min", "chap", "oz", "mme", "mlle", "mssrs", "gym"]:
            report2(pn, item, 'unexpected period')

    # disjointed contraction
    m = re.finditer(r'\p{Z}’(m|ve|ll|t)($|[\p{Z}\p{P}])', s)
    for item in m:
        report2(pn, item, 'disjointed contraction')

    # suspected HTML tag
    m = re.finditer(r'<[^>]+>', s)
    for item in m:
        report2(pn, item, 'suspected HTML tag')

    # quote direction (by context)
    m = re.finditer(r'([\.,;!?’‘]+[‘“])|([A-Za-z]+[“])|([A-LN-Za-z]+[‘])|(“ )|( ”)|(‘s\s)', s)
    for item in m:
        report2(pn, item, 'quote direction (by context)')

    # standalone 0 or 1
    m = re.finditer(r'(^|[\p{Z}\p{P}])([01])($|[\p{Z}\p{P}])', s)
    for item in m:
        if not (item.group(2) == "1" and item.group(3) == ","):  # allow 1,000 or Oct. 1,
            report2(pn, item, 'standalone 0 or 1')

    # mixed numbers/letters in word
    m = re.finditer(r'(^|[\p{Z}\p{P}])([^\p{Z}\p{P}]*(\p{L}\p{N}|\p{N}\p{L})[^\p{Z}\p{P}]*)($|[\p{Z}\p{P}])', s)
    for item in m:
        theword = item.group(2)
        if not re.match(r"\d+(st|nd|rd|th)", theword):
            report2(pn, item, f"mixed numbers/letters in word {item.group(2)}")

    # Blank Page placeholder
    m = re.finditer(r'blank page', s, re.IGNORECASE)
    for item in m:
        report2(pn, item, 'Blank Page placeholder')

    # hyphenation and dashes

    # mixed hyphen-dash
    # note, will catch the common construction: space+en-dash+space
    m = re.finditer(r'(\p{Pd})(\p{Pd})', s, re.IGNORECASE)
    for item in m:
        if item.group(1) != item.group(2):
            report2(pn, item, 'mixed hyphen-dash')
    # mixed hyphen-dash
    m = re.finditer(r'(\p{Pd})', s, re.IGNORECASE)
    for item in m:
        if item.group(1) not in "—-–":  # em-, hyphen, en-dash
            report2(pn, item, 'potentially unsafe ePub dash')
    # spaced dash
    m = re.finditer(r'\p{Z}\p{Pd}', s, re.IGNORECASE)
    for item in m:
        report2(pn, item, 'spaced dash')
    m = re.finditer(r'\p{Pd}\p{Z}', s, re.IGNORECASE)
    for item in m:
        report2(pn, item, 'spaced dash')

    # unusual characters
    # allow special pattern for DP-style thought break
    m = re.finditer(r'[^A-Za-z0-9 \.,:;“”‘’\-\?—!\(\)_\[\]]+', s)
    for item in m:
        if not re.match('^\s+\*\s+\*\s+\*\s+\*\s+\*', s):  # allow DP thought break
            report2(pn, item, f"unusual character {item.group(0)}")

    NOCOMMAPATTERN = "(^|[\p{Z}\p{P}])(the,|it’s,|their,|an,|mrs,|a,|our,\
    |that’s,|its,|whose,|every,|i’ll,|your,|my,|mr,|mrs,|mss,|mssrs,|ft,|\
    pm,|st,|dr,|rd,|pp,|cf,|jr,|sr,|vs,|lb,|lbs,|ltd,|i'm,|during,|let,|\
    toward,|among,)"

    # commas not expected after certain words
    m = re.finditer(NOCOMMAPATTERN, s)
    for item in m:
        report2(pn, item, 'unexpected comma after word')

    NOPERIODPATTERN = "(^|[\p{Z}\p{P}])(every\.|i’m\.|during\.|that’s\.\
    |their\.|your\.|our\.|my\.|or\.|and\.|but\.|as\.|if\.|the\.|its\.\
    |it’s\.|until\.|than\.|whether\.|i’ll\.|whose\.|who\.|because\.|when\.\
    |let\.|till\.|very\.|an\.|among\.|those\.|into\.|whom\.|having\.|thence\.)"

    # periods not expected after certain words
    m = re.finditer(NOPERIODPATTERN, s)
    for item in m:
        report2(pn, item, 'unexpected period after word')

    # paragraph ends with unusal character
    m = re.finditer(r'[^.”\?!\*:]$', s)
    for item in m:
        report2(pn, item, 'paragraph ends with unusual character')

    # inconsistent quotation marks
    if count_straight < count_curly:
        m = re.finditer(r'[\'"]', s)
    else:
        m = re.finditer(r'[‘’“”]', s)
    for item in m:
        report2(pn, item, 'inconsistent quote marks')

    # ellipsis checks
    m = re.finditer(r'(\.\.\.\.)[^\p{Z}]',s)
    for item in m:
        report2(pn, item, 'suspect ellipsis check')
    m = re.finditer(r'\P{Z}(\.\.\.)\p{Z}',s)
    for item in m:
        report2(pn, item, 'suspect ellipsis check')
    m = re.finditer(r'\p{Z}(\.\.\.)\P{Z}',s)
    for item in m:
        report2(pn, item, 'suspect ellipsis check')
    m = re.finditer(r'\.\.\.\.\.',s)
    for item in m:
        report2(pn, item, 'suspect ellipsis check')

    # now a small FSM to deal with punctuation.
    # only works if smart quotes.

    if count_curly > 0 and count_straight == 0:
        # hide all known apostrophes
        s2 = re.sub(r"(\p{L})’(\p{L})", r"\1X\2", s)
        stack = []
        reported = False
        theline = paras.startline(pn)
        for c in s2:  # iterate character at a time
            if c == '“':  # open double quote
                # ok to push if empty or there isn't one there now
                if len(stack) == 0 or stack[-1] != '“':
                    stack.append('“')
                else:
                    report3(f"check quotes in paragraph starting at line {theline+1}")
                    report3(f"  {wb[theline]}")
                    reported = True
                    break
            if c == '”':  # close double quote
                # ok to pop if there is an open double quote available
                if len(stack) > 0 and stack[-1] == "“":
                    stack.pop()
                else:
                    report3(f"check quotes in paragraph starting at line {theline+1}")
                    report3(f"  {wb[theline]}")
                    reported = True
                    break
            if c == '‘':  # open single quote
                # ok to push if last push was ODQ
                if len(stack) > 0 and stack[-1] == "“":
                    stack.append('‘')
                else:
                    report3(f"check quotes in paragraph starting at line {theline+1}")
                    report3(f"  {wb[theline]}")
                    reported = True
                    break
            if c == '’':  # (maybe) close single quote
                # ok to pop if there is an open single quote available
                if len(stack) > 0 and stack[-1] == "‘":
                    stack.pop()
                else:
                    # cannot reliably identify CSQ from apostrophe
                    pass

        # at end of paragraph scan, stack should be empty, or
        # if can have an open double quote if the
        # next paragraph starts with an open double quote (continued quote)
        if not reported and len(stack) == 1 and stack[-1] == '“':
            # are we at last paragraph? is it a run-on quote?
            if pn >= paras.npara() - 1 or not wb[paras.startline(pn+1)].startswith("“"):
                theline = paras.startline(pn)
                report3(f"check quotes in paragraph starting at line {theline+1}")
                report3(f"  {wb[theline]}")

# some checks are per-line checks so working out of the para class doesn't help
# trailing space on line
# for w, aline in enumerate(ap.lines):
#    m = re.search(r' $', aline)
#    if m:
#        paras.inject(pn, w, len(ap.lines[w])-1)

# do the line-by-line checks

# long lines are absolute
# short lines must be considered wrt surrounding lines
# PG definitions:
#   define LONGEST_PG_LINE   75
#   define WAY_TOO_LONG      80
#   define SHORTEST_PG_LINE  55
#
# make no reports if no lines are too short or too long

longest = []
shortest = []

for i in range(len(wb)):
    if len(wb[i]) >= 75:
        longest.append([i, len(wb[i])])
    if i != 0 and len(wb[i-1]) > len(wb[i]) and i != len(wb)-1 and len(wb[i]) < len(wb[i+1]) and len(wb[i-1]) > 55:
        if len(wb[i]) != 0 and len(wb[i]) <= 55:
            shortest.append([i, len(wb[i])])

# sort by second value, the length
longest.sort(key=lambda a: a[1])
count = 5
if len(longest) > 0:
    report3("long lines:")
    while len(longest) > 0 and count > 0:
        atup = longest.pop()
        report3(f"  {atup[0]+1:5}: {wb[atup[0]]} ({atup[1]})")
        count -= 1

shortest.sort(key=lambda a: a[1], reverse=True)
count = 5
if len(shortest) > 0:
    report3("short lines:")
    while len(shortest) > 0 and count > 0:
        atup = shortest.pop()
        report3(f"  {atup[0]+1:5}: {wb[atup[0]]} ({atup[1]})")
        count -= 1

# save results to specified file

with open(args["outfile"], "w") as f:
    f.write("<pre>")
    f.write("pgtext run report\n")
    f.write(f"run started: {str(datetime.datetime.now())}\n");
    f.write("source file: {}\n".format(os.path.basename(args['infile'])))
    f.write(f"<span style='background-color:#FFFFDD'>close this window to return to the UWB.</span>\n");
    f.write("\n")

    for line in reports3:
        f.write(f"{line}\n")

    # these are the ones recorded with report2
    # reports is a map. convert to list and sort
    rlist = sorted(list(reports))
    for k in rlist:
        f.write(f"{k}\n")
        count = 0
        limit = 4
        if args["verbose"]:
            limit=100
        for line in reports[k]:
            if count < limit:
                f.write(f"   {line}\n")
            if count == limit:
                remain = len(reports[k]) - limit
                f.write(f"   ... {remain} more\n")
            count += 1
    f.write("</pre>")