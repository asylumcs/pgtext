#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
  pgtext.py
  MIT license (c) 2021 Asylum Computer Services LLC
  https://asylumcs.net
  
  TODO: mixed case in word. ignore MacPherson if it occurs many times.
        staircase versus "stair-case"
        staircase versus "stair case"
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
import unicodedata
import time

theWordlist = set([])  # set of words, contractions from wordlist.txt
reports = {}  # a map of description to list
reports3 = []  # top-level sequential reports
proper_names = []  # list of probable proper names
hypwp = {}  # map of hyphenated words/phrases
nhypwp = {}  # corresponding map of non-hyphenated words/phrases
quotetype = ""  # straight or curly quote predominance
allowed_mixed_case = []  # proper names with accepted mixed case


def fatal(msg):
    """fatal error: print message and exit"""
    print(f"FATAL: {msg}")
    sys.exit(1)


def loadWordlist():
    """
    wordlist is English words with contractions
    it must exist in same directory as main program
    """
    loc = os.path.dirname(os.path.realpath(__file__))
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
        self.reports = []  # one per line of the original paragraph
        self.startline = 0  # line number in wb where paragraph started
        self.wset = set([])  # all words in this paragraph


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
        """msg"""
        s = ""  # string to hold entire paragraph
        startline = 0  # first line of paragraph in wb
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
            np.reports.append(list(" " * len(wb[i])))
            s = wb[i]  # cumulative paragraph text
            i += 1
            while i < len(wb) and wb[i] != "":
                np.lines.append(wb[i])  # more lines in this paragraph
                np.reports.append(list(" " * len(wb[i])))
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
            posn -= len(self.parg[pn].lines[i]) + 1
            if posn < 0:  # flag may be on the hidden space between lines.
                posn = 0
            i += 1
        return i, posn

    def startline(self, pn):
        """starting line in text for this paragraph"""
        return self.parg[pn].startline

    def npara(self):
        """how many paragraphs"""
        return len(self.parg)

    def inject(self, m, n, p, z="^"):
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
parser.add_argument(
    "-o", "--outfile", help="output file", default="report.txt", required=False
)
parser.add_argument("-v", "--verbose", help="show all reports", action="store_true")
args = vars(parser.parse_args())

pp = pprint.PrettyPrinter(indent=4)

# load word list, including common English contractions
loadWordlist()

paras = Paragraphs()  # new, empty Paragraph class

wb = loadFile(args["infile"])
paras.populatePara(wb)


def report(pn, item, alt="^", offset=0):
    """the 'alt' argument, if present, replaces the default '^'"""
    line, posn = paras.trlate(pn, item.start())
    paras.inject(pn, line, posn, alt)


def report2(pn, item, desc):
    """paragraph number, where it is (linearly), description"""

    # if description already in map, append to reports for that error
    if desc not in reports:
        reports[desc] = []
    line, _ = paras.trlate(pn, item.start())
    theline = paras.startline(pn) + line
    # append only new reports
    if f"{theline} {wb[theline]}" not in reports[desc]:
        reports[desc].append(f"{theline} {wb[theline]}")


def report3(s, highlight=False):
    """top level reports, not associated with a line number"""
    if highlight:
        s = f"<span style='padding-left:0.6em; margin-top:1em; background-color:papayawhip;'>{s}</span>"
    reports3.append(s)


# determine if the text uses straight or curly quotes. use that to
# flag those that are inconsistent later if curly quotes are used.

count_straight = 0
count_curly = 0
for pn, ap in enumerate(paras.parg):
    s = ap.ptext  # get the paragraph
    count_straight += s.count('"')
    count_straight += s.count("'")
    count_curly += s.count("”")
    count_curly += s.count("“")
    count_curly += s.count("’")
    count_curly += s.count("‘")
if count_curly > count_straight:
    quotetype = "curly"
else:
    quotetype = "straight"
if count_curly > 0 and count_straight > 0:
    report3(f"error: mixed quotes found. curly:{count_curly} straight:{count_straight}")

# attempt to identify proper names used in this text
prop = {}  # map of capitalized words
for pn, ap in enumerate(paras.parg):
    s = ap.ptext
    m = re.finditer(r"\p{Lu}\p{L}+", s)
    for item in m:
        theword = item.group(0)
        if theword in prop:
            prop[theword] += 1
        else:
            prop[theword] = 1

# dictionary words that are common names
special_prop = [
    "Bud",
    "Will",
    "Jack",
    "Jimmy",
    "Carol",
    "Amber",
    "Mark",
    "Scott",
    "Frank",
]

# any capitalized word that is not in the wordlist as lower-case
# and that occurs at least twice is perhaps a proper name
for item in prop:
    if item in special_prop:
        proper_names.append(item)
    if not item.lower() in theWordlist and prop[item] >= 2:
        proper_names.append(item)

# save proper names with mixed capitalization
for item in proper_names:
    if re.search(r".\p{Ll}\p{Lu}|.\p{Lu}\p{Ll}", item):
        allowed_mixed_case.append(item)

# identify hyphenated words/phrases with counts
# 'desk-sergeant': 1, 'made-by-the-million': 1, etc.
for pn, ap in enumerate(paras.parg):
    s = ap.ptext
    m = re.finditer(r"(\p{L}+)-([\p{L}-]+)", s)
    for item in m:
        theword = item.group(0)
        if theword in hypwp:
            hypwp[theword] += 1
        else:
            hypwp[theword] = 1

# construct non-hyphenated version of hypwp
# list of non-hyphenated version of hyphenated words
nh_hypwp = []  # list of non-hyphenated versions of hypwp
for item in hypwp:
    nh_hypwp.append(re.sub(r"-", " ", item))

for pn, ap in enumerate(paras.parg):
    s = ap.ptext
    for lookfor in nh_hypwp:
        m = re.finditer("\P{L}" + lookfor + "\P{L}", s)
        for item in m:
            if lookfor in nhypwp:
                nhypwp[lookfor] += 1
            else:
                nhypwp[lookfor] = 1

# every entry in nhypwp represents a match hyp and non-hyp same phrase
if len(nhypwp) > 0:
    report3("hyphenation/non-hyphenation phrase report", True)
    for thephrase in nhypwp:
        hthephrase = re.sub(" ", "-", thephrase)
        report3(
            f'  "{thephrase}" ({nhypwp[thephrase]}) <-> "{hthephrase}" ({hypwp[hthephrase]})'
        )
        # find up to maxlist of each in the text
        maxlist = 3
        count_thephrase = 0
        count_hthephrase = 0
        for pn, ap in enumerate(paras.parg):
            s = ap.ptext  # get a paragraph as one string
            if count_thephrase < maxlist:
                m = re.finditer(thephrase, s)
                for item in m:
                    line, _ = paras.trlate(pn, item.start())
                    theline = paras.startline(pn) + line
                    report3(f"    {theline}: {wb[theline]}")
                    count_thephrase += 1
            if count_hthephrase < maxlist:
                m2 = re.finditer(hthephrase, s)
                for item in m2:
                    line, _ = paras.trlate(pn, item.start())
                    theline = paras.startline(pn) + line
                    report3(f"    {theline}: {wb[theline]}")
                    count_hthephrase += 1

# run tests, paragraph at-a-time
for pn, ap in enumerate(paras.parg):
    s = ap.ptext  # get a paragraph as one string

    # allow Illustration, Greek, Music, "Transcriber" or number after '['
    m = re.finditer(r"\[[^IGMT\d]", s)
    for item in m:
        report2(pn, item, "unexpected character after '['")

    # punctuation checks

    # punctuation after "the"
    m = re.finditer(r"(^|[\p{Z}\p{P}])the\p{P}", s)
    for item in m:
        report2(pn, item, "punctuation after 'the'")
    # date format October 8,1948
    m = re.finditer(r",1\p{N}\p{N}\p{N}", s)
    for item in m:
        report2(pn, item, "suspect date punctuation")
    # special cases of contiguous punctuation
    s2 = s.replace("etc.,", "")  # allow "etc.,"
    m = re.finditer(r"(,\.)|(\.,)|(,,)|([^\.]\.\.([^\.]|$))", s2)
    for item in m:
        report2(pn, item, "suspect contiguous punctuation")
    # collapsed punctuation
    # m = re.finditer(r"[\p{L}|\p{N}]\p{Z}?[\.:;,][\p{L}|\p{N}]", s)
    m = re.finditer(r"(\p{L})[\.:;,](\p{L})", s)
    for item in m:
        if not (item.group(1).isnumeric() and item.group(2).isnumeric()):
            report2(pn, item, "incorrectly spaced punctuation")

    # -------------------------------------------------------------------------
    # mixed case in word (3 checks)

    # first upper followed by upper then lower somewhere in word
    # start of line or space or punctuation
    # two upper case in a row, optionally other characters, then
    # a lower case letter before the word ends
    # m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Lu}\p{Lu}\p{L}?\p{Ll}', s)
    # for item in m:
    #    report2(pn, item, "mixed case in word")
    # first upper followed by lower then upper somewhere in word
    # m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Lu}[^\p{Z}\p{P}]*?\p{Ll}\p{Lu}', s)
    # for item in m:
    #    report2(pn, item, "mixed case in word")
    # first lower followed by upper anywhere in word
    # m = re.finditer(r'(^|[\p{Z}\p{P}])\p{Ll}[^\p{Z}\p{P}]*?\p{Lu}', s)
    # for item in m:
    #    report2(pn, item, "mixed case in word")

    # two upper followed by lower somewhere in word (HAPpY)
    m = re.finditer(
        r"(^|[\p{Z}\p{P}])(\p{Lu}\p{Lu}\p{L}*\p{Ll}\p{L}*)([\p{Z}\p{P}]|$)", s
    )
    for item in m:
        if not item.group(2) in allowed_mixed_case:
            report2(pn, item, "mixed case in word")

    # first upper followed by lower then upper somewhere in word (HapPy)
    m = re.finditer(
        r"(^|[\p{Z}\p{P}])(\p{Lu}\p{Ll}\p{L}*\p{Lu}\p{L}*)([\p{Z}\p{P}]|$)", s
    )
    for item in m:
        if not item.group(2) in allowed_mixed_case:
            report2(pn, item, "mixed case in word")

    # first lower followed by upper anywhere in word
    m = re.finditer(r"(^|[\p{Z}\p{P}])(\p{Ll}\p{L}*\p{Lu}\p{L}*)([\p{Z}\p{P}]|$)", s)
    for item in m:
        if not item.group(2) in allowed_mixed_case:
            report2(pn, item, "mixed case in word")

    # -------------------------------------------------------------------------
    # rare to end word
    m = re.finditer(
        r"(cb|gb|pb|sb|tb|wh|fr|br|qu|tw|gl|fl|sw|gr|sl|cl|iy)($|[\p{Z}\p{P}])", s
    )
    for item in m:
        report2(pn, item, "unusual characters ending word")

    # rare to start word
    m = re.finditer(r"(^|[\p{Z}\p{P}])(hr|hl|cb|sb|tb|wb|tl|tn|rn|lt|tj)", s)
    for item in m:
        report2(pn, item, "unusual characters starting word")

    # single character paragraph
    m = re.finditer(r"^.$", s)
    for item in m:
        report2(pn, item, "single character paragraph")

    # hyphenation adjacent to space
    m = re.finditer(r"\p{L}(-\s+|\s+-)\p{L}", s)
    for item in m:
        report2(pn, item, "hyphenation adjacent to space")

    # exclamation point suspect: “You should runI”
    m = re.finditer(r"I”", s)
    for item in m:
        report2(pn, item, "exclamation point suspect")

    # unexpected period: "this is. not a easy task"
    # do not report common abbreviations that appear with a period,
    # such as "50 per cent. per annum"
    m = re.finditer(r"(\p{L}+)\.\p{Z}\p{Ll}", s)
    for item in m:
        if not item.group(1) in [
            "cent",
            "cents",
            "viz",
            "vol",
            "vols",
            "vid",
            "ed",
            "al",
            "etc",
            "op",
            "cit",
            "deg",
            "min",
            "chap",
            "oz",
            "mme",
            "mlle",
            "mssrs",
            "gym",
        ]:
            report2(pn, item, "unexpected period")

    # disjointed contraction
    m = re.finditer(r"\p{Z}’(m|ve|ll|t)($|[\p{Z}\p{P}])", s)
    for item in m:
        report2(pn, item, "disjointed contraction")

    # suspected HTML tag
    m = re.finditer(r"<[^>]+>", s)
    for item in m:
        report2(pn, item, "suspected HTML tag")

    # quote direction (by context)
    m = re.finditer(
        r"([\.,;!?’‘]+[‘“])|([A-Za-z]+[“])|([A-LN-Za-z]+[‘])|(“ )|( ”)|(‘s\s)", s
    )
    for item in m:
        report2(pn, item, "quote direction (by context)")

    # standalone 0 or 1
    m = re.finditer(r"(^|[\p{Z}\p{P}])([01])($|[\p{Z}\p{P}])", s)
    for item in m:
        if not (
            item.group(2) == "1" and item.group(3) == ","
        ):  # allow 1,000 or Oct. 1,
            report2(pn, item, "standalone 0 or 1")

    # mixed numbers/letters in word
    m = re.finditer(
        r"(^|[\p{Z}\p{P}])([^\p{Z}\p{P}]*(\p{L}\p{N}|\p{N}\p{L})[^\p{Z}\p{P}]*)($|[\p{Z}\p{P}])",
        s,
    )
    for item in m:
        theword = item.group(2)
        if not re.match(r"\d+(st|nd|rd|th)", theword):
            report2(pn, item, f"mixed numbers/letters in word {item.group(2)}")

    # period/comma suspect
    # period, space, lower-case letter
    # meant to catch "You never know. inevitably, where you will find her."
    m = re.finditer(r"\. \p{Ll}", s)
    for item in m:
        report2(pn, item, f"period/comma suspect")
    # comma, space, capitalized word that's also in wordlist in lower-case
    # meant to catch "He went to the farm, Then he saw her."
    m = re.finditer(r"\, (\p{Lu}\p{L}+)", s)
    for item in m:
        # allow "If you say so, Morgan." using proper names list
        theword = item.group(1).lower()
        if not item.group(1) in proper_names and theword in theWordlist:
            report2(pn, item, f"period/comma suspect")

    # Blank Page placeholder
    m = re.finditer(r"blank page", s, re.IGNORECASE)
    for item in m:
        report2(pn, item, "Blank Page placeholder")

    # hyphenation and dashes

    # mixed hyphen-dash
    # note, will catch the common construction: space+en-dash+space
    m = re.finditer(r"(\p{Pd})(\p{Pd})", s, re.IGNORECASE)
    for item in m:
        if item.group(1) != item.group(2):
            report2(pn, item, "mixed hyphen-dash")
    # mixed hyphen-dash
    m = re.finditer(r"(\p{Pd})", s, re.IGNORECASE)
    for item in m:
        if item.group(1) not in "—-–":  # em-, hyphen, en-dash
            report2(pn, item, "potentially unsafe ePub dash")
    # spaced dash
    m = re.finditer(r"\p{Z}\p{Pd}", s, re.IGNORECASE)
    for item in m:
        report2(pn, item, "spaced dash")
    m = re.finditer(r"\p{Pd}\p{Z}", s, re.IGNORECASE)
    for item in m:
        report2(pn, item, "spaced dash")

    # unusual characters
    # allow special pattern for DP-style thought break
    if quotetype == "straight":
        m = re.finditer(r'[^A-Za-z0-9 \.,:;"\'\-\?—!\(\)_\[\]]', s)
    else:
        m = re.finditer(r"[^A-Za-z0-9 \.,:;“”‘’\-\?—!\(\)_\[\]]", s)
    for item in m:
        if re.match("^\s+\*\s+\*\s+\*\s+\*\s+\*", s):  # allow DP thought break
            continue
        report2(pn, item, f"unusual character {unicodedata.name(item.group(0))}")

    NOCOMMAPATTERN = "(^|[\p{Z}\p{P}])(the,|it’s,|their,|an,|mrs,|a,|our,\
    |that’s,|its,|whose,|every,|i’ll,|your,|my,|mr,|mrs,|mss,|mssrs,|ft,|\
    pm,|st,|dr,|rd,|pp,|cf,|jr,|sr,|vs,|lb,|lbs,|ltd,|i'm,|during,|let,|\
    toward,|among,)"

    # commas not expected after certain words
    m = re.finditer(NOCOMMAPATTERN, s)
    for item in m:
        report2(pn, item, "unexpected comma after word")

    NOPERIODPATTERN = "(^|[\p{Z}\p{P}])(every\.|i’m\.|during\.|that’s\.\
    |their\.|your\.|our\.|my\.|or\.|and\.|but\.|as\.|if\.|the\.|its\.\
    |it’s\.|until\.|than\.|whether\.|i’ll\.|whose\.|who\.|because\.|when\.\
    |let\.|till\.|very\.|an\.|among\.|those\.|into\.|whom\.|having\.|thence\.)"

    # periods not expected after certain words
    m = re.finditer(NOPERIODPATTERN, s)
    for item in m:
        report2(pn, item, "unexpected period after word")

    # paragraph ends with unusal character
    m = re.finditer(r"[^.”\?!\*:]$", s)
    for item in m:
        report2(pn, item, "paragraph ends with unusual character")

    # inconsistent quotation marks
    if count_straight < count_curly:
        m = re.finditer(r'[\'"]', s)
    else:
        m = re.finditer(r"[‘’“”]", s)
    for item in m:
        report2(pn, item, "inconsistent quote marks")

    # ellipsis checks
    m = re.finditer(r"(\.\.\.\.)[^\p{Z}]", s)
    for item in m:
        report2(pn, item, "suspect ellipsis check")
    m = re.finditer(r"\P{Z}(\.\.\.)\p{Z}", s)
    for item in m:
        report2(pn, item, "suspect ellipsis check")
    m = re.finditer(r"\p{Z}(\.\.\.)\P{Z}", s)
    for item in m:
        report2(pn, item, "suspect ellipsis check")
    m = re.finditer(r"\.\.\.\.\.", s)
    for item in m:
        report2(pn, item, "suspect ellipsis check")

# run quote tests, paragraph at-a-time
# use a small FSM to deal with punctuation.
# only works if smart quotes.

any_reported = False
for pn, ap in enumerate(paras.parg):
    s = ap.ptext  # get a paragraph as one string
    if count_curly > 0 and count_straight == 0:
        # hide all known apostrophes
        s2 = re.sub(r"(\p{L})’(\p{L})", r"\1X\2", s)
        stack = []
        reported = False
        theline = paras.startline(pn)
        for c in s2:  # iterate character at a time
            if c == "“":  # open double quote
                # ok to push if empty or there isn't one there now
                if len(stack) == 0 or stack[-1] != "“":
                    stack.append("“")
                else:
                    if not any_reported:
                        report3("quotation mark checks", True)
                        any_reported = True
                    report3(f"   {theline+1}: {wb[theline]}")
                    reported = True
                    break
            if c == "”":  # close double quote
                # ok to pop if there is an open double quote available
                if len(stack) > 0 and stack[-1] == "“":
                    stack.pop()
                else:
                    if not any_reported:
                        report3("quotation mark checks", True)
                        any_reported = True
                    report3(f"   {theline+1}: {wb[theline]}")
                    reported = True
                    break
            if c == "‘":  # open single quote
                # ok to push if last push was ODQ
                if len(stack) > 0 and stack[-1] == "“":
                    stack.append("‘")
                else:
                    if not any_reported:
                        report3("quotation mark checks", True)
                        any_reported = True
                    report3(f"   {theline+1}: {wb[theline]}")
                    reported = True
                    break
            if c == "’":  # (maybe) close single quote
                # ok to pop if there is an open single quote available
                if len(stack) > 0 and stack[-1] == "‘":
                    stack.pop()
                else:
                    # cannot reliably identify CSQ from apostrophe
                    pass

    # we are at the end of a paragraph. report if anythging on stack
    if not reported and len(stack) > 0:
        if not any_reported:
            report3("")
            report3(
                "quotation mark checks; paragraphs starting at line indicated", True
            )
            any_reported = True
        report3(f"   {theline+1}: {wb[theline]}")

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
    if (
        i != 0
        and len(wb[i - 1]) > len(wb[i])
        and i != len(wb) - 1
        and len(wb[i]) < len(wb[i + 1])
        and len(wb[i - 1]) > 55
    ):
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


# check: common he/be, hut/but and had/bad checks

HADBADPATTERN = (
    "\bi bad\b|\byou bad\b|\bhe bad\b|\bshe bad\b|\bthey bad\b|\ba had\b|\bthe had\b"
)
HUTBUTPATTERN = "(, hut\P{L})|(; hut\P{L})"
HEBEPATTERN = "\bto he\b|\bis be\b|\bbe is\b|\bwas be\b|\bbe would\b|\bbe could\b"

for pn, ap in enumerate(paras.parg):  # paragraph at a time
    s = ap.ptext  # get a paragraph as one string

    m = re.finditer(HADBADPATTERN, s)
    for item in m:
        report2(pn, item, "had/bad suspect")
    m = re.finditer(HUTBUTPATTERN, s)
    for item in m:
        report2(pn, item, "hut/but suspect")
    m = re.finditer(HEBEPATTERN, s)
    for item in m:
        report2(pn, item, "he/be suspect")

# save results to specified file

with open(args["outfile"], "w") as f:
    f.write("<pre>")
    f.write("pgtext run report\n")
    f.write(f"run started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("source file: {}\n".format(os.path.basename(args["infile"])))
    f.write(
        f"<span style='color:silver'>close this window to return to the UWB.</span>\n"
    )
    f.write("\n")

    for line in reports3:
        f.write(f"{line}\n")

    # these are the ones recorded with report2
    # reports is a map. convert to list and sort
    rlist = sorted(list(reports))
    for k in rlist:
        f.write(
            f"<div style='padding-left:0.6em; margin-top:1em; background-color:papayawhip;'>{k}</div>"
        )
        count = 0
        limit = 4
        if args["verbose"]:
            limit = 100
        for line in reports[k]:
            if count < limit:
                f.write(f"   {line}\n")
            if count == limit:
                remain = len(reports[k]) - limit
                f.write(f"   ... {remain} more\n")
            count += 1
    f.write("</pre>")
