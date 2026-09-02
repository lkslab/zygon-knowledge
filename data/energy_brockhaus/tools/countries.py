#!/usr/bin/env python3
"""The country universe -- single source of truth for every tool here.

`WORLD` is the ISO-3166-1 alpha-2 set. The brockhaus's coverage map, worklist,
and bloc-membership check all resolve against it, so "which countries should
exist" is answered in exactly one place. Codes that are not countries (bloc
aggregates, the all-countries wildcard) live in NONCOUNTRY and are excluded
from coverage denominators -- an EU-level target is not a country's coverage.
"""

WORLD = (
    "AD AE AF AG AL AM AO AR AT AU AZ BA BB BD BE BF BG BH BI BJ BN BO BR BS "
    "BT BW BY BZ CA CD CF CG CH CI CL CM CN CO CR CU CV CY CZ DE DJ DK DM DO DZ "
    "EC EE EG ER ES ET FI FJ FM FR GA GB GD GE GH GM GN GQ GR GT GW GY HN HR HT "
    "HU ID IE IL IN IQ IR IS IT JM JO JP KE KG KH KI KM KN KP KR KW KZ LA LB LC "
    "LI LK LR LS LT LU LV LY MA MC MD ME MG MH MK ML MM MN MR MT MU MV MW MX MY "
    "MZ NA NE NG NI NL NO NP NR NZ OM PA PE PG PH PK PL PT PW PY QA RO RS RU RW "
    "SA SB SC SD SE SG SI SK SL SM SN SO SR SS ST SV SY SZ TD TG TH TJ TL TM TN "
    "TR TT TV TW TZ UA UG US UY UZ VA VC VE VN VU WS YE ZA ZM ZW"
    # Inhabited territories and special administrative regions. They have their
    # own energy systems, policies and ISO-2 codes, so they are countries for
    # coverage purposes even where they are not sovereign states. HK and GL were
    # already carrying rows while being absent from this list, which made the
    # bloc-membership check reject 48 legitimate records.
    " HK MO GL FO PR PS NC PF AW CW SX GI IM JE GG BM KY VG VI GU AS MP"
    " RE MQ GP GF YT EH KP"
).split()

WORLD_SET = set(WORLD)

# The wildcard `*` means "applies to every party" (e.g. a Paris Agreement row).
WILDCARD = "*"

# Populated from blocs.csv at runtime; this is the static fallback for tools
# that must work before blocs.csv is read.
NONCOUNTRY = {"EU", "EU27", WILDCARD, ""}


def is_country(code):
    return code in WORLD_SET
