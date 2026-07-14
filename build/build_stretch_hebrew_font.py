"""Build kashida-capable Hebrew fonts from open-source bases. Each entry in
CONFIGS specifies a source font (e.g. Frank Ruhl Libre, Keter Aram Tsova)
and per-letter geometric zones (bar/arm/leg/box ranges, x_cutoff). For each
of the six scribally-stretchable letters (ד ה ל ם ר ת), we derive 6 widened
variants and wire them via GSUB ligatures so `letter + N × U+05C6` produces
`letter_stretched_N`.

The framework is config-driven so adding a new font is just adding one
CONFIGS entry. Per-font tuning is required because each font's glyphs sit
at different coordinates (Frank Ruhl uses UPM=1000, Keter Aram Tsova
UPM=2048, Heebo UPM=1000 with different stroke heights, etc.).

License notes:
  - SIL OFL fonts (Frank Ruhl Libre, David Libre, Heebo, Noto, ...) — must
    be renamed (per OFL §3) when modified. Output stays under SIL OFL.
  - GPL fonts (Culmus: Keter Aram Tsova, Keter YG, Taamey Frank, Shofar,
    Ktav Yad CLM) — derivatives must remain GPL. Distribute output as GPL.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pathops
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

FONTS_DIR = Path(__file__).resolve().parents[1] / "web" / "public" / "fonts"

# Our stretch trigger. Originally U+E010 (PUA) — but browsers segment text
# into script runs BEFORE shaping, and PUA has script=Unknown/Zzzz. That
# means lam+E010 lands in two separate shaping runs and the GSUB `liga`
# lookup can never match across them. Use U+05C6 (Hebrew Punctuation Nun
# Hafukha) instead: script=Hebrew → stays in the Hebrew run, so the
# ligature substitution fires. It's non-combining (gc=Po) and extremely
# rare in real text (only appears a few times in Torah — Numbers 10:35-36).
#
# For SYRIAC fonts, U+05C6 has script=Hebrew so HarfBuzz splits the run at
# every trigger — same problem as PUA. Syriac fonts override this to
# U+0640 (Arabic tatweel), which has script=Common and stays in whatever
# run it's placed in. See `stretch_codepoint` on NOTO_SANS_SYRIAC + Nohadra.
STRETCH_CODEPOINT = 0x05C6
STRETCH_GLYPH = f"uni{STRETCH_CODEPOINT:04X}"
MAX_LEVELS = 16        # number of stretch variants per letter

# ---------------------------------------------------------------------------
# Per-font configurations. STEP is in font units; scale with the font's UPM
# (Frank Ruhl uses 1000, Keter Aram Tsova 2048, ...). The visual stretch
# at a given font-size is `step / upem * font-size-px` per level.
# ---------------------------------------------------------------------------

# `alias_codepoints` is a list of Unicode codepoints (Hebrew Presentation
# Forms) that the build resolves to the font's actual glyph name via cmap.
# This works across fonts that use different naming conventions (fontTools'
# `uniFB33` vs Culmus's `daleddagesh`).
ALIAS_DAGESH = {
    "dalet":    [0xFB33],   # ד + dagesh
    "he":       [0xFB34],   # ה + mapiq
    "lamed":    [0xFB3C],   # ל + dagesh (rare)
    "resh":     [0xFB48],   # ר + dagesh (rare)
    "tav":      [0xFB4A],   # ת + dagesh
}

# Arabic combining marks to import into every Hebrew stretch font: shaddah,
# three tanwin marks, sukun. Pulled from Amiri-Regular.ttf and scaled to
# the target font's UPM. Lets users place these marks over any Hebrew
# letter (academic / comparative use case).
ARABIC_MARKS = [
    0x0651,  # shadda (gemination)
    0x064B, 0x064C, 0x064D,  # fathatan, dammatan, kasratan
    0x0652,  # sukun
    0x064E, 0x064F, 0x0650,  # fatha, damma, kasra (added for full Judeo-Arabic vocalization)
    0x0653,  # maddah
    0x0670,  # dagger alif
]

# Combining diaeresis (U+0308): two dots above. Used for Hebrew Heh + dots
# to visually represent Arabic ة (taa marbuta), among other comparative uses.
# Amiri's diaeresis is positioned for Latin x-heights, too low for Hebrew —
# we design our own glyph instead.
DIAERESIS_CP = 0x0308

FRANK_RUHL = {
    "id": "frank-ruhl",
    "source": "FrankRuhlLibre.ttf",
    "output": "SemiticStretchHebrew.ttf",
    "family": "Semitic Stretch Hebrew",
    "postscript": "SemiticStretchHebrew",
    "internal_id": "SemiticSearch-SemiticStretchHebrew-2.0",
    "step": 150,
    "import_marks": ARABIC_MARKS,
    # Mono mode: after the leftward stretch shift, translate the whole glyph
    # rightward by the same total_shift. Result — the letter's LEFT edge
    # sits at its natural cursor-relative position (no overlap into the
    # preceding letter), and the widening extends RIGHTWARD into the space
    # the grown advance created. Fixes "hey too close to shin" and
    # "final mem too far" from the shift-mode baseline. Aesthetic trade:
    # the bar visually extends rightward from natural-left rather than
    # leftward from natural-right.
    "lsb_mode": "mono",
    "letters": {
        # dalet/resh/lamed all opt into overflow chains: kashidas beyond
        # MAX_LEVELS substitute into bar segments that tile leftward of the
        # max pre-baked variant, with a rounded corner cap on the leftmost
        # segment matching the natural bar's left-edge design.
        # chain_bar_top=546: natural bar's flat top is at y=546, but the
        # upper-left ear/serif peaks at y=586. Without this override,
        # seg_bar_top defaults to 586 (the body's max y) and the bar_segment
        # tile is built 40 units taller than the natural body's bar —
        # creating a visible height mismatch (chain extension towers above
        # natural body). Setting chain_bar_top to the actual flat top
        # makes the chain bar a uniform strip.
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 440, "bar_top": 620, "x_cutoff": 290,
                 "chain_bar_top": 546,
                 "alias_codepoints": ALIAS_DAGESH["dalet"], "overflow": True},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 440, "bar_top": 620, "leg_max_y": 400, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 440, "bar_top": 573, "arm_min_y": 573, "x_cutoff": 300,
                 "alias_codepoints": ALIAS_DAGESH["lamed"], "overflow": True, "arm_top_y": 793},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 300},
        # Same ear-peak issue as dalet — bar flat top at y=546, ear at y=586.
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 440, "bar_top": 620, "x_cutoff": 300,
                 "chain_bar_top": 546,
                 "alias_codepoints": ALIAS_DAGESH["resh"], "overflow": True},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 440, "bar_top": 620, "leg_max_y": 440, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Keter Aram Tsova (Culmus, GPL) — UPM=2048, so all values ~2× Frank Ruhl's.
# Initial values from coordinate inspection; will be refined visually.
KETER_ARAM_TSOVA = {
    "id": "keter-aram-tsova",
    "source": "KeterAramTsova.ttf",
    "output": "SemiticStretchKeterAramTsova.ttf",
    "family": "Semitic Stretch Keter Aram Tsova",
    "postscript": "SemiticStretchKeterAramTsova",
    "internal_id": "SemiticSearch-SemiticStretchKeterAramTsova-1.0",
    "step": 300,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        # dalet: single-contour topology (one closed outline that traces
        # outside + inside). bar_bottom=650 lets the underside (y=699)
        # and the left ear's lower curve (y≥655) shift together with the
        # top, so the bar extends as a unit. x_cutoff=500 anchors pt 46
        # at (509, 713) — the corner where the descender's interior left
        # wall meets the bar's underside — preventing it from shifting
        # leftward by `shift` and distorting the inner cavity.
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 650, "bar_top": 1250, "x_cutoff": 500,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        # he: leg_max_y=800 captures the left leg + underside; bar_bottom
        # set to 800 too so the gap between leg/bar zones (which left the
        # left ear y=855 stranded) closes. x_cutoff=600 anchors the inner
        # right edge (pts 11-15 at x=665-681) — it joins the right leg's
        # interior, which must stay put. Earlier 700 dragged the inner
        # edge leftward and broke the underside/right-leg connection.
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 800, "bar_top": 1250, "leg_max_y": 800, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        # Lamed: body wide y=675-1227 (right reaches 784, narrowing to
        # 666 in the joint band), pure arm y>1227 (x<196).
        # arm_min_y=1227 keeps the body's slight slope from getting
        # sliced — earlier arm_min_y=1089 sliced off body-right points
        # at y=1100ish that should have stayed anchored.
        # chain_bar_top=1047: natural bar flat top is at y=1047, but the
        # body has a right-shoulder peak at y=1092 that pulls seg_bar_top
        # 45 units too high. Without the override the bar_segment tile
        # was 45 units taller than the natural bar, producing a visible
        # step where the chain met the body.
        # chain_bar_bottom=766: bar_bottom=675 captures the wall for stretch
        # purposes, but the natural bar's flat bottom sits at y=766 (sloping
        # to 792 at the right). Without the override the bar tile extended
        # 91 units below the body's bar — the "tab below the top line."
        # x_cutoff=290 (was 400): keeps the on-curve at (299, 1047) anchored.
        # Previously it translated, while the off-curve at (469, 1047) and
        # the shoulder peak at (666, 1092) stayed put — creating a wide
        # gradual rise from y=1047 to y=1092 across the entire chain
        # extension's bar top instead of a tight curve at the body.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 675, "bar_top": 1227, "arm_min_y": 1227, "x_cutoff": 290,
                 "chain_bar_top": 1047, "chain_bar_bottom": 766,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 600},
        # resh: underside at y=720-784. bar_bottom=720 brings underside
        # into the stretch zone so the bar widens uniformly (top + bottom).
        # x_cutoff=600 anchors the descender's inner left wall (pt 53 at
        # x=607) so it stays connected to the right leg.
        # underside_y_max=800 + underside_x_min=150 flattens the arch in
        # the underside (pts 54-58 dip to y=784) into a clean line from
        # the right anchor (607, 720) to the leftmost shifted point at
        # y=745. underside_x_min excludes the left ear (pts 0-4 at x<100)
        # which lives in the same y range but should keep its curved shape.
        # chain_bar_top=1070: natural bar flat top is at y=1070, but the
        # upper-left ear peaks at y=1213 — a 143-unit gap. Without this
        # override the bar_segment tile towered above the natural bar.
        # chain_bar_bottom=744: the underside-flatten output is a slope from
        # y=720 (right) to y=745 (left). Setting tile bottom to 744 matches
        # the start glyph's leftmost bar bottom at the chain seam.
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 720, "bar_top": 1250, "x_cutoff": 600,
                 "chain_bar_top": 1070, "chain_bar_bottom": 744,
                 "underside_y_max": 800, "underside_x_min": 150,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 900, "bar_top": 1250, "leg_max_y": 900, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Shmulik CLM (Culmus fancy, GPL) — UPM=2048, distinctive serif Hebrew
# inspired by hand-set type. Top bars sit around y=900-1238.
SHMULIK = {
    "id": "shmulik",
    "source": "ShmulikCLM.ttf",
    "output": "SemiticStretchShmulikCLM.ttf",
    "family": "Semitic Stretch Shmulik CLM",
    "postscript": "SemiticStretchShmulikCLM",
    "internal_id": "SemiticSearch-SemiticStretchShmulikCLM-1.0",
    "step": 300,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        # Shmulik's body bars sit at y=1050 with serifs reaching y=1186.
        # Letters are wide (1280-1600 advance), so x_cutoffs are bigger
        # than narrower fonts — they anchor the actual right descender/leg
        # which sits near x=1000+.
        # bar_bottom=810 (not 900): the body's natural bar+wall combined
        # region runs y=810 (wall bottom) to y=1050 (bar top). With
        # bar_bottom=810 the stretch zone includes the wall — both bar AND
        # wall translate as a unit, so variants/chains have a uniform full
        # thickness from variant.xMin all the way to the body. With 900
        # only the bar would translate while the wall stayed put, yielding
        # a visible wedge that tapers from full thickness at the body to
        # bar-only thickness at the chain seam.
        # chain_bar_top=1050: caps the chain bar tile (and bar_clip_x_left
        # detection) at the bar's natural flat top, excluding the kotz
        # region (extends up to y=1238). The kotz is captured in the cap
        # region of the tail glyph, not in the bar rectangle.
        # x_cutoff=800 (was 900): the natural top has off-curves at (845, 1050)
        # and (880, 1065) that bridge the bar's flat-top on-curve at (795, 1050)
        # to the kotz peak on-curve at (919, 1104). With cutoff=900 those
        # off-curves translated leftward while the kotz on-curve stayed put —
        # creating a 4900-wide degenerate bezier that ramped y=1050→1104 across
        # the entire chain extension. cutoff=800 keeps both off-curves anchored
        # so the rise stays tight at the natural kotz boundary. Same logic at
        # the bottom-right corner: (824, 810) off-curve now stays anchored.
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 810, "bar_top": 1250, "x_cutoff": 800,
                 "chain_bar_top": 1050,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        # he: x_cutoff was 1100 — but Shmulik's right floating leg lives at
        # x=1005-1239, so 1100 sliced THROUGH it (left half x<1100 shifted,
        # right half x>=1100 stayed → tore the leg). Lowering to 900 keeps
        # the entire right leg anchored (x>900) while the bar's left edge
        # at x=114 still shifts.
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 900, "bar_top": 1250, "leg_max_y": 900, "x_cutoff": 900,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        # Lamed: body wide y=697-1124 (right reaches 1126), pure arm
        # y>1240 (x<393). arm_min_y=1240 keeps the body's TOP-RIGHT
        # (x=1126 at y up to 1124) anchored by x-split — earlier
        # arm_min_y=981 sliced it off because the body has a slight
        # slope and points just above 981 with x=1126 got rigidly
        # translated leftward.
        # chain_bar_bottom=812: bar_bottom=700 captures the descender area
        # for stretch translation, but the natural body's bar bottom sits
        # at y=812 (where the body's left edge meets the arm root). Without
        # the override, the bar tile extends 112 units below the natural
        # body's bar — visible as a tab hanging down at every chain seam.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 700, "bar_top": 1240, "arm_min_y": 1240, "x_cutoff": 500,
                 "chain_bar_bottom": 812,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        # finalmem: was x_cutoff=1100 — but the right corner serifs
        # have points at x≈1100-1300, and the inner contour ends at
        # x=1039. Lowering to 800 anchors all right-side serif features.
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 800},
        # bar_bottom=810: same wall-translation rationale as dalet.
        # x_cutoff=730 (was 900): the natural bottom has off-curves at (777, 811)
        # and (753, 811) that translated under cutoff=900, while the wall-curl
        # off-curves at (811, 806), (821, 803), (838, 787) etc. stayed put
        # (y<bar_bottom). The result was a ~13-unit dip in the chain extension's
        # bottom edge over ~4800 units. cutoff=730 keeps the bar-bottom off-curves
        # anchored at their natural positions so the wall transition stays tight.
        # Top transition is unaffected (already clean — natural off-curves at
        # x=1020, 1064 sit past any reasonable cutoff).
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 810, "bar_top": 1250, "x_cutoff": 730,
                 "chain_bar_top": 1050,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        # tav: was x_cutoff=1200 but Shmulik's right descender sits at
        # x=1163-1595 with internal points at x≈1163; cutoff=1200 split
        # it. Lowered to 1000 — right descender (all x>1100) now stays
        # anchored, plus left leg + bar's left half still translate.
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 900, "bar_top": 1250, "leg_max_y": 900, "x_cutoff": 1000,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Hillel (Culmus fancy, GPL) — UPM=1000, modern Israeli serif. No
# composed-dagesh glyphs, so aliases unused (IgnoreMarks lookupflag
# suffices to skip the dagesh combining mark).
HILLEL = {
    "id": "hillel",
    "source": "HillelCLM-Medium.ttf",
    "output": "SemiticStretchHillelCLM.ttf",
    "family": "Semitic Stretch Hillel CLM",
    "postscript": "SemiticStretchHillelCLM",
    "internal_id": "SemiticSearch-SemiticStretchHillelCLM-1.0",
    # 150 instead of 130 — keeps the stretch ratio consistent at ~0.15em
    # per level across all UPM=1000 fonts. Was 130 because Hillel renders
    # smaller; normalizing makes side-by-side comparisons fair.
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 350, "bar_top": 520, "x_cutoff": 280},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 350, "bar_top": 520, "leg_max_y": 320, "x_cutoff": 280},
        # Lamed: body wide y=403-520 (x to 456), pure arm y>520 (x<140).
        # x_cutoff=200 anchors body's right edge cleanly.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 400, "bar_top": 520, "arm_min_y": 520, "x_cutoff": 200},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 280},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 350, "bar_top": 520, "x_cutoff": 250},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 350, "bar_top": 520, "leg_max_y": 350, "x_cutoff": 320},
    },
}

# Gladia (Culmus fancy, GPL) — UPM=1000, bold display Hebrew. No composed
# dagesh forms, same as Hillel.
GLADIA = {
    "id": "gladia",
    "source": "GladiaCLM-Bold.ttf",
    "output": "SemiticStretchGladiaCLM.ttf",
    "family": "Semitic Stretch Gladia CLM",
    "postscript": "SemiticStretchGladiaCLM",
    "internal_id": "SemiticSearch-SemiticStretchGladiaCLM-1.0",
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 450, "bar_top": 620, "x_cutoff": 380},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 450, "bar_top": 620, "leg_max_y": 400, "x_cutoff": 380},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 450, "bar_top": 600, "arm_min_y": 600, "x_cutoff": 300},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 350},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 450, "bar_top": 620, "x_cutoff": 350},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 450, "bar_top": 620, "leg_max_y": 450, "x_cutoff": 400},
    },
}

# --- More fonts requested from opensiddur.org/help/fonts/ ---

NOTO_SANS_HEBREW = {
    "id": "noto-sans-hebrew",
    "source": "NotoSansHebrew.ttf",
    "output": "SemiticStretchNotoSansHebrew.ttf",
    "family": "Semitic Stretch Noto Sans Hebrew",
    "postscript": "SemiticStretchNotoSansHebrew",
    "internal_id": "SemiticSearch-SemiticStretchNotoSansHebrew-1.0",
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 440, "bar_top": 620, "x_cutoff": 300,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 440, "bar_top": 620, "leg_max_y": 400, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 440, "bar_top": 600, "arm_min_y": 600, "x_cutoff": 280,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 350},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 440, "bar_top": 620, "x_cutoff": 280,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 440, "bar_top": 620, "leg_max_y": 440, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

NOTO_SERIF_HEBREW = {
    "id": "noto-serif-hebrew",
    "source": "NotoSerifHebrew.ttf",
    "output": "SemiticStretchNotoSerifHebrew.ttf",
    "family": "Semitic Stretch Noto Serif Hebrew",
    "postscript": "SemiticStretchNotoSerifHebrew",
    "internal_id": "SemiticSearch-SemiticStretchNotoSerifHebrew-1.0",
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 480, "bar_top": 670, "x_cutoff": 300,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 480, "bar_top": 670, "leg_max_y": 440, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 480, "bar_top": 650, "arm_min_y": 650, "x_cutoff": 300,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 350},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 480, "bar_top": 670, "x_cutoff": 280,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 480, "bar_top": 670, "leg_max_y": 480, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

SHOFAR = {
    "id": "shofar",
    "source": "ShofarRegular.ttf",
    "output": "SemiticStretchShofar.ttf",
    "family": "Semitic Stretch Shofar",
    "postscript": "SemiticStretchShofar",
    "internal_id": "SemiticSearch-SemiticStretchShofar-1.0",
    "step": 300,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 900, "bar_top": 1250, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 900, "bar_top": 1250, "leg_max_y": 800, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 900, "bar_top": 1200, "arm_min_y": 1200, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 600},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 900, "bar_top": 1250, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 900, "bar_top": 1250, "leg_max_y": 900, "x_cutoff": 800,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# FreeMono (GNU FreeFont, GPL) — monospace with Hebrew. Step = 600 (the
# font's mono cell width) so each stretch level adds exactly one full
# character cell. Preserves monospacing: a stretched letter occupies
# (1 + n) cells, keeping all column alignments intact.
FREE_MONO = {
    "id": "free-mono",
    "source": "FreeMono.ttf",
    "output": "SemiticStretchFreeMono.ttf",
    "family": "Semitic Stretch FreeMono",
    "postscript": "SemiticStretchFreeMono",
    "internal_id": "SemiticSearch-SemiticStretchFreeMono-1.0",
    "step": 600,
    # Mono cell width = 600. "mono" mode rewrites the glyph so the body
    # sits in the RIGHTMOST of the (1+N) cells (next to the previous
    # letter under RTL), with the kashida bar extending LEFTWARD into the
    # additional cells. Under "natural" the body would stay in the
    # leftmost cell, leaving a huge gap to the next letter on the right.
    "lsb_mode": "mono",
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 350, "bar_top": 500, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 350, "bar_top": 500, "leg_max_y": 320, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 350, "bar_top": 480, "arm_min_y": 480, "x_cutoff": 300,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 350},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 350, "bar_top": 500, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 350, "bar_top": 500, "leg_max_y": 350, "x_cutoff": 400,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Nachlieli CLM (Culmus, GPL) — UPM=1090, light/airy serif Hebrew.
NACHLIELI = {
    "id": "nachlieli",
    "source": "NachlieliCLM-Light.ttf",
    "output": "SemiticStretchNachlieliCLM.ttf",
    "family": "Semitic Stretch Nachlieli CLM",
    "postscript": "SemiticStretchNachlieliCLM",
    "internal_id": "SemiticSearch-SemiticStretchNachlieliCLM-1.0",
    "step": 165,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 420, "bar_top": 620, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 420, "bar_top": 620, "leg_max_y": 380, "x_cutoff": 380,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 420, "bar_top": 600, "arm_min_y": 600, "x_cutoff": 320,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 380},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 420, "bar_top": 620, "x_cutoff": 320,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 420, "bar_top": 620, "leg_max_y": 430, "x_cutoff": 430,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Miriam Mono CLM (Culmus, GPL) — monospace serif Hebrew. UPM=1000,
# mono cell width=600. Step = 600 to match — preserves monospacing.
MIRIAM_MONO = {
    "id": "miriam-mono",
    "source": "MiriamMonoCLM-Book.ttf",
    "output": "SemiticStretchMiriamMonoCLM.ttf",
    "family": "Semitic Stretch Miriam Mono CLM",
    "postscript": "SemiticStretchMiriamMonoCLM",
    "internal_id": "SemiticSearch-SemiticStretchMiriamMonoCLM-1.0",
    "step": 600,
    "lsb_mode": "mono",  # see FreeMono note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 350, "bar_top": 500, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 350, "bar_top": 500, "leg_max_y": 320, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 350, "bar_top": 480, "arm_min_y": 480, "x_cutoff": 280,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 350},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 350, "bar_top": 500, "x_cutoff": 320,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 350, "bar_top": 500, "leg_max_y": 350, "x_cutoff": 350,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Ezra SIL SR (SIL OFL) — UPM=2048, scholarly Hebrew Bible font with full
# cantillation. SR = "SIL Roman" version with right-to-left support tweaks.
EZRA_SIL = {
    "id": "ezra-sil",
    "source": "EzraSIL-SR.ttf",
    "output": "SemiticStretchEzraSIL.ttf",
    "family": "Semitic Stretch Ezra SIL SR",
    "postscript": "SemiticStretchEzraSIL",
    "internal_id": "SemiticSearch-SemiticStretchEzraSIL-1.0",
    "step": 300,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 1000, "bar_top": 1500, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        # he: bar_bottom was 1100 / leg_max_y was 1000 — but Ezra's bar
        # bottom row sits at y=1018, smack in the 100-unit gap zone. All
        # bar-bottom points (165, 244, 1061, 1141, 1149, 1201 at y=1018,
        # plus 134 at y=1072) stayed anchored while the upper bar shifted
        # → bar tore apart, and the inflated advance forced "ים" to wrap
        # to a new visual line. Set both to 1000 to close the gap so
        # bar-bottom points (y=1018) land in bar zone with x-split.
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 1000, "bar_top": 1500, "leg_max_y": 1000, "x_cutoff": 800,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        # Lamed: body wide y=893-1259, joint narrows y=1259-1442 (right
        # still at 1160), pure arm y>1442 (x<352). bar_top=1442 keeps the
        # joint in bar zone with x-split; x_cutoff=400 anchors right side.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 900, "bar_top": 1442, "arm_min_y": 1442, "x_cutoff": 400,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 700},
        # resh / tav: same story as he above — bar bottom is at y=1018 in
        # Ezra, so bar_bottom=1100 left the bar's lower-left points outside
        # the shift zone and the upper-left points inside it → taper. Lower
        # to 1000.
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 1000, "bar_top": 1500, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 1000, "bar_top": 1500, "leg_max_y": 1000, "x_cutoff": 800,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# StamAshkenazCLM (Culmus, GPL) — Ashkenazi Stam (Torah-scribal) style.
# This is the closest match to the requested "Taamey Ashkenaz" — Culmus
# does not have a separate "Taamey Ashkenaz" font, only StamAshkenaz. The
# lamed reaches x=-300 even at baseline (already-extended arm); set the
# arm_min_y high so we don't double-stretch.
STAM_ASHKENAZ = {
    "id": "stam-ashkenaz",
    "source": "StamAshkenazCLM.ttf",
    "output": "SemiticStretchStamAshkenazCLM.ttf",
    "family": "Semitic Stretch Stam Ashkenaz CLM",
    "postscript": "SemiticStretchStamAshkenazCLM",
    "internal_id": "SemiticSearch-SemiticStretchStamAshkenazCLM-1.0",
    "step": 300,
    # Source lamed already has xMin=-300 (an extended arm) so the body's
    # right edge (xMax=1115) sits 50 units inside advance=1165. With
    # "shift" mode the renderer translates by -xMin, pushing the body
    # past the advance and into the next letter. With "natural" the body
    # stays at xMax=1115 while advance grows by `shift` → big gap to the
    # next letter on the right. "mono" mode translates by exactly `shift`,
    # preserving the body's 50-unit right offset within the new advance.
    "lsb_mode": "mono",
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 850, "bar_top": 1450, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        # he: bar_bottom was 850 / leg_max_y was 800 — but the actual bar
        # bottom sits at y=700 and the bar's left edge runs UP from y=830.
        # That left a 50-unit gap zone (800..850) where the bar's left-edge
        # points at (114, 832) and (114, 848) DIDN'T shift while everything
        # above and below did → notch/break in the bar's left edge. Set
        # both to 700 (the actual bar bottom) to close the gap.
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 700, "bar_top": 1450, "leg_max_y": 700, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        # Lamed: body wide y=563-1127 (x to 1115), narrow joint y=1127-1314
        # (x=176 only), arm y>1314 reaches OUT to x=-300 (Stam style).
        # bar_top=1314 / arm_min_y=1314 / x_cutoff=400 splits cleanly.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 550, "bar_top": 1314, "arm_min_y": 1314, "x_cutoff": 400,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 600},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 850, "bar_top": 1100, "x_cutoff": 600,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 850, "bar_top": 1100, "leg_max_y": 900, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}

# Shlomo SemiStam (CC BY-SA / OFL via the Open Siddur project, derived
# from Ezra SIL SR — has full cantillation marks). Wayback-archived from
# Google Sites since the original host requires sign-in.
SHLOMO_SEMISTAM = {
    "id": "shlomo-semistam",
    "source": "ShlomoSemiStam.ttf",
    "output": "SemiticStretchShlomoSemiStam.ttf",
    "family": "Semitic Stretch Shlomo SemiStam",
    "postscript": "SemiticStretchShlomoSemiStam",
    "internal_id": "SemiticSearch-SemiticStretchShlomoSemiStam-1.0",
    "step": 300,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 1100, "bar_top": 1500, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["dalet"]},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 1100, "bar_top": 1500, "leg_max_y": 1000, "x_cutoff": 800,
                 "alias_codepoints": ALIAS_DAGESH["he"]},
        # Lamed: body wide y=898-1259 (x to 1180), joint y=1259-1440 (x to
        # 833), arm y>1620 (x<325). bar_top=1440 catches body+joint with
        # x-split; x_cutoff=500 anchors right side cleanly.
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 900, "bar_top": 1440, "arm_min_y": 1440, "x_cutoff": 500,
                 "alias_codepoints": ALIAS_DAGESH["lamed"]},
        0x05DD: {"name": "finalmem", "class": "box", "x_cutoff": 700},
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 1100, "bar_top": 1400, "x_cutoff": 700,
                 "alias_codepoints": ALIAS_DAGESH["resh"]},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 1100, "bar_top": 1400, "leg_max_y": 1100, "x_cutoff": 800,
                 "alias_codepoints": ALIAS_DAGESH["tav"]},
    },
}


# ─── Syriac ──────────────────────────────────────────────────────────
#
# Extends the same bar/arm/leg/box framework to Noto Sans Syriac. Syriac
# is cursive (letters typically JOIN their neighbors), so this stretch
# targets the ISOLATED forms only — good enough for word-final and
# stand-alone letters where scribal justification happens most.
#
# Chosen letters based on glyph-geometry inspection of Noto Sans Syriac
# (UPM=1000):
#   dalath ܕ  U+0715  x=[44..465] y=[-18..426]
#   rish   ܪ  U+072A  x=[44..465] y=[-18..610]
#   taw    ܬ  U+072C  x=[65..688] y=[-29..713]
# Dalath and rish share the classic "kaf-like" curved-top-and-tail shape;
# taw has a clearer horizontal cross-bar. All three are traditional
# scribal justification anchors in Estrangela and Serto manuscripts.
NOTO_SANS_SYRIAC = {
    "id": "noto-sans-syriac",
    "source": "NotoSansSyriac.ttf",
    "output": "SemiticStretchNotoSansSyriac.ttf",
    "family": "Semitic Stretch Noto Sans Syriac",
    "postscript": "SemiticStretchNotoSansSyriac",
    "internal_id": "SemiticSearch-SemiticStretchNotoSansSyriac-1.0",
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "language_system": "syrc",  # Syriac script tag (as opposed to hebr)
    # Widening trigger: U+2060 (Word Joiner), NOT U+0640 tatweel.
    # Reason: separates the two behaviors — Word Joiner fires the widening
    # ligature (letter → widened variant), while U+0640 stays available as
    # the font's natural cursive tatweel for baseline bridging. Both are
    # script=Common so they stay in the Syriac shaping run.
    "stretch_codepoint": 0x2060,
    "letters": {
        # Dalath: bar-class. Bar zone is the flat top portion; x_cutoff picks
        # a point between the stretchable left curve and the anchored right
        # tail. Conservative values pending visual verification.
        0x0715: {"name": "dalath", "class": "bar", "bar_bottom": 300, "bar_top": 420, "x_cutoff": 220},
        # Rish: same shape as dalath but with the additional dot/serif
        # above (higher y-max). Same bar zone. bar_bottom raised from 250
        # to 300 so the shift stops short of the rounded lower transition
        # of the bar — fixes the awkward bottom edge at low stretch levels
        # (image 53/54).
        0x072A: {"name": "rish",   "class": "bar", "bar_bottom": 300, "bar_top": 420, "x_cutoff": 220},
        # Taw: has a horizontal cross-bar higher up. Treat as leg-class
        # (bar + descending left leg). leg_max_y catches the descender
        # portion so it doesn't drag horizontally with the bar shift.
        # x_cutoff dropped from 350 → 250 so taw's vertical ascender
        # (roughly x=280-350, y=400-713) sits fully to the right of the
        # cutoff and stays anchored. Previous value caught the ascender's
        # base in the shift zone while its top (y>bar_top=700) stayed put
        # — producing the triangular tear in image 60.
        0x072C: {"name": "taw",    "class": "leg", "bar_bottom": 400, "bar_top": 700, "leg_max_y": 200, "x_cutoff": 250},
        # Beth: Estrangela beth has a flat top bar from x≈385 to x≈721 at
        # y≈423, with a left-curl foot at x=49-300 below y=100. Widen the
        # whole left half of the letter (curl + rise + left bar) as a
        # unit — bar zone spans the entire body y range so the shifted
        # left half stays continuous with the rise/curl.
        0x0712: {"name": "beth",   "class": "bar", "bar_bottom": 0, "bar_top": 429, "x_cutoff": 550},
    },
}

# Noto Rashi Hebrew (Google, OFL) — UPM=1000. Semi-cursive Rashi script,
# historically used to typeset medieval commentaries alongside the biblical
# text in narrow justified columns — exactly the use-case for kashida
# widening. Letters are DISCRETE (non-joining), so no shaping complications.
# Initial values from bounds inspection: bars sit at y≈500-620, bar-descenders
# (he right leg, tav left leg) drop from ~400 down to baseline.
NOTO_RASHI = {
    "id": "noto-rashi-hebrew",
    "source": "NotoRashiHebrew.ttf",
    "output": "SemiticStretchRashi.ttf",
    "family": "Semitic Stretch Rashi",
    "postscript": "SemiticStretchRashi",
    "internal_id": "SemiticSearch-SemiticStretchRashi-1.0",
    "step": 150,
    "lsb_mode": "mono",  # fixes stretched-letter overlap; see FRANK_RUHL note
    "import_marks": ARABIC_MARKS,
    # Rashi has no U+FB33/34/... presentation-form dagesh glyphs — Rashi text
    # is unpointed in practice, so no ALIAS_DAGESH entries needed.
    #
    # Rashi's letters have a decorative upper-left "hook / ear" peaking at
    # y≈650, while the flat bar sits at y≈590. We need bar_top HIGH ENOUGH
    # to include the ear in the shift zone (so it translates left with the
    # bar); otherwise the ear stays anchored while the bar slides out from
    # under it, breaking the contour. chain_bar_top pulls the OVERFLOW
    # rectangle back down to the flat bar y so the chain seam doesn't
    # tower above the natural body.
    "letters": {
        0x05D3: {"name": "dalet",    "class": "bar", "bar_bottom": 500, "bar_top": 655, "x_cutoff": 220,
                 "chain_bar_top": 590},
        0x05D4: {"name": "he",       "class": "leg", "bar_bottom": 500, "bar_top": 655, "leg_max_y": 400, "x_cutoff": 260},
        0x05DC: {"name": "lamed",    "class": "arm", "bar_bottom": 500, "bar_top": 620, "arm_min_y": 620, "x_cutoff": 200, "arm_top_y": 883,
                 "chain_bar_top": 590},
        # finalmem ם deliberately omitted: Rashi's natural ם is a rounded
        # form, and the mechanical box-class widening produces an ungainly
        # elongated rectangle that reads as un-scribal. Rashi commentators
        # historically stretched ד ה ל ר ת only.
        0x05E8: {"name": "resh",     "class": "bar", "bar_bottom": 500, "bar_top": 655, "x_cutoff": 220,
                 "chain_bar_top": 590},
        0x05EA: {"name": "tav",      "class": "leg", "bar_bottom": 450, "bar_top": 655, "leg_max_y": 400, "x_cutoff": 280},
    },
}

# Nohadra Sapna (Sargis Yonan, OFL) — block-style geometric Syriac.
# UPM=1000, converted from CFF to TT via scripts/convert_nohadra.py.
# Very clean geometry: flat bar at y=303 across every stretchable letter.
NOHADRA_SAPNA = {
    "id": "nohadra-sapna",
    "source": "NohadraSyriacSapna.ttf",
    "output": "SemiticStretchNohadraSapna.ttf",
    "family": "Semitic Stretch Nohadra Sapna",
    "postscript": "SemiticStretchNohadraSapna",
    "internal_id": "SemiticSearch-SemiticStretchNohadraSapna-1.0",
    "step": 150,
    "lsb_mode": "mono",
    "language_system": "syrc",
    # Widening trigger: U+2060 (Word Joiner), NOT U+0640 tatweel.
    # Reason: separates the two behaviors — Word Joiner fires the widening
    # ligature (letter → widened variant), while U+0640 stays available as
    # the font's natural cursive tatweel for baseline bridging. Both are
    # script=Common so they stay in the Syriac shaping run.
    "stretch_codepoint": 0x2060,
    # Nohadra is non-cursive block-style. Auto-justify clusters tatweels on
    # stretchable letters, and our widening ligature consumes every one into
    # a widened variant. Override the font's natural baseline-height (y≈101)
    # tatweel glyph with our 1×1 invisible placeholder so any unmatched
    # tatweel doesn't render as a low block that mismatches the widened
    # letters' y=303 bar height (the "gaps in bars" from image 43).
    "override_trigger_glyph": True,
    # Nohadra letters have significant natural right padding in their base
    # advance (base_adv=958 vs xMax=555 for beth → 400 units of trailing
    # whitespace). Widened variants inherit that padding, and when placed
    # adjacent, the gap between one letter's rightmost bar point and the
    # next letter's leftmost bar point shows as a dark stripe (image 57).
    # Fill each widened variant's advance area with a bar strip at the
    # correct y-range so the bars butt up cleanly across letter boundaries.
    "fill_advance_with_bar": {"bar_bottom": 200, "bar_top": 303},
    "letters": {
        # beth: flat bar y=303 (x=177-555), left foot x=51-177 at y=0-101.
        # bar_zone spans entire body so foot travels with the bar shift.
        0x0712: {"name": "beth",   "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 400},
        # dalath: simple flat bar y=303 across the letter.
        0x0715: {"name": "dalath", "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 200},
        # rish: dalath body + dot above at y=303-455 (x=125-273). Bar_top=303
        # keeps the dot outside the shift zone → it stays at natural position.
        0x072A: {"name": "rish",   "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 200},
        # taw: dalath body + short vertical ascender at x=234-356, y=303-505.
        # Ascender's LEFT edge is right of x_cutoff so it stays anchored while
        # the bar's left half shifts leftward.
        0x072C: {"name": "taw",    "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 200},
        # ─── Extended set: common letters with full-width flat tops at y=303
        # (measured via glyph geometry survey). Adding these gives auto-justify
        # something to stretch on every Peshitta line — the base 4-letter set
        # left most lines with only 0-1 stretchable positions.
        0x0710: {"name": "alaph",  "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 400},
        0x0717: {"name": "he",     "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 400},
        0x0718: {"name": "waw",    "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 220},
        0x0721: {"name": "mim",    "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 300},
        0x0723: {"name": "semkath","class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 400},
        0x072B: {"name": "shin",   "class": "bar", "bar_bottom": 0, "bar_top": 303, "x_cutoff": 400},
    },
}

# Nohadra Amedia — same design as Sapna, slightly different weight/style.
# Same geometry (verified via bbox sampling), so same config values.
NOHADRA_AMEDIA = {
    **NOHADRA_SAPNA,
    "id": "nohadra-amedia",
    "source": "NohadraSyriacAmedia.ttf",
    "output": "SemiticStretchNohadraAmedia.ttf",
    "family": "Semitic Stretch Nohadra Amedia",
    "postscript": "SemiticStretchNohadraAmedia",
    "internal_id": "SemiticSearch-SemiticStretchNohadraAmedia-1.0",
}

# Ge'ez / Ethiopic — Noto Serif Ethiopic. Ethiopic is a SYLLABARY (each
# fidel = consonant+vowel), so we widen 5 consonant SERIES × 7 vowel
# orders = 35 codepoints. The stretchable candidates were selected by
# glyph geometry: fidels with prominent horizontal decorative strokes
# whose left half can shift LEFT while the right anchor + vowel
# decoration stay in place. Modelled on the manuscript calligraphic
# widening tradition (14th–19th c. illuminated Ge'ez).
#
# Widening trigger: U+2060 (Word Joiner) — same as Syriac. script=Common
# so it stays in the Ethiopic run and the ligature substitution fires.
# `override_trigger_glyph: True` keeps unmatched triggers invisible.
_ETH_SERIES = {
    # base_cp: (name, x_cutoff)
    # x_cutoff is the vertical split — points to the LEFT shift with the
    # stretch, points to the RIGHT stay anchored. Chosen just LEFT of the
    # main "middle" or "right anchor" of the fidel so the anchor and any
    # right-side vowel decoration stay put.
    0x1218: ("ma",  400),   # መ series (7 fidels መ ሙ ሚ ማ ሜ ም ሞ)
    0x1220: ("sza", 300),   # ሠ series
    0x1210: ("hha", 280),   # ሐ series
    0x1320: ("tha", 400),   # ጠ series
    0x12C8: ("wa",  380),   # ወ series
}
_ETHIOPIC_LETTERS: dict[int, dict] = {}
for _base, (_name, _xcut) in _ETH_SERIES.items():
    for _order in range(7):
        _cp = _base + _order
        _ord_suffix = ["e", "u", "i", "aa", "ee", "y", "o"][_order]
        _ETHIOPIC_LETTERS[_cp] = {
            "name": f"{_name}_{_ord_suffix}",
            "class": "bar",
            # Bar zone spans essentially the full glyph height so every
            # left-side contour point participates in the shift (Ethiopic
            # fidels have decorative features throughout — no need to
            # isolate a specific horizontal band).
            "bar_bottom": -200,
            "bar_top": 900,
            "x_cutoff": _xcut,
        }

NOTO_SERIF_ETHIOPIC = {
    "id": "noto-serif-ethiopic",
    "source": "NotoSerifEthiopic.ttf",
    "output": "SemiticStretchNotoSerifEthiopic.ttf",
    "family": "Semitic Stretch Noto Serif Ethiopic",
    "postscript": "SemiticStretchNotoSerifEthiopic",
    "internal_id": "SemiticSearch-SemiticStretchNotoSerifEthiopic-1.0",
    "step": 100,
    "lsb_mode": "mono",
    "language_system": "ethi",  # OpenType script tag for Ethiopic
    "stretch_codepoint": 0x2060,
    "override_trigger_glyph": True,
    "letters": _ETHIOPIC_LETTERS,
}

CONFIGS = [
    FRANK_RUHL, KETER_ARAM_TSOVA, SHMULIK, HILLEL, GLADIA,
    NOTO_SANS_HEBREW, NOTO_SERIF_HEBREW, SHOFAR,
    FREE_MONO, NACHLIELI, MIRIAM_MONO, EZRA_SIL,
    STAM_ASHKENAZ, SHLOMO_SEMISTAM,
    NOTO_RASHI,
    NOTO_SANS_SYRIAC, NOHADRA_SAPNA, NOHADRA_AMEDIA,
    NOTO_SERIF_ETHIOPIC,
]

# Stretching model (matches Torah scribal widening):
#   bar — top bar stretches; no rigid arm/leg (dalet ד, resh ר).
#   arm — top bar stretches; arm ABOVE rides rigidly with the bar's left
#         edge (lamed ל).
#   leg — top bar stretches; LEFT leg BELOW rides rigidly with the bar's
#         left edge (tav ת, he ה). Right leg stays anchored.
#   box — enclosed rectangle widens on the left (finalmem ם).
#
# Within the bar zone we use a hard x-split (not linear falloff): points at
# x<x_cutoff shift by the full amount (riding with the arm/leg), points at
# x≥x_cutoff stay anchored. This produces a FLAT extended top bar.
#
# `aliases`: extra source glyphs that should ALSO trigger the stretch (in
# addition to the base codepoint). Needed because each font's `ccmp`/`rlig`
# pre-composes letter+dagesh into Hebrew Presentation Forms (U+FB30 block)
# BEFORE our liga runs. Without aliases, vocalized text with dagesh (תּ,
# דּ, ...) would never stretch.


def stretch_glyph(
    font: TTFont,
    src_name: str,
    shift: int,
    *,
    letter_class: str = "bar",
    bar_bottom: int = 440,
    bar_top: int = 620,
    arm_min_y: int | None = None,
    leg_max_y: int | None = None,
    x_cutoff: int | None = None,
    shift_contours: list[int] | None = None,
    underside_y_max: int | None = None,
    underside_x_min: int | None = None,
) -> object:
    """Return a new TTGlyph built from `src_name` with selected points
    shifted LEFT. Shift depends on letter_class and the point's (x, y):

      bar — y in [bar_bottom, bar_top] AND x < x_cutoff:
              shift = full * (1 - x/x_cutoff)   (linear falloff)
            else: no shift.

      arm — y >= arm_min_y AND x < x_cutoff: full shift (rigid translate).
            y in [bar_bottom, arm_min_y] AND x < x_cutoff:
              shift = full * (1 - x/x_cutoff).
            else: no shift.

      leg — y <= leg_max_y AND x < x_cutoff: full shift (rigid left leg).
            y in [bar_bottom, bar_top] AND x < x_cutoff:
              shift = full * (1 - x/x_cutoff).
            else: no shift.

      box — x < x_cutoff: full shift (widen left side of rectangle).
    """
    src = font["glyf"][src_name]
    if src.numberOfContours <= 0:
        return copy.deepcopy(src)

    def shift_for(x: int, y: int) -> float:
        """Hard-boundary horizontal stretch. Points are either:
          — shifted by the FULL amount (they move rigidly leftward with the
            stretching region's left edge), or
          — not shifted at all (they stay anchored to the right side).
        A linear falloff would curve the extended bar; the user wants it
        FLAT (like image #36), so we use a hard x-boundary inside the bar
        zone. The arm (above) or leg (below) the bar also translates
        rigidly by the full amount, staying connected to the bar's left
        edge and preserving its own decorative shape (serifs, flags).
        """
        if x_cutoff is None:
            return 0.0
        if letter_class == "box":
            return shift if x < x_cutoff else 0.0
        if letter_class == "arm":
            # above the bar: whole arm translates by full shift
            if arm_min_y is not None and y > arm_min_y:
                return shift
            # inside the bar: hard x-split
            if bar_bottom <= y <= bar_top:
                return shift if x < x_cutoff else 0.0
            return 0.0
        if letter_class == "leg":
            # below the bar: left leg (x<x_cutoff) translates, right leg stays
            if leg_max_y is not None and y <= leg_max_y:
                return shift if x < x_cutoff else 0.0
            # inside the bar: hard x-split
            if bar_bottom <= y <= bar_top:
                return shift if x < x_cutoff else 0.0
            return 0.0
        # "bar" (dalet, resh): only the bar zone stretches, hard split
        if bar_bottom <= y <= bar_top:
            return shift if x < x_cutoff else 0.0
        return 0.0

    # "shear" class: shift each point LEFT by an amount proportional to
    # (1 - y/bar_top). Top of letter (y=bar_top) doesn't move; bottom
    # (y=0) shifts by the full amount; linear interpolation between.
    # This widens letters whose skeleton is DIAGONAL (aleph, ayin) without
    # breaking the contours — the whole letter tilts so the diagonal
    # becomes more horizontal while every part stays connected at the top.
    if letter_class == "shear":
        y_ref = bar_top  # use bar_top as the "anchor y" where shift = 0
        new_glyph = copy.deepcopy(src)
        for i, (x, y) in enumerate(new_glyph.coordinates):
            factor = max(0.0, 1.0 - y / y_ref) if y_ref > 0 else 0.0
            dx = shift * factor
            if dx != 0:
                new_glyph.coordinates[i] = (int(round(x - dx)), y)
        new_glyph.recalcBounds(font["glyf"])
        return new_glyph

    # "contours" class kept for reference — rigid translation of whole
    # contours. Works when the letter has truly disconnected parts but
    # creates visible gaps for letters whose contours share a visual
    # connection (like aleph's diagonal touching the upper hook).
    if letter_class == "contours" and shift_contours is not None:
        end_pts = list(src.endPtsOfContours)
        def contour_idx(i: int) -> int:
            for ci, end in enumerate(end_pts):
                if i <= end:
                    return ci
            return len(end_pts) - 1
        new_glyph = copy.deepcopy(src)
        for i, (x, y) in enumerate(new_glyph.coordinates):
            if contour_idx(i) in shift_contours:
                new_glyph.coordinates[i] = (int(x - shift), y)
        new_glyph.recalcBounds(font["glyf"])
        return new_glyph

    new_glyph = copy.deepcopy(src)
    orig_coords = list(src.coordinates)
    for i, (x, y) in enumerate(new_glyph.coordinates):
        s = shift_for(x, y)
        if s > 0:
            new_glyph.coordinates[i] = (int(round(x - s)), y)

    # Optionally straighten the underside of the bar. Some fonts (e.g.
    # Keter Aram Tsova resh) have an arch-shaped underside — the bottom
    # edge of the top bar dips to a flat dome at y=784 between two end
    # points at y=720 and y=745. When stretched, this arch is preserved
    # and reads as a "bend" in the otherwise straight bar. Snapping the
    # moving underside points onto the line connecting the right anchor
    # to the leftmost shifted point flattens the dome into a clean
    # (slightly angled) line. underside_x_min lets us exclude the left
    # ear, which lives in the same y range but should keep its curve.
    if underside_y_max is not None:
        underside_idx = [
            i for i, (ox, oy) in enumerate(orig_coords)
            if bar_bottom <= oy <= underside_y_max
            and (underside_x_min is None or ox >= underside_x_min)
        ]
        anchor = None    # rightmost original (x, y) that did NOT shift
        leftmost = None  # leftmost original (idx, x, y) that DID shift
        for i in underside_idx:
            ox, oy = orig_coords[i]
            nx, _ = new_glyph.coordinates[i]
            if ox == nx:  # not shifted
                if anchor is None or ox > anchor[0]:
                    anchor = (ox, oy)
            else:
                if leftmost is None or ox < leftmost[1]:
                    leftmost = (i, ox, oy)
        if anchor is not None and leftmost is not None:
            ax, ay = anchor
            li, _, _ = leftmost
            lx_new, ly_new = new_glyph.coordinates[li]
            slope = (ly_new - ay) / (lx_new - ax) if lx_new != ax else 0
            for i in underside_idx:
                ox, _ = orig_coords[i]
                nx, _ = new_glyph.coordinates[i]
                if ox != nx:
                    target_y = ay + slope * (nx - ax)
                    new_glyph.coordinates[i] = (nx, int(round(target_y)))

    new_glyph.recalcBounds(font["glyf"])
    return new_glyph


def build_simple_gsub_ligatures(font: TTFont, lig_map: dict[tuple[str, str], str]) -> None:
    """Install a ligature-substitution lookup and WIRE IT INTO EVERY
    existing `liga` feature in the font. Adding a duplicate feature record
    or duplicate script record would be ignored by most OT shapers, so
    instead we append our new lookup index to each liga-feature already
    present. Fall back to creating a new feature if none exists."""
    components_by_first: dict[str, list[tuple[str, str]]] = {}
    for (first, second), lig in lig_map.items():
        components_by_first.setdefault(first, []).append((second, lig))

    gsub = font.get("GSUB")
    if gsub is None:
        gsub = font["GSUB"] = otTables_new_gsub()

    # Build the ligature-subst subtable.
    ligs = ot.LigatureSubst()
    ligs.ligatures = {}
    for first, pairs in components_by_first.items():
        bucket = []
        for second, lig in pairs:
            L = ot.Ligature()
            L.Component = [second]
            L.LigGlyph = lig
            L.CompCount = 2
            bucket.append(L)
        ligs.ligatures[first] = bucket

    lookup = ot.Lookup()
    lookup.LookupType = 4
    lookup.LookupFlag = 0
    lookup.SubTableCount = 1
    lookup.SubTable = [ligs]

    table = gsub.table
    if table.LookupList is None:
        table.LookupList = ot.LookupList()
        table.LookupList.Lookup = []
        table.LookupList.LookupCount = 0
    lookup_index = len(table.LookupList.Lookup)
    table.LookupList.Lookup.append(lookup)
    table.LookupList.LookupCount = len(table.LookupList.Lookup)

    # Ensure FeatureList / ScriptList exist.
    if table.FeatureList is None:
        table.FeatureList = ot.FeatureList()
        table.FeatureList.FeatureRecord = []
        table.FeatureList.FeatureCount = 0
    if table.ScriptList is None:
        table.ScriptList = ot.ScriptList()
        table.ScriptList.ScriptRecord = []
        table.ScriptList.ScriptCount = 0

    # Find every existing 'liga' FeatureRecord and append our lookup_index
    # to its LookupListIndex. If none exists, create one and wire it up
    # from every existing script's DefaultLangSys.
    wired = 0
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag == "liga":
            rec.Feature.LookupListIndex.append(lookup_index)
            rec.Feature.LookupCount = len(rec.Feature.LookupListIndex)
            wired += 1

    if wired == 0:
        # No existing liga feature — create one and point all scripts at it.
        feat = ot.Feature()
        feat.LookupListIndex = [lookup_index]
        feat.LookupCount = 1
        fr = ot.FeatureRecord()
        fr.FeatureTag = "liga"
        fr.Feature = feat
        table.FeatureList.FeatureRecord.append(fr)
        table.FeatureList.FeatureCount = len(table.FeatureList.FeatureRecord)
        new_feat_index = len(table.FeatureList.FeatureRecord) - 1
        # Attach to all existing scripts (DFLT / hebr / etc.)
        for sr in table.ScriptList.ScriptRecord:
            if sr.Script.DefaultLangSys is not None:
                lis = sr.Script.DefaultLangSys.FeatureIndex
                if new_feat_index not in lis:
                    lis.append(new_feat_index)
                    sr.Script.DefaultLangSys.FeatureCount = len(lis)
        # If no scripts either, create DFLT.
        if not table.ScriptList.ScriptRecord:
            sr = ot.ScriptRecord()
            sr.ScriptTag = "DFLT"
            s = ot.Script()
            s.DefaultLangSys = ot.DefaultLangSys()
            s.DefaultLangSys.LookupOrder = None
            s.DefaultLangSys.ReqFeatureIndex = 0xFFFF
            s.DefaultLangSys.FeatureIndex = [new_feat_index]
            s.DefaultLangSys.FeatureCount = 1
            s.LangSysRecord = []
            s.LangSysCount = 0
            sr.Script = s
            table.ScriptList.ScriptRecord.append(sr)
            table.ScriptList.ScriptCount = 1


def otTables_new_gsub():
    """Build a minimal empty GSUB table object."""
    from fontTools.ttLib.tables.otBase import BaseTTXConverter
    from fontTools.ttLib.tables.G_S_U_B_ import table_G_S_U_B_
    t = table_G_S_U_B_("GSUB")
    t.table = ot.GSUB()
    t.table.ScriptList = None
    t.table.FeatureList = None
    t.table.LookupList = None
    t.table.Version = 0x00010000
    return t


def import_arabic_marks(target_font: TTFont, codepoints: list[int]) -> int:
    """Copy combining-mark glyphs from Amiri-Regular.ttf into target_font,
    scaling coordinates if UPMs differ. Returns count of marks imported.

    Why: shaddah / tanwin (U+0651, U+064B-064D) are Arabic combining marks.
    When typed after a Hebrew letter, browsers either render them via font
    fallback (often misaligned) or show tofu. Embedding the mark glyphs
    directly in our Hebrew font lets the same font render the base + mark
    as one shaping run, avoiding fallback weirdness.

    The source glyph's y-coordinates (Amiri designs them at y=820-1230 to
    sit above Arabic letters) line up well with Hebrew letter heights
    when both UPMs are 1000. For other UPMs we scale.
    """
    amiri_path = FONTS_DIR / "Amiri-Regular.ttf"
    if not amiri_path.exists():
        return 0
    amiri = TTFont(str(amiri_path))
    src_upem = amiri["head"].unitsPerEm
    dst_upem = target_font["head"].unitsPerEm
    scale = dst_upem / src_upem
    src_cmap = amiri.getBestCmap()
    target_glyf = target_font["glyf"]
    target_hmtx = target_font["hmtx"]
    order = target_font.getGlyphOrder()
    imported = 0
    for cp in codepoints:
        gname = src_cmap.get(cp)
        if not gname:
            continue
        src_glyph = amiri["glyf"][gname]
        # Decompose composite glyphs into a flat outline (kasratan is
        # composite in Amiri — referencing other glyphs by name — and we
        # can't easily port its components piecewise). Use TTGlyphPen +
        # decompose machinery via the glyph set.
        if src_glyph.numberOfContours == -1:
            # Composite — render via amiri's glyph set then capture outline.
            from fontTools.pens.recordingPen import DecomposingRecordingPen
            from fontTools.pens.transformPen import TransformPen
            from fontTools.misc.transform import Identity
            amiri_gs = amiri.getGlyphSet()
            pen = DecomposingRecordingPen(amiri_gs)
            amiri_gs[gname].draw(pen)
            ttpen = TTGlyphPen(None)
            scale_t = Identity.scale(scale, scale)
            tp = TransformPen(ttpen, scale_t)
            pen.replay(tp)
            new_glyph = ttpen.glyph()
        else:
            new_glyph = copy.deepcopy(src_glyph)
            for i, (x, y) in enumerate(new_glyph.coordinates):
                new_glyph.coordinates[i] = (int(round(x * scale)), int(round(y * scale)))
            new_glyph.recalcBounds(target_glyf)
        target_glyf[gname] = new_glyph
        # Combining marks have advance=0
        target_hmtx.metrics[gname] = (0, 0)
        if gname not in order:
            order.append(gname)
        # cmap mapping
        for t in target_font["cmap"].tables:
            if t.isUnicode() or t.platformID == 3:
                t.cmap[cp] = gname
        imported += 1
    target_font.setGlyphOrder(order)
    return imported


def add_two_dots_above(target_font: TTFont) -> bool:
    """Install a custom 'two dots above' glyph at U+0308 (combining diaeresis).
    Designed for Hebrew letter heights — sits well above the letter cap. Uses
    negative x-positioning so the mark backs up over the preceding character.
    Returns True if added.
    """
    upem = target_font["head"].unitsPerEm
    # Scale factors relative to UPM=1000 baseline
    s = upem / 1000.0
    cy = int(900 * s)        # vertical center of the dots (above letter cap)
    r = int(60 * s)          # dot radius
    cx_left = int(-330 * s)  # left dot center (negative — backs up over base)
    cx_right = int(-110 * s)

    pen = TTGlyphPen(None)
    for cx in (cx_left, cx_right):
        # Approximate a circle with 4 quadratic Bezier segments.
        pen.moveTo((cx + r, cy))
        pen.qCurveTo((cx + r, cy + r), (cx, cy + r))
        pen.qCurveTo((cx - r, cy + r), (cx - r, cy))
        pen.qCurveTo((cx - r, cy - r), (cx, cy - r))
        pen.qCurveTo((cx + r, cy - r), (cx + r, cy))
        pen.closePath()
    glyph = pen.glyph()

    gname = f"uni{DIAERESIS_CP:04X}"
    order = target_font.getGlyphOrder()
    if gname not in order:
        order.append(gname)
        target_font.setGlyphOrder(order)
    target_font["glyf"][gname] = glyph
    target_font["hmtx"].metrics[gname] = (0, 0)  # combining mark
    for t in target_font["cmap"].tables:
        if t.isUnicode() or t.platformID == 3:
            t.cmap[DIAERESIS_CP] = gname
    return True


def build_overflow_segment(
    font: TTFont,
    src_glyph_name: str,
    info: dict,
    step: int,
    max_levels: int,
    lsb_mode: str,
) -> tuple[str, int, int]:
    """Build the overflow "tatweel" bar-segment glyph for a stretchable
    letter. Returns (segment_glyph_name, advance, lsb).

    Inspired by Arabic kashida tatweel: a flat horizontal segment matching
    the letter's bar y-band that tiles seamlessly to the LEFT (in RTL
    display) of the letter's max pre-baked variant. Each additional U+05C6
    after `letter_s{max_levels}` substitutes into another segment, so the
    extension grows without bound.

    Geometry:
      · width = `step` font units (one stretch level), so segment N adds
        the same horizontal increment as a pre-baked level would have.
      · y-band = [bar_bottom, bar_top] from the letter config — matches
        the bar's design thickness exactly so the seam is invisible.

    LSB math:
      · HarfBuzz emits glyphs in VISUAL left-to-right order (regardless of
        script direction). Renderers accumulate pen rightward (pen += adv)
        and draw each glyph at `pen + (lsb - xMin)`.
      · For RTL text "ל" + N kashidas + "ה", the buffer order is:
        [heh, seg, seg, ..., seg, lamed_s16] — segments sit BETWEEN heh
        (leftmost) and lamed_s16 (rightmost), tiling to lamed's bar-left.
      · The variant's bar-left display = pen_lamed + (lsb - xMin) +
        bar_xmin_stretched. Since pen_lamed is determined by cumulative
        advance of preceding glyphs, the segment just needs an LSB that
        positions its outline at the bar's y-band exactly:
            lsb_seg = bar_left_offset_in_glyph
        (= the leftmost bar-x minus the glyph's own xMin in the source.)
      · This makes segments tile contiguously and the LAST segment's
        right edge land exactly on the variant's bar-left display.
    """
    bar_bottom = int(info["bar_bottom"])
    bar_top = int(info["bar_top"])
    letter_name = str(info["name"])

    pen = TTGlyphPen(None)
    pen.moveTo((0, bar_bottom))
    pen.lineTo((step, bar_bottom))
    pen.lineTo((step, bar_top))
    pen.lineTo((0, bar_top))
    pen.closePath()
    seg_glyph = pen.glyph()

    seg_name = f"{letter_name}_bar_segment"

    src_glyph = font["glyf"][src_glyph_name]

    # Bar's leftmost x within its y-band (in source-glyph coordinates).
    # Both bar_xmin and glyph xmin shift by the same total_shift during
    # stretching, so the offset is invariant — read it from the source.
    bar_xs = [x for x, y in src_glyph.coordinates if bar_bottom <= y <= bar_top]
    bar_left_offset = (min(bar_xs) - src_glyph.xMin) if bar_xs else 0

    # See docstring above for derivation. For all lsb_modes the LSB is the
    # same simple value because what matters is where the segment's outline
    # falls relative to its pen position — and that's just the bar offset.
    lsb_seg = bar_left_offset

    font["glyf"][seg_name] = seg_glyph
    font["hmtx"].metrics[seg_name] = (step, lsb_seg)
    order = font.getGlyphOrder()
    if seg_name not in order:
        order.append(seg_name)
        font.setGlyphOrder(order)

    return seg_name, step, lsb_seg


def _clip_glyph_at_y(
    glyf_table, glyph_name: str, y_threshold: int, *, keep_below: bool
) -> pathops.Path:
    """Boolean-intersect a glyph's outline with a half-plane y <= threshold
    (keep_below=True) or y >= threshold (False). Returns a pathops Path.

    Draws directly from the glyf table rather than via font.getGlyphSet() —
    the latter eagerly loads gvar, which is stale after we've added stretch
    variant glyphs (gvar.glyphCount no longer matches the font's glyphOrder).
    """
    src = pathops.Path()
    glyf_table[glyph_name].draw(src.getPen(), glyf_table)
    BIG = 100_000
    clip = pathops.Path()
    cp = clip.getPen()
    if keep_below:
        cp.moveTo((-BIG, -BIG)); cp.lineTo((BIG, -BIG))
        cp.lineTo((BIG, y_threshold)); cp.lineTo((-BIG, y_threshold))
    else:
        cp.moveTo((-BIG, y_threshold)); cp.lineTo((BIG, y_threshold))
        cp.lineTo((BIG, BIG)); cp.lineTo((-BIG, BIG))
    cp.closePath()
    return pathops.op(src, clip, pathops.PathOp.INTERSECTION)


def build_overflow_chain(
    font: TTFont,
    src_glyph_name: str,
    last_variant_name: str,
    info: dict,
    step: int,
    max_levels: int,
) -> tuple[str, str, str]:
    """For a stretchable letter with bar or arm class, build the three-glyph
    chain that extends the bar past the pre-baked variant cap. For arm-class
    letters the arm migrates to the leftmost end:

      · {name}_overflow_start   — lamed_s{max} with the arm clipped off
                                  (just bar + body). Substitutes in for
                                  lamed_s{max} when overflow triggers, so
                                  the arm doesn't double up at both ends.
      · {name}_bar_segment      — plain bar rectangle, intermediate tile.
      · {name}_overflow_tail    — bar rectangle + arm extracted from the
                                  original glyph, translated to overhang
                                  the bar's left by `bar_left_offset`
                                  units (matching lamed_s{max}'s arm-vs-
                                  bar offset).

    GSUB chain (added later in fea_lines):
      sub last' kashida by start;        # demote when overflow about to fire
      sub start kashida' lookup → tail;  # first overflow kashida → tail
      sub tail  kashida' lookup → tail;  # subsequent kashidas → tail
      sub tail' tail by intermediate;    # demote all-but-rightmost tail to plain seg

    All lsb math assumes lsb_mode="shift" (caller responsibility to gate).
    """
    bar_bottom = int(info["bar_bottom"])
    bar_top = int(info["bar_top"])
    letter_class = str(info.get("class", "bar"))
    has_arm = letter_class == "arm"
    arm_min_y = int(info.get("arm_min_y", bar_top))
    letter_name = str(info["name"])

    glyf = font["glyf"]
    src_glyph = glyf[src_glyph_name]

    # Bar's leftmost x within its y-band (in source-glyph coords). Both bar
    # and arm shift by the same total_shift during stretching so this is
    # invariant.
    bar_xs = [x for x, y in src_glyph.coordinates if bar_bottom <= y <= bar_top]
    bar_left_offset = (min(bar_xs) - src_glyph.xMin) if bar_xs else 0

    # The body's natural bar top — typically lower than `bar_top` because
    # `bar_top` covers the bar/arm transition shoulder. Clipping lamed_s{max}
    # at this y and matching the segment's top to it makes the bar a uniform
    # flat strip across the entire extended cluster (no seam at the shoulder).
    arm_xs = [x for x, y in src_glyph.coordinates if y > arm_min_y]
    arm_x_range = (min(arm_xs), max(arm_xs)) if arm_xs else (0, 0)
    body_top_ys = [
        y for x, y in src_glyph.coordinates
        if bar_bottom <= y <= bar_top
        and not (arm_x_range[0] <= x <= arm_x_range[1])
    ]
    seg_bar_top = max(body_top_ys) if body_top_ys else bar_top
    # chain_bar_top: the chain bar TILE's top (lower than seg_bar_top
    # when the natural body has a kotz extending above the bar). Defaults
    # to seg_bar_top. Set on letters whose seg_bar_top includes a kotz
    # peak so the bar tile stays at bar height while the cap region
    # (edge_path, which uses seg_bar_top) still captures the kotz.
    chain_bar_top = int(info.get("chain_bar_top", seg_bar_top))
    # chain_bar_bottom: the chain bar TILE's bottom (higher than bar_bottom
    # when the natural body's bar bottom sits ABOVE the stretch zone bottom —
    # e.g., bar_bottom encompasses a wall/descender for translation purposes,
    # but the actual flat bar bottom is higher up). Defaults to bar_bottom.
    # Set this when the bar_segment tile would otherwise extend below the
    # natural body's bar, creating a visible step at the chain seam.
    chain_bar_bottom = int(info.get("chain_bar_bottom", bar_bottom))

    # The bar's left-edge has rounded corners (top-left and bottom-left
    # softening) in most Hebrew designs. We want those corners ONLY at the
    # visual leftmost end of the extended cluster (= seg_tail), so we need
    # to clip them off lamed_overflow_start AND graft them onto seg_tail.
    #
    # bar_clip_x_left = the x in last_glyph coords where the bar's flat
    # extension ends and the natural left ear/cap begins. Compute it from
    # the SOURCE glyph using two complementary signals:
    #   leftmost: leftmost ON-curve at bar's flat top (chain_bar_top), and
    #   rightmost: rightmost x of any kotz pt (y > chain_bar_top in stretch
    #              zone, x < x_cutoff so it actually translates).
    # Take the MAX so the cap captures both the bar's flat-top left edge
    # AND the kotz's right curl. If the kotz right side extends past the
    # bar's leftmost flat point (Shmulik dalet: kotz curl reaches x=411
    # but bar flat starts at x=394), using just leftmost leaves a kotz
    # sliver in the start glyph.
    last_glyph = glyf[last_variant_name]
    cutoff = info.get("x_cutoff")
    bar_top_pts = [
        src_glyph.coordinates[i][0]
        for i in range(len(src_glyph.coordinates))
        if (src_glyph.flags[i] & 1)
        and abs(src_glyph.coordinates[i][1] - chain_bar_top) <= 5
    ]
    # Filter kotz pts to LEFT HALF of bar zone — the bar zone spans
    # [src.xMin, x_cutoff]; the bar's left kotz is in the left half,
    # the right kotz (above the body's right side) is in the right
    # half. Without this filter, off-curve transitions between bar
    # and right kotz get treated as left-side kotz pts, pulling
    # bar_clip_x_left way too far right.
    bar_zone_mid = (int(src_glyph.xMin) + (cutoff if cutoff is not None else int(src_glyph.xMax))) // 2
    kotz_xs = [
        src_glyph.coordinates[i][0]
        for i in range(len(src_glyph.coordinates))
        if src_glyph.coordinates[i][1] > chain_bar_top + 5
        and src_glyph.coordinates[i][0] < bar_zone_mid
    ]
    if bar_top_pts:
        src_bar_left = min(bar_top_pts)
        if kotz_xs:
            src_bar_left = max(src_bar_left, max(kotz_xs) + 5)
        bar_clip_x_left = src_bar_left + (int(last_glyph.xMin) - int(src_glyph.xMin))
    else:
        # Fallback: second-leftmost x at y=bar_bottom in last_glyph (works
        # when the source has on-curves exactly at bar_bottom — e.g., a flat
        # bar bottom with rounded left corner).
        bottom_xs = sorted({x for x, y in last_glyph.coordinates if y == bar_bottom})
        bar_clip_x_left = bottom_xs[1] if len(bottom_xs) >= 2 else last_glyph.xMin

    # 1. start glyph: lamed_s{max} clipped at (x >= bar_clip_x_left, y <= seg_bar_top)
    # so its left edge is a clean vertical line that tiles seamlessly with
    # the rectangular intermediate segments.
    BIG = 100_000
    src_path = pathops.Path()
    last_glyph.draw(src_path.getPen(), glyf)
    clip_box = pathops.Path()
    cb = clip_box.getPen()
    cb.moveTo((bar_clip_x_left, -BIG)); cb.lineTo((BIG, -BIG))
    cb.lineTo((BIG, seg_bar_top)); cb.lineTo((bar_clip_x_left, seg_bar_top))
    cb.closePath()
    no_arm_path = pathops.op(src_path, clip_box, pathops.PathOp.INTERSECTION)
    start_pen = TTGlyphPen(None)
    no_arm_path.draw(start_pen)
    start_glyph = start_pen.glyph()
    start_glyph.recalcBounds(glyf)
    start_name = f"{letter_name}_overflow_start"
    glyf[start_name] = start_glyph
    base_advance = font["hmtx"].metrics[src_glyph_name][0]
    max_advance = base_advance + step * max_levels
    # lsb=0 (shift mode) keeps display alignment consistent with lamed_s{max}.
    font["hmtx"].metrics[start_name] = (max_advance, 0)

    # 2. Extract the natural left-side structure (ear + arm + bar's leftmost
    # portion) from lamed_s{max} as a single piece. Earlier versions used
    # two separate extractions — a "cap" clipped at seg_bar_top plus an
    # "arm" clipped from the source above seg_bar_top — and joined them with
    # a filler rect. That produced visible square corners at the synthetic
    # boundaries (cap-top horizontal line, filler edges) where the natural
    # design has smooth ear-to-arm curves.
    #
    # Single extraction: keep everything in last_glyph at x <= bar_clip_x_left
    # and y >= chain_bar_bottom. Translate so its rightmost x lands at 0,
    # matching the bar tile's leftmost edge. Optional arm_top_y clip removes
    # decorative serifs at the very top (set per-letter when the source's arm
    # ends in a kotz that reads as a "lip" when grafted onto an extension).
    left_clip = pathops.Path()
    lc = left_clip.getPen()
    lc.moveTo((-BIG, chain_bar_bottom)); lc.lineTo((bar_clip_x_left, chain_bar_bottom))
    lc.lineTo((bar_clip_x_left, BIG)); lc.lineTo((-BIG, BIG))
    lc.closePath()
    left_path = pathops.op(src_path, left_clip, pathops.PathOp.INTERSECTION)
    arm_top_y = info.get("arm_top_y") if has_arm else None
    if arm_top_y is not None:
        top_clip = pathops.Path()
        tc = top_clip.getPen()
        tc.moveTo((-BIG, -BIG)); tc.lineTo((BIG, -BIG))
        tc.lineTo((BIG, int(arm_top_y))); tc.lineTo((-BIG, int(arm_top_y)))
        tc.closePath()
        left_path = pathops.op(left_path, top_clip, pathops.PathOp.INTERSECTION)
    left_xmax_orig = left_path.bounds[2] if left_path.bounds else 0
    left_path = left_path.transform(1, 0, 0, 1, -left_xmax_orig, 0)

    # 3. tail glyph: natural left piece + bar rectangle. Bar extends 2 units
    # beyond `step` on both sides so adjacent segments overlap (hides sub-
    # pixel/AA gaps).
    tail_pen = TTGlyphPen(None)
    left_path.draw(tail_pen)
    tail_pen.moveTo((-2, chain_bar_bottom))
    tail_pen.lineTo((step + 2, chain_bar_bottom))
    tail_pen.lineTo((step + 2, chain_bar_top))
    tail_pen.lineTo((-2, chain_bar_top))
    tail_pen.closePath()
    tail_glyph = tail_pen.glyph()
    tail_glyph.recalcBounds(glyf)
    tail_name = f"{letter_name}_overflow_tail"
    glyf[tail_name] = tail_glyph
    # lsb = xMin so display offset = 0 → bar's display = pen..pen+step,
    # tiling seamlessly to the next intermediate segment (which has lsb=0).
    font["hmtx"].metrics[tail_name] = (step, tail_glyph.xMin)

    # 5. intermediate segment: plain bar rectangle, lsb=0. Outline extends
    # 2 units beyond `step` on each side to overlap adjacent segments and
    # hide sub-pixel rendering gaps between glyphs.
    int_pen = TTGlyphPen(None)
    int_pen.moveTo((-2, chain_bar_bottom))
    int_pen.lineTo((step + 2, chain_bar_bottom))
    int_pen.lineTo((step + 2, chain_bar_top))
    int_pen.lineTo((-2, chain_bar_top))
    int_pen.closePath()
    int_glyph = int_pen.glyph()
    int_name = f"{letter_name}_bar_segment"
    glyf[int_name] = int_glyph
    font["hmtx"].metrics[int_name] = (step, 0)

    order = font.getGlyphOrder()
    for n in (start_name, int_name, tail_name):
        if n not in order:
            order.append(n)
    font.setGlyphOrder(order)

    return start_name, int_name, tail_name


def _restore_table(font, tag: str, saved_bytes: bytes):
    """Restore a table (GDEF / GPOS) from its compiled binary. feaLib
    replaces both when it builds features from a .fea source, so we save
    before and put back after. GDEF carries glyph classifications (base
    vs mark vs ligature); GPOS carries the mark-to-base anchors that
    position Hebrew niqqud."""
    from fontTools.ttLib import newTable
    tbl = newTable(tag)
    tbl.decompile(saved_bytes, font)
    font[tag] = tbl


def _add_widened_variant_anchors(font, config) -> int:
    """After restoring the original GPOS, add MarkBase anchor entries
    for each widened variant so niqqud attaches at the CENTER of the
    widened advance (not the natural letter body position, which after
    `mono` LSB translation ends up flush right in the widened glyph).

    For each base letter that already has anchors in the GPOS MarkBase
    lookup, and for each of its widened variants (letter_sN), inject a
    new BaseRecord whose per-class anchors have the same Y as the base
    but X shifted to (advance_of_variant) / 2. This aligns marks with
    the horizontal midpoint of the widened glyph.

    Returns the count of widened variants that received new anchors.
    """
    from fontTools.ttLib.tables import otTables as ot

    if "GPOS" not in font or "GSUB" not in font:
        return 0

    gpos = font["GPOS"].table
    hmtx = font["hmtx"]
    if gpos is None or not gpos.LookupList:
        return 0

    # Find every MarkBase (Type 4) lookup — Frank Ruhl et al. have one.
    added = 0
    letters = config.get("letters") or {}
    # Map source glyph name → its widened variant names in this build.
    # Variant names are e.g. `dalet_s1`, `dalet_s2`, ..., `lamed_s16`.
    cmap = font["cmap"].getBestCmap()
    variants_for_source: dict[str, list[str]] = {}
    for cp, info in letters.items():
        src_gname = cmap.get(cp)
        if not src_gname:
            continue
        letter_name = info.get("name")
        if not letter_name:
            continue
        vlist = [f"{letter_name}_s{n}" for n in range(1, MAX_LEVELS + 1)]
        # Only keep those that actually exist as glyphs in this build.
        gorder = set(font.getGlyphOrder())
        vlist = [v for v in vlist if v in gorder]
        if vlist:
            variants_for_source[src_gname] = vlist

    if not variants_for_source:
        return 0

    # Frank Ruhl's original MarkBase coverage MISSES three Hebrew finals
    # (ם ן ץ) — Hebrew niqqud on those letters falls through to shaper
    # defaults, which collide with the descender on ן/ץ. Backfill each
    # missing final by copying a similar-covered base's anchor structure
    # and adjusting X (to the final's bbox centre) and — for the
    # below-mark class — Y (below the descender's lowest point).
    HEBREW_FINALS_MISSING = {
        # missing_cp: (donor_cp — a letter with anchors we can borrow)
        0x05DD: 0x05DE,   # ם ← מ
        0x05DF: 0x05E0,   # ן ← נ
        0x05E5: 0x05E6,   # ץ ← צ
    }
    # Which mark classes in Frank Ruhl are BELOW-base (need descender
    # clearance on finals). From earlier inspection: class 1 (patach,
    # sheva, kubutz, kasra, chirik) is the only below class.
    BELOW_MARK_CLASSES = {1}
    glyf = font["glyf"]

    for lookup in gpos.LookupList.Lookup:
        if lookup.LookupType != 4:  # 4 = MarkToBase
            continue
        for sub in lookup.SubTable or []:
            base_glyphs = list(sub.BaseCoverage.glyphs)
            base_records = list(sub.BaseArray.BaseRecord)
            for src_gname, variants in variants_for_source.items():
                if src_gname not in base_glyphs:
                    continue
                src_idx = base_glyphs.index(src_gname)
                src_record = base_records[src_idx]
                src_anchors = src_record.BaseAnchor
                for vname in variants:
                    if vname in base_glyphs:
                        continue  # already has anchors — skip
                    v_adv = hmtx[vname][0] if vname in hmtx.metrics else None
                    if v_adv is None or v_adv <= 0:
                        continue
                    # Copy the src's anchors but shift X to center of variant advance.
                    new_anchors = []
                    for a in src_anchors:
                        if a is None:
                            new_anchors.append(None)
                            continue
                        na = ot.BaseAnchor()
                        na.Format = 1
                        # 0.42 × advance (not dead-centre): a small
                        # leftward bias gives visual balance against ל's
                        # upper-left tail and equivalent hook features on
                        # other stretchable letters. Matches the offset
                        # used for Arabic marks in _add_arabic_mark_gpos.
                        na.XCoordinate = int(v_adv * 0.58)
                        na.YCoordinate = a.YCoordinate
                        new_anchors.append(na)
                    new_rec = ot.BaseRecord()
                    new_rec.BaseAnchor = new_anchors
                    base_glyphs.append(vname)
                    base_records.append(new_rec)
                    added += 1
            # Backfill missing Hebrew finals (Frank Ruhl skipped ם ן ץ).
            for missing_cp, donor_cp in HEBREW_FINALS_MISSING.items():
                missing_g = cmap.get(missing_cp)
                donor_g = cmap.get(donor_cp)
                if not missing_g or not donor_g or missing_g in base_glyphs:
                    continue
                if donor_g not in base_glyphs:
                    continue
                donor_idx = base_glyphs.index(donor_g)
                donor_anchors = base_records[donor_idx].BaseAnchor
                # Determine the missing final's bbox for X centring +
                # descender clearance on below-marks.
                g = glyf[missing_g]
                g.recalcBounds(glyf)
                if g.numberOfContours <= 0:
                    continue
                cx = (g.xMin + g.xMax) // 2
                # If this final has a descender (yMin < -100), place
                # below-marks below the descender's lowest point.
                below_y = g.yMin - 40 if g.yMin < -100 else None
                new_anchors = []
                for cls_idx, a in enumerate(donor_anchors):
                    if a is None:
                        new_anchors.append(None)
                        continue
                    na = ot.BaseAnchor()
                    na.Format = 1
                    na.XCoordinate = cx
                    if cls_idx in BELOW_MARK_CLASSES and below_y is not None:
                        na.YCoordinate = below_y
                    else:
                        na.YCoordinate = a.YCoordinate
                    new_anchors.append(na)
                new_rec = ot.BaseRecord()
                new_rec.BaseAnchor = new_anchors
                base_glyphs.append(missing_g)
                base_records.append(new_rec)
                added += 1
            # After the widened + missing-final backfill, also ensure
            # every Hebrew consonant has a class-4 anchor above the
            # letter top so U+0307 dot-above (used for Judeo-Arabic
            # phoneme marking on כ̇ ג̇ ט̇ ץ̇) sits cleanly above the
            # ink. Only touch subtables whose ClassCount already
            # covers class 4 — otherwise editing the mark array would
            # need a matching ClassCount bump and mark-record fixup
            # which is beyond this override's scope.
            if sub.ClassCount >= 5:
                for cp in range(0x05D0, 0x05EB):
                    gname = cmap.get(cp)
                    if not gname or gname not in base_glyphs:
                        continue
                    gg = glyf[gname]
                    gg.recalcBounds(glyf)
                    if gg.numberOfContours <= 0:
                        continue
                    cx = (gg.xMin + gg.xMax) // 2
                    dot_above_y = gg.yMax + 20
                    idx = base_glyphs.index(gname)
                    record = base_records[idx]
                    while len(record.BaseAnchor) < 5:
                        record.BaseAnchor.append(None)
                    cls4 = ot.BaseAnchor()
                    cls4.Format = 1
                    cls4.XCoordinate = cx
                    cls4.YCoordinate = dot_above_y
                    record.BaseAnchor[4] = cls4
            # Rewrite coverage + array with the extended lists.
            sub.BaseCoverage.glyphs = base_glyphs
            sub.BaseArray.BaseRecord = base_records
            sub.BaseArray.BaseCount = len(base_records)
    return added


# Arabic marks we might import + their above/below classification.
# The anchor X is computed at build time from each mark's visual centre
# (bbox midpoint), NOT from Amiri's own attach anchor — the attach
# anchor puts the mark's rendered dots off-centre when the base is
# centred, whereas the visual midpoint gives a proper centred stack.
# The Y is fixed per class: 801 puts above-marks at their natural
# Amiri-designed height; -327 does the same for below-marks.
_ARABIC_MARK_CLASSES: dict[int, str] = {
    0x0651: "above",   # shadda
    0x0652: "above",   # sukun
    0x064B: "above",   # fathatan
    0x064C: "above",   # dammatan
    0x064D: "below",   # kasratan
    0x064E: "above",   # fatha
    0x064F: "above",   # damma
    0x0650: "below",   # kasra
    0x0653: "above",   # maddah
    0x0670: "above",   # dagger alif
}
_ARABIC_MARK_ANCHOR_Y = {"above": 801, "below": -327}


def _add_arabic_mark_stacking(font) -> int:
    """Add GPOS MarkToMark (Type 6) so above-vowels (fatha/damma/tanwīn/
    sukun) stack ABOVE the shadda when they follow it. Without this,
    both marks anchor to the base letter at the same X,Y and overlap.

    Places the vowel mark's visual centre + bottom at a point slightly
    above the shadda's visible top — a small upward stack matching
    Amiri's stack ordering.
    """
    from fontTools.ttLib.tables import otTables as ot

    if "GPOS" not in font:
        return 0
    gpos = font["GPOS"].table
    cmap = font["cmap"].getBestCmap()
    glyf = font["glyf"]
    glyph_order = set(font.getGlyphOrder())

    shadda = cmap.get(0x0651)
    if not shadda or shadda not in glyph_order:
        return 0
    shadda_g = glyf[shadda]
    shadda_g.recalcBounds(glyf)
    if shadda_g.numberOfContours <= 0:
        return 0

    # Marks that should stack above shadda (any additional above-mark).
    STACKING_MARKS = [
        0x064E, 0x064F, 0x064B, 0x064C, 0x0652,  # fatha, damma, fathatan, dammatan, sukun
    ]
    present = []
    for cp in STACKING_MARKS:
        g = cmap.get(cp)
        if g and g in glyph_order:
            mg = glyf[g]
            mg.recalcBounds(glyf)
            if mg.numberOfContours > 0:
                present.append((cp, g, mg))
    if not present:
        return 0

    # Build the MarkMarkPos subtable.
    sub = ot.MarkMarkPos()
    sub.Format = 1
    sub.ClassCount = 1

    # Mark1Coverage: the stacking marks (fatha, damma, etc.)
    sub.Mark1Coverage = ot.Mark1Coverage()
    sub.Mark1Coverage.glyphs = [g for _, g, _ in present]
    sub.Mark1Array = ot.Mark1Array()
    sub.Mark1Array.MarkRecord = []
    for cp, g, mg in present:
        # Attach anchor on the ATTACHING mark = its own visual centre X
        # + its bottom Y (so its bottom lines up with the base-mark's top).
        anchor = ot.MarkAnchor()
        anchor.Format = 1
        anchor.XCoordinate = (mg.xMin + mg.xMax) // 2
        anchor.YCoordinate = mg.yMin
        mr = ot.MarkRecord()
        mr.Class = 0
        mr.MarkAnchor = anchor
        sub.Mark1Array.MarkRecord.append(mr)
    sub.Mark1Array.MarkCount = len(sub.Mark1Array.MarkRecord)

    # Mark2Coverage: shadda (the base-mark to stack above).
    sub.Mark2Coverage = ot.Mark2Coverage()
    sub.Mark2Coverage.glyphs = [shadda]
    sub.Mark2Array = ot.Mark2Array()
    sub.Mark2Array.Mark2Record = []
    m2a = ot.Mark2Anchor()
    m2a.Format = 1
    m2a.XCoordinate = (shadda_g.xMin + shadda_g.xMax) // 2
    # Slightly above shadda's visible top so the vowel sits with a
    # small gap above.
    m2a.YCoordinate = shadda_g.yMax + 30
    m2r = ot.Mark2Record()
    m2r.Mark2Anchor = [m2a]
    sub.Mark2Array.Mark2Record.append(m2r)
    sub.Mark2Array.Mark2Count = 1

    # Wrap in a lookup and register with `mkmk` feature.
    lookup = ot.Lookup()
    lookup.LookupType = 6
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    new_idx = len(gpos.LookupList.Lookup) - 1

    found_mkmk = False
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag == "mkmk":
            fr.Feature.LookupListIndex.append(new_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
            found_mkmk = True
    if not found_mkmk:
        feat = ot.Feature()
        feat.LookupListIndex = [new_idx]
        feat.LookupCount = 1
        feat.FeatureParams = None
        fr = ot.FeatureRecord()
        fr.FeatureTag = "mkmk"
        fr.Feature = feat
        gpos.FeatureList.FeatureRecord.append(fr)
        gpos.FeatureList.FeatureCount = len(gpos.FeatureList.FeatureRecord)
        idx = len(gpos.FeatureList.FeatureRecord) - 1
        for sr in gpos.ScriptList.ScriptRecord:
            for ls in [sr.Script.DefaultLangSys] + [lsr.LangSys for lsr in (sr.Script.LangSysRecord or [])]:
                if ls is not None:
                    ls.FeatureIndex.append(idx)
                    ls.FeatureCount = len(ls.FeatureIndex)

    return len(present)


def _add_arabic_mark_gpos(font, config) -> int:
    """Give the imported Arabic marks (shadda, sukun, harakat) proper
    GDEF classification + a new GPOS MarkBase subtable so they anchor
    at the CENTRE of every widened Hebrew variant. Without this, the
    Arabic marks fall through to the shaper's default positioning
    (mark drawn at cursor with its own inherent offset), which puts
    them over the far right of a widened glyph rather than centred.

    Returns the count of widened variants that received a base anchor
    for the new (Arabic) mark class.
    """
    from fontTools.ttLib.tables import otTables as ot

    if "GPOS" not in font or "GDEF" not in font:
        return 0

    cmap = font["cmap"].getBestCmap()
    hmtx = font["hmtx"]
    glyph_order = set(font.getGlyphOrder())

    # Which Arabic marks are actually in this build? Compute each
    # mark's visual centre from its glyph bounds — that's the X anchor
    # we want (so the visible dots sit centred on the base's centre).
    glyf = font["glyf"]
    present: list[tuple[int, str, tuple[int, int, str]]] = []
    for cp, cls in _ARABIC_MARK_CLASSES.items():
        gname = cmap.get(cp)
        if not gname or gname not in glyph_order:
            continue
        g = glyf[gname]
        if g.numberOfContours <= 0:
            continue
        # Imported glyphs may not have bounds computed yet — recalc.
        g.recalcBounds(glyf)
        vx = (g.xMin + g.xMax) // 2
        vy = _ARABIC_MARK_ANCHOR_Y[cls]
        present.append((cp, gname, (vx, vy, cls)))
    if not present:
        return 0

    # 1. Ensure GDEF classifies each Arabic mark as class=3 (Mark).
    gdef = font["GDEF"].table
    if gdef.GlyphClassDef is None:
        gdef.GlyphClassDef = ot.GlyphClassDef()
        gdef.GlyphClassDef.classDefs = {}
    for cp, gname, _ in present:
        gdef.GlyphClassDef.classDefs[gname] = 3

    # 2. Collect base glyphs to give Arabic-mark anchors:
    #    (a) widened variants of stretchable letters (letter_s1..s16)
    #    (b) ALL natural Hebrew consonants (22 base + 5 finals) — because
    #        Amiri's marks were designed for wider Arabic bases, so on
    #        narrower Hebrew letters they land off-centre unless we
    #        override with a per-letter bbox-centre anchor.
    letters = config.get("letters") or {}
    variant_bases: list[str] = []
    for cp, info in letters.items():
        letter_name = info.get("name")
        if not letter_name:
            continue
        for n in range(1, MAX_LEVELS + 1):
            v = f"{letter_name}_s{n}"
            if v in glyph_order:
                variant_bases.append(v)
    # Natural Hebrew consonants — U+05D0..U+05EA.
    natural_bases: list[str] = []
    for cp in range(0x05D0, 0x05EB):
        gname = cmap.get(cp)
        if gname and gname in glyph_order:
            natural_bases.append(gname)
    if not variant_bases and not natural_bases:
        return 0

    # 3. Build the new MarkBase subtable — class 0 = above, class 1 = below.
    sub = ot.MarkBasePos()
    sub.Format = 1
    sub.ClassCount = 2
    sub.MarkCoverage = ot.MarkCoverage()
    sub.MarkCoverage.glyphs = [g for _, g, _ in present]
    sub.MarkArray = ot.MarkArray()
    sub.MarkArray.MarkRecord = []
    for cp, gname, (mx, my, cls) in present:
        anchor = ot.MarkAnchor()
        anchor.Format = 1
        anchor.XCoordinate = mx
        anchor.YCoordinate = my
        mr = ot.MarkRecord()
        mr.Class = 0 if cls == "above" else 1
        mr.MarkAnchor = anchor
        sub.MarkArray.MarkRecord.append(mr)
    sub.MarkArray.MarkCount = len(sub.MarkArray.MarkRecord)

    # Base anchors —
    #   • Widened variants: X = centre of the widened advance.
    #   • Natural Hebrew letters: X = the glyph's own bbox centre
    #     (so the Arabic mark sits above/below the visible ink,
    #     not over Amiri's presumed-wider default position).
    #   • Below-mark Y: -327 for normal letters, but final letters
    #     with descenders (ך ן ץ ף — bounded to yMin < -100) get a
    #     lower Y so the mark clears the descender's lowest point.
    FINAL_LETTERS = {0x05DA, 0x05DF, 0x05E3, 0x05E5}  # ך ן ף ץ (ם has no descender)
    def _below_y_for(gname: str, cp: int | None) -> int:
        # Extra clearance for finals — put the mark below the
        # descender's lowest point instead of just below baseline.
        if cp in FINAL_LETTERS:
            g = glyf[gname]
            g.recalcBounds(glyf)
            if g.numberOfContours > 0 and g.yMin < -100:
                return g.yMin - 40   # 100-unit padding below the descender
        return -327
    sub.BaseCoverage = ot.BaseCoverage()
    all_bases = list(variant_bases) + list(natural_bases)
    sub.BaseCoverage.glyphs = all_bases
    sub.BaseArray = ot.BaseArray()
    sub.BaseArray.BaseRecord = []
    # Widened variants — shift the anchor slightly left of the
    # advance midpoint (0.42 × advance instead of 0.5 × advance).
    # Purely-centred marks look off-balance against ל's upper-left
    # tail hook and equivalent hook features on other stretchable
    # letters; a small leftward bias makes marks visually anchor
    # over the widened bar's centre rather than pushing them near
    # the letter body on the right.
    for vname in variant_bases:
        adv = hmtx[vname][0]
        cx = int(adv * 0.58)
        # Above-mark Y: match the widened glyph's own top-of-ink so
        # marks clear tall features (widened lamed's arm reaches
        # y=793 same as natural ל).
        vg = glyf[vname] if vname in glyf else None
        if vg is not None:
            vg.recalcBounds(glyf)
            above_y = max(801, vg.yMax + 60) if vg.numberOfContours > 0 else 801
        else:
            above_y = 801
        above = ot.BaseAnchor(); above.Format = 1
        above.XCoordinate = cx; above.YCoordinate = above_y
        below = ot.BaseAnchor(); below.Format = 1
        below.XCoordinate = cx; below.YCoordinate = -327
        br = ot.BaseRecord()
        br.BaseAnchor = [above, below]
        sub.BaseArray.BaseRecord.append(br)
    # Then natural Hebrew letters — anchor at each letter's own bbox
    # centre so Amiri marks visually centre on the Hebrew ink.
    for gname in natural_bases:
        g = glyf[gname]
        g.recalcBounds(glyf)
        # Fallback to advance-centre if the glyph has no visible outline.
        cx = ((g.xMin + g.xMax) // 2) if g.numberOfContours > 0 else (hmtx[gname][0] // 2)
        # Reverse-look-up the codepoint for final-letter descender check.
        cp = next((c for c, n in cmap.items() if n == gname), None)
        # Above-mark Y: normally 801 works, but tall letters (ל reaches
        # y=793) sit within ~30 units of the mark's visible ink, which
        # reads as a collision. Push above_y up to the letter's yMax + 60
        # for anything tall enough to matter.
        above_y = max(801, g.yMax + 60) if g.numberOfContours > 0 else 801
        above = ot.BaseAnchor(); above.Format = 1
        above.XCoordinate = cx; above.YCoordinate = above_y
        below = ot.BaseAnchor(); below.Format = 1
        below.XCoordinate = cx; below.YCoordinate = _below_y_for(gname, cp)
        br = ot.BaseRecord()
        br.BaseAnchor = [above, below]
        sub.BaseArray.BaseRecord.append(br)
    sub.BaseArray.BaseCount = len(sub.BaseArray.BaseRecord)

    # 4. Wrap in a lookup, append to LookupList.
    gpos = font["GPOS"].table
    lookup = ot.Lookup()
    lookup.LookupType = 4
    lookup.LookupFlag = 0
    lookup.SubTable = [sub]
    lookup.SubTableCount = 1
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount = len(gpos.LookupList.Lookup)
    new_lookup_idx = len(gpos.LookupList.Lookup) - 1

    # 5. Wire the new lookup into the `mark` feature (create if missing).
    mark_feature_indices: list[int] = []
    for i, fr in enumerate(gpos.FeatureList.FeatureRecord):
        if fr.FeatureTag == "mark":
            fr.Feature.LookupListIndex.append(new_lookup_idx)
            fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
            mark_feature_indices.append(i)
    if not mark_feature_indices:
        feat = ot.Feature()
        feat.LookupListIndex = [new_lookup_idx]
        feat.LookupCount = 1
        feat.FeatureParams = None
        fr = ot.FeatureRecord()
        fr.FeatureTag = "mark"
        fr.Feature = feat
        gpos.FeatureList.FeatureRecord.append(fr)
        gpos.FeatureList.FeatureCount = len(gpos.FeatureList.FeatureRecord)
        idx = len(gpos.FeatureList.FeatureRecord) - 1
        for sr in gpos.ScriptList.ScriptRecord:
            for ls_holder in [sr.Script.DefaultLangSys] + [
                lsr.LangSys for lsr in (sr.Script.LangSysRecord or [])
            ]:
                if ls_holder is not None:
                    ls_holder.FeatureIndex.append(idx)
                    ls_holder.FeatureCount = len(ls_holder.FeatureIndex)

    return len(all_bases)


def _splice_original_gsub_back(font, original_gsub_bytes):
    """After feaLib REBUILT the GSUB with only our stretch features,
    splice the source font's original GSUB (init/medi/fina/ccmp/rlig/...)
    back in. Preserves cursive joining for Syriac and non-critical
    features for Hebrew.

    Merge strategy: original lookups get appended AFTER our new lookups;
    all references (lookup indices in features, in chained subtables,
    and in script lang-sys feature indices) are shifted accordingly.
    """
    from fontTools.ttLib import newTable

    # Decompile the original GSUB bytes into an OT table structure.
    original_gsub = newTable("GSUB")
    original_gsub.decompile(original_gsub_bytes, font)

    new_table = font["GSUB"].table
    orig_table = original_gsub.table

    orig_lookups = list(orig_table.LookupList.Lookup) if orig_table.LookupList else []
    orig_features = list(orig_table.FeatureList.FeatureRecord) if orig_table.FeatureList else []
    orig_scripts = list(orig_table.ScriptList.ScriptRecord) if orig_table.ScriptList else []

    n_new_lookups = len(new_table.LookupList.Lookup) if new_table.LookupList else 0
    n_new_features = len(new_table.FeatureList.FeatureRecord) if new_table.FeatureList else 0

    # 1. Shift internal lookup references inside each original lookup
    #    (Type 5 / 6 chained lookups embed lookup indices in their subtables).
    for lookup in orig_lookups:
        for st in lookup.SubTable or []:
            for attr in ("SubstLookupRecord", "PosLookupRecord"):
                recs = getattr(st, attr, None)
                if not recs:
                    continue
                for rec in recs:
                    rec.LookupListIndex += n_new_lookups

    # 2. Append original lookups AFTER our new lookups.
    if new_table.LookupList is None:
        new_table.LookupList = ot.LookupList()
        new_table.LookupList.Lookup = []
    new_table.LookupList.Lookup.extend(orig_lookups)
    new_table.LookupList.LookupCount = len(new_table.LookupList.Lookup)

    # 3. Shift lookup indices inside each original feature, then append.
    for fr in orig_features:
        fr.Feature.LookupListIndex = [i + n_new_lookups for i in fr.Feature.LookupListIndex]
        fr.Feature.LookupCount = len(fr.Feature.LookupListIndex)
    if new_table.FeatureList is None:
        new_table.FeatureList = ot.FeatureList()
        new_table.FeatureList.FeatureRecord = []
    new_table.FeatureList.FeatureRecord.extend(orig_features)
    new_table.FeatureList.FeatureCount = len(new_table.FeatureList.FeatureRecord)

    # 4. Merge script records — feature indices reference the feature list
    #    (which now has our new features first, then original features).
    #    Original scripts' feature indices must be shifted by n_new_features.
    def _shift_langsys(ls):
        if ls is None:
            return
        ls.FeatureIndex = [i + n_new_features for i in ls.FeatureIndex]
        ls.FeatureCount = len(ls.FeatureIndex)

    for sr in orig_scripts:
        _shift_langsys(sr.Script.DefaultLangSys)
        for lsr in (sr.Script.LangSysRecord or []):
            _shift_langsys(lsr.LangSys)

    # Merge into existing script list. If a script tag is already present
    # (feaLib made one for our features), MERGE the LangSys feature indices;
    # else append the whole ScriptRecord.
    if new_table.ScriptList is None:
        new_table.ScriptList = ot.ScriptList()
        new_table.ScriptList.ScriptRecord = []
    existing_scripts = {sr.ScriptTag: sr for sr in new_table.ScriptList.ScriptRecord}
    for sr in orig_scripts:
        if sr.ScriptTag in existing_scripts:
            existing = existing_scripts[sr.ScriptTag]
            if existing.Script.DefaultLangSys and sr.Script.DefaultLangSys:
                existing.Script.DefaultLangSys.FeatureIndex.extend(sr.Script.DefaultLangSys.FeatureIndex)
                existing.Script.DefaultLangSys.FeatureCount = len(existing.Script.DefaultLangSys.FeatureIndex)
            elif sr.Script.DefaultLangSys:
                existing.Script.DefaultLangSys = sr.Script.DefaultLangSys
            existing.Script.LangSysRecord = (existing.Script.LangSysRecord or []) + (sr.Script.LangSysRecord or [])
            existing.Script.LangSysCount = len(existing.Script.LangSysRecord)
        else:
            new_table.ScriptList.ScriptRecord.append(sr)
    new_table.ScriptList.ScriptCount = len(new_table.ScriptList.ScriptRecord)


def build_one(config: dict) -> int:
    # Per-font stretch trigger codepoint. Default is Hebrew nun hafukha for
    # Hebrew scripts; Syriac fonts override to Arabic tatweel U+0640 so the
    # trigger stays in the Syriac shaping run (script=Common).
    global STRETCH_CODEPOINT, STRETCH_GLYPH
    STRETCH_CODEPOINT = config.get("stretch_codepoint", 0x05C6)
    STRETCH_GLYPH = f"uni{STRETCH_CODEPOINT:04X}"
    src_path = FONTS_DIR / config["source"]
    out_path = FONTS_DIR / config["output"]
    family = config["family"]
    postscript = config["postscript"]
    internal_id = config["internal_id"]
    step = int(config["step"])
    letters = config["letters"]

    print(f"\n=== Building {family} (from {config['source']}) ===")
    if not src_path.exists():
        print(f"  ! Missing source font {src_path}")
        return 1

    font = TTFont(str(src_path))

    # --- 1. Trigger glyph. Zero-advance placeholder for chain-substitution:
    # our GSUB ligature consumes (letter, N × trigger) → stretched variant.
    #
    # Three cases:
    #  1. Codepoint not yet in font's cmap (Hebrew fonts without U+05C6
    #     mapped): install our 1×1 invisible placeholder.
    #  2. Codepoint already present + font is CURSIVE (has positional
    #     forms — Noto Sans Syriac, Idiqlat, etc.): preserve the font's
    #     natural tatweel glyph. Auto-justify inserts tatweels BETWEEN
    #     joining letters and the natural tatweel bridges them into a
    #     horizontal bar — the whole point for cursive scripts.
    #  3. Codepoint present + font is NON-CURSIVE (Nohadra): overwrite
    #     with 1×1 placeholder. Non-cursive fonts widen via our ligature
    #     which consumes every tatweel into a widened letter variant.
    #     Unmatched tatweels showing at baseline height (y≈0-101) would
    #     mismatch the widened bar height (y≈303), producing the
    #     "gaps in bars" artifact from image 43.
    #
    # `override_trigger_glyph` config field forces case 3 for non-cursive
    # fonts that happen to have the codepoint in their source cmap.
    order = font.getGlyphOrder()
    force_override = config.get("override_trigger_glyph", False)
    if STRETCH_GLYPH not in order or force_override:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0)); pen.lineTo((1, 0)); pen.lineTo((1, 1)); pen.lineTo((0, 1)); pen.closePath()
        trigger_glyph = pen.glyph()
        if STRETCH_GLYPH not in order:
            order.append(STRETCH_GLYPH)
            font.setGlyphOrder(order)
        font["glyf"][STRETCH_GLYPH] = trigger_glyph
        font["hmtx"].metrics[STRETCH_GLYPH] = (40, 0)
        # Map the codepoint.
        for t in font["cmap"].tables:
            if t.isUnicode() or t.platformID == 3:
                t.cmap[STRETCH_CODEPOINT] = STRETCH_GLYPH

    # --- 2. For each stretch letter, generate MAX_LEVELS variant glyphs.
    # letter_variants: src_glyph -> {"variants": [s1..sMAX], "aliases": [...]}
    # Aliases are extra source glyphs (composed presentation forms) that
    # should also trigger the same stretch (see LETTERS dict for details).
    letter_variants: dict[str, dict] = {}
    # src_glyph -> (segment_glyph_name, last_variant_name) — populated for
    # bar-class letters with "overflow": True (simple single-segment chain).
    overflow_segments: dict[str, tuple[str, str]] = {}
    # src_glyph -> (start, intermediate, tail, last_variant) — populated
    # for arm-class letters with "overflow": True (start/tail/intermediate
    # three-glyph chain that migrates the arm to the leftmost end).
    overflow_chains: dict[str, tuple[str, str, str, str]] = {}
    cmap = font.getBestCmap()

    for cp, info in letters.items():
        letter_name = str(info["name"])
        letter_class = str(info.get("class", "bar"))
        bar_bottom = int(info.get("bar_bottom", 440))  # type: ignore
        bar_top = int(info.get("bar_top", 620))  # type: ignore
        arm = info.get("arm_min_y")
        arm_min_y = int(arm) if isinstance(arm, int) else None
        leg = info.get("leg_max_y")
        leg_max_y = int(leg) if isinstance(leg, int) else None
        x_cut = info.get("x_cutoff")
        x_cut_int = int(x_cut) if isinstance(x_cut, int) else None
        und_y = info.get("underside_y_max")
        underside_y_max = int(und_y) if isinstance(und_y, int) else None
        und_x = info.get("underside_x_min")
        underside_x_min = int(und_x) if isinstance(und_x, int) else None
        # Resolve alias codepoints (Hebrew Presentation Forms) to the
        # actual glyph names this font uses. Different fonts have different
        # naming conventions (uniFB33 vs daleddagesh).
        alias_cps_raw = info.get("alias_codepoints", [])
        alias_cps = list(alias_cps_raw) if isinstance(alias_cps_raw, list) else []
        aliases = [cmap[a] for a in alias_cps if a in cmap]
        shift_contours_raw = info.get("shift_contours")
        shift_contours = list(shift_contours_raw) if isinstance(shift_contours_raw, list) else None
        src_glyph = cmap.get(cp)
        if not src_glyph:
            print(f"  skip {letter_name}: not in cmap")
            continue

        # Helper to build MAX_LEVELS stretched variants from ANY source glyph
        # (isolated or positional form). Positional forms in cursive fonts
        # (Syriac beth.init/.medi/.fina, etc.) need their OWN stretched
        # variants so cursive joining chains stay intact — the .init form
        # widened must still have its left-joining stub, else adjacent
        # letters render dangling stubs into the widened body.
        def build_form_variants(src_name: str, variant_prefix: str) -> list[str]:
            if src_name not in font["hmtx"].metrics:
                return []
            base_adv = font["hmtx"].metrics[src_name][0]
            forms_variants: list[str] = []
            order = font.getGlyphOrder()
            for n in range(1, MAX_LEVELS + 1):
                vn = f"{variant_prefix}_s{n}"
                shift_ = step * n
                new_g = stretch_glyph(
                    font, src_name, shift_,
                    letter_class=letter_class,
                    bar_bottom=bar_bottom, bar_top=bar_top,
                    arm_min_y=arm_min_y, leg_max_y=leg_max_y,
                    x_cutoff=x_cut_int,
                    shift_contours=shift_contours,
                    underside_y_max=underside_y_max,
                    underside_x_min=underside_x_min,
                )
                lsb_mode_ = config.get("lsb_mode", "shift")
                if lsb_mode_ == "mono":
                    for i in range(len(new_g.coordinates)):
                        x, y = new_g.coordinates[i]
                        new_g.coordinates[i] = (x + shift_, y)
                    new_g.recalcBounds(font["glyf"])
                    new_l = new_g.xMin
                elif lsb_mode_ == "natural":
                    new_l = new_g.xMin
                else:
                    new_l = 0
                new_adv = base_adv + shift_
                # Non-cursive block fonts (Nohadra) have significant natural
                # right padding baked into base advance — visible whitespace
                # between letters. For plain natural text that's fine, but
                # widened letters need their bars to butt up to the next
                # letter's bar with only a hairline seam. Add a "trailing
                # bar cap" from natural xMax to the advance boundary at
                # bar height, so the widened letter's outline actually
                # fills its advance. Governed by `fill_advance_with_bar`
                # config field which encodes {bar_bottom, bar_top}.
                fill_bar = config.get("fill_advance_with_bar")
                if fill_bar and new_adv > new_g.xMax + 2:
                    bb, bt = int(fill_bar["bar_bottom"]), int(fill_bar["bar_top"])
                    from fontTools.pens.ttGlyphPen import TTGlyphPen as _Pen
                    cap = _Pen(None)
                    cap.moveTo((new_g.xMax, bb))
                    cap.lineTo((new_adv, bb))
                    cap.lineTo((new_adv, bt))
                    cap.lineTo((new_g.xMax, bt))
                    cap.closePath()
                    cap_g = cap.glyph()
                    # Merge cap contours into the variant glyph.
                    orig_coords = list(new_g.coordinates)
                    orig_flags = list(new_g.flags)
                    orig_ends = list(new_g.endPtsOfContours)
                    orig_pt_count = len(orig_coords)
                    for c, ff in zip(cap_g.coordinates, cap_g.flags):
                        orig_coords.append(c)
                        orig_flags.append(ff)
                    for ep in cap_g.endPtsOfContours:
                        orig_ends.append(orig_pt_count + ep)
                    from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
                    new_g.coordinates = GlyphCoordinates(orig_coords)
                    import array as _array
                    new_g.flags = _array.array("B", orig_flags)
                    new_g.endPtsOfContours = orig_ends
                    new_g.numberOfContours = len(orig_ends)
                    new_g.recalcBounds(font["glyf"])
                font["glyf"][vn] = new_g
                font["hmtx"].metrics[vn] = (new_adv, new_l)
                if vn not in order:
                    order.append(vn)
                font.setGlyphOrder(order)
                forms_variants.append(vn)
            return forms_variants

        base_advance = font["hmtx"].metrics[src_glyph][0]
        variants: list[str] = []
        for n in range(1, MAX_LEVELS + 1):
            variant_name = f"{letter_name}_s{n}"
            total_shift = step * n
            new_glyph = stretch_glyph(
                font, src_glyph, total_shift,
                letter_class=letter_class,
                bar_bottom=bar_bottom, bar_top=bar_top,
                arm_min_y=arm_min_y, leg_max_y=leg_max_y,
                x_cutoff=x_cut_int,
                shift_contours=shift_contours,
                underside_y_max=underside_y_max,
                underside_x_min=underside_x_min,
            )
            # Grow advance proportionally: stretched letter takes more
            # horizontal space so neighbors don't overlap its extended arm.
            # lsb_mode controls how the renderer positions the body:
            #   "shift"   (default): lsb=0 → renderer translates right by
            #              (lsb - xMin) = -xMin, pulling the body close to
            #              the previous letter and letting the kashida
            #              visually bridge to it. Right for proportional
            #              fonts where the source xMin is small/positive.
            #   "natural": lsb=xMin → no translation, body stays at its
            #              source-coord position. Required for fonts whose
            #              source already has very negative xMin (e.g. Stam
            #              Ashkenaz lamed at xMin=-300): with lsb=0 the
            #              body translates so far right it intersects the
            #              previous letter.
            #   "mono":    translate the entire stretched glyph rightward
            #              by exactly `shift`. The advance grows by `shift`,
            #              so this preserves the body's offset from the
            #              advance's right edge — the body stays where it
            #              would naturally sit relative to the NEXT letter
            #              on its right. The arm and kashida extend left
            #              into the new space. Required for (a) mono fonts
            #              (body lands in the rightmost cell, kashida fills
            #              the extra cells leftward) and (b) any font whose
            #              source has very negative xMin (e.g. Stam Ashkenaz
            #              lamed at -300), where "shift" overshoots and
            #              "natural" leaves a `shift`-sized gap to the next
            #              letter.
            lsb_mode = config.get("lsb_mode", "shift")
            if lsb_mode == "mono":
                for i in range(len(new_glyph.coordinates)):
                    x, y = new_glyph.coordinates[i]
                    new_glyph.coordinates[i] = (x + total_shift, y)
                new_glyph.recalcBounds(font["glyf"])
                new_lsb = new_glyph.xMin
            elif lsb_mode == "natural":
                new_lsb = new_glyph.xMin
            else:
                new_lsb = 0
            font["glyf"][variant_name] = new_glyph
            font["hmtx"].metrics[variant_name] = (base_advance + total_shift, new_lsb)
            if variant_name not in order:
                order.append(variant_name)
            font.setGlyphOrder(order)
            variants.append(variant_name)
        # Positional-form variants. Cursive scripts (Syriac, Arabic) run
        # init/medi/fina/med2/fin2/fin3 lookups BEFORE `liga`, so by the
        # time our ligature fires the letter's glyph is `uni0712.init`
        # (or .medi/.fina) — no longer `uni0712`. Earlier we mapped these
        # forms to the ISOLATED widened glyph, but that produced dangling
        # joining stubs on adjacent letters (they'd been shaped expecting
        # to connect to init's left stub, which isn't there on isolated).
        # Instead build a SEPARATE stretched set for each positional form
        # from THAT form's outline; joining chains stay intact at every
        # stretch level.
        POSITIONAL_SUFFIXES = (".init", ".medi", ".fina", ".isol",
                               ".init.short", ".medi.short", ".fina.short",
                               ".initB", ".mediB", ".finaB",
                               ".init2", ".medi2", ".fina2",
                               ".fin2", ".fin3", ".med2")
        positional_variants: dict[str, list[str]] = {}
        for suffix in POSITIONAL_SUFFIXES:
            positional = src_glyph + suffix
            if positional in font.getGlyphOrder():
                pos_prefix = f"{letter_name}{suffix}"
                pos_vars = build_form_variants(positional, pos_prefix)
                if pos_vars:
                    positional_variants[positional] = pos_vars

        letter_variants[src_glyph] = {
            "variants": variants,
            "aliases": aliases,
            "positional_variants": positional_variants,
        }
        alias_note = f" + aliases {aliases}" if aliases else ""
        pos_note = f" + positional-form sets [{', '.join(positional_variants.keys())}]" if positional_variants else ""
        print(f"  {letter_name} (class {letter_class}): {MAX_LEVELS} variants × step={step}{alias_note}{pos_note}")

        # Overflow tatweel-style chain. Default-enabled for bar/arm class
        # letters in shift-mode fonts (the math for natural/mono modes
        # still needs derivation, so those are skipped). Leg/box classes
        # still TODO. Per-letter `"overflow": False` opts out.
        is_shift = config.get("lsb_mode", "shift") == "shift"
        overflow_default = letter_class in ("bar", "arm") and is_shift
        overflow_enabled = info.get("overflow", overflow_default)
        if overflow_enabled and is_shift and letter_class in ("bar", "arm"):
            start, intermed, tail = build_overflow_chain(
                font, src_glyph, variants[-1], info, step, MAX_LEVELS,
            )
            overflow_chains[src_glyph] = (start, intermed, tail, variants[-1])
            print(f"    + overflow chain ({letter_class}): start={start}, int={intermed}, tail={tail}")

    # --- 2a. Drop variable-font tables. Noto Sans/Serif Hebrew (and other
    # Google variable fonts) ship with fvar/gvar/HVAR/STAT/avar. When we
    # add stretch variant glyphs to the font, gvar's per-glyph variation
    # records no longer match glyphCount → font is invalid and the new
    # glyphs render as blanks. We don't need variable axes for static
    # stretch derivatives, so drop the variable-font tables entirely.
    for tag in ("fvar", "gvar", "avar", "cvar", "HVAR", "VVAR", "MVAR", "STAT"):
        if tag in font:
            del font[tag]

    # --- 2b. Optionally import Arabic combining marks (shaddah, tanwin,
    # sukun) so the same font can render Hebrew base + Arabic mark cleanly.
    import_marks = config.get("import_marks", [])
    if import_marks:
        n = import_arabic_marks(font, list(import_marks))
        print(f"  imported {n} Arabic mark glyphs from Amiri")
    # --- 2c. Custom two-dots-above (U+0308) — designed for Hebrew letter
    # heights. Lets users place dots above Hebrew Heh to evoke Arabic ة.
    if add_two_dots_above(font):
        print(f"  installed two-dots-above (U+0308)")

    # --- 3. Wire up GSUB ligatures via feaLib (Adobe Feature File syntax).
    #
    # IMPORTANT: Use MULTI-COMPONENT ligatures, not a chain. HarfBuzz's
    # ligature substitution fires once per cursor position then advances
    # PAST the new ligature, so (lam, E010) → lam_s1 followed by
    # (lam_s1, E010) → lam_s2 never chains — the shaper doesn't reconsider
    # the just-emitted glyph. Instead, emit rules for every count:
    #   sub lam E010 E010 E010 E010 E010 E010 by lam_s6;
    #   sub lam E010 E010 E010 E010 E010 by lam_s5;
    #   ...
    # and list longest first so greedy matching picks the biggest chain.
    #
    # Also declare `languagesystem hebr dflt;` so the feature is registered
    # under the Hebrew script, not just DFLT.
    # `lookupflag IgnoreMarks;` tells the shaper to skip over niqqud
    # (combining marks in GDEF Mark class) when matching ligature components.
    # Without it, a letter with its own niqqud (e.g. "תּ" = ת + dagesh)
    # followed by triggers won't match because the dagesh sits between the
    # letter and the first trigger. With IgnoreMarks, (ת + [skip dagesh] +
    # U+05C6 × N) → tav_sN correctly.
    # Pick the OpenType script tag. Hebrew fonts use `hebr`; Syriac fonts
    # use `syrc`. If a config declares `language_system`, use that; else
    # default to Hebrew. Both scripts share the same underlying stretch
    # machinery — only the `languagesystem` line changes.
    script_tag = config.get("language_system", "hebr")
    fea_lines = [
        "languagesystem DFLT dflt;",
        f"languagesystem {script_tag} dflt;",
        "",
    ]
    # Helper lookups for the overflow chain. Defined OUTSIDE the feature
    # block so they can be invoked from chained-context rules. Each
    # overflow letter gets its own `kashida → bar_segment` (or → tail)
    # lookup so we can reference the per-letter glyph by name.
    for src_glyph, (seg_name, _last) in overflow_segments.items():
        fea_lines.append(f"lookup k_to_{seg_name} {{")
        fea_lines.append(f"    sub {STRETCH_GLYPH} by {seg_name};")
        fea_lines.append(f"}} k_to_{seg_name};")
        fea_lines.append("")
    for src_glyph, (_start, _int, tail, _last) in overflow_chains.items():
        fea_lines.append(f"lookup k_to_{tail} {{")
        fea_lines.append(f"    sub {STRETCH_GLYPH} by {tail};")
        fea_lines.append(f"}} k_to_{tail};")
        fea_lines.append("")
    fea_lines += [
        "feature liga {",
        "    lookupflag IgnoreMarks;",
    ]
    total_rules = 0
    for src_glyph, payload in letter_variants.items():
        variants = payload["variants"]
        aliases = payload.get("aliases", [])
        positional_variants = payload.get("positional_variants", {})
        # Isolated form + non-positional aliases (dagesh presentation forms)
        # both map to the isolated stretched set.
        isolated_firsts = [src_glyph] + [a for a in aliases if a in font.getGlyphOrder()]
        for first in isolated_firsts:
            for n in range(len(variants), 0, -1):
                comps = " ".join([first] + [STRETCH_GLYPH] * n)
                fea_lines.append(f"    sub {comps} by {variants[n - 1]};")
                total_rules += 1
        # Each positional form maps to its OWN per-form stretched set so
        # the joining stub survives the widening.
        for pos_form, pos_vars in positional_variants.items():
            for n in range(len(pos_vars), 0, -1):
                comps = " ".join([pos_form] + [STRETCH_GLYPH] * n)
                fea_lines.append(f"    sub {comps} by {pos_vars[n - 1]};")
                total_rules += 1
    # --- Overflow chain. AFTER all the multi-component ligatures so the
    # max-level ligature consumes its full quota of kashidas first, then
    # leftover kashidas get tatweel-substituted into bar segments. The
    # second rule (`sub bar_segment U+05C6'`) is what makes the chain
    # arbitrarily long: each substitution puts a bar_segment before the
    # next kashida, which then triggers the same lookup. HarfBuzz processes
    # chained-context substitutions left-to-right with re-entry, so the
    # cascade resolves in one pass.
    overflow_rules = 0
    for src_glyph, (seg_name, last_variant) in overflow_segments.items():
        fea_lines.append(f"    sub {last_variant} {STRETCH_GLYPH}' lookup k_to_{seg_name};")
        fea_lines.append(f"    sub {seg_name} {STRETCH_GLYPH}' lookup k_to_{seg_name};")
        overflow_rules += 2
    # Arm-class overflow chain (lamed). The "extend" rules and the "demote"
    # rule must live in SEPARATE lookups — within one lookup the shaper
    # makes a single left-to-right pass, so without splitting, all the new
    # tails would already be there but the demote rule would miss them.
    # Splitting forces a second pass after extend completes.
    #
    # Pass 1 (extend, single lookup):
    #   [lamed_s16, k, k, k] → [start, tail, tail, tail]
    # Pass 2 (demote, separate lookup):
    #   → [start, intermediate, intermediate, tail]
    # The arm rides with the LAST tail = leftmost segment in display.
    fea_lines.append("} liga;")
    for src_glyph, (start, intermed, tail, last_variant) in overflow_chains.items():
        fea_lines.append("")
        fea_lines.append(f"feature liga {{")
        fea_lines.append(f"    lookupflag IgnoreMarks;")
        fea_lines.append(f"    sub {last_variant}' {STRETCH_GLYPH} by {start};")
        fea_lines.append(f"    sub {start} {STRETCH_GLYPH}' lookup k_to_{tail};")
        fea_lines.append(f"    sub {tail} {STRETCH_GLYPH}' lookup k_to_{tail};")
        fea_lines.append(f"}} liga;")
        fea_lines.append("")
        fea_lines.append(f"feature liga {{")
        fea_lines.append(f"    lookupflag IgnoreMarks;")
        fea_lines.append(f"    sub {tail}' {tail} by {intermed};")
        fea_lines.append(f"}} liga;")
        overflow_rules += 4
    fea_src = "\n".join(fea_lines)
    # addOpenTypeFeaturesFromString REPLACES the entire GSUB table with a
    # fresh build from the FEA source — losing every existing feature the
    # source font already had (ccmp, locl, init, medi, fina, rlig, stch,
    # ...). For Syriac and other cursive scripts, init/medi/fina/rlig are
    # what produce cursive joining; without them each letter renders as
    # its isolated form and the word doesn't connect.
    #
    # Save the original GSUB, let feaLib build the new one, then splice
    # the original's lookups and features back in with shifted indices.
    original_gsub_bytes = None
    if "GSUB" in font:
        try:
            original_gsub_bytes = font["GSUB"].compile(font)
        except Exception:
            # Some source fonts have broken GSUB — skip preservation.
            original_gsub_bytes = None
    # feaLib REPLACES both GDEF and GPOS in addition to GSUB. Save the raw
    # binaries so we can restore them after — GPOS carries the mark-to-base
    # anchors that position Hebrew niqqud under the correct letter body,
    # and GDEF classifies mark glyphs (needed for `liga` to look past marks
    # and for the shaper to know what's a base vs mark).
    original_gpos_bytes = None
    original_gdef_bytes = None
    if "GPOS" in font:
        try: original_gpos_bytes = font["GPOS"].compile(font)
        except Exception: pass
    if "GDEF" in font:
        try: original_gdef_bytes = font["GDEF"].compile(font)
        except Exception: pass
    addOpenTypeFeaturesFromString(font, fea_src)
    if original_gsub_bytes is not None:
        _splice_original_gsub_back(font, original_gsub_bytes)
    if original_gpos_bytes is not None:
        _restore_table(font, "GPOS", original_gpos_bytes)
    if original_gdef_bytes is not None:
        _restore_table(font, "GDEF", original_gdef_bytes)
    # Extend the restored GPOS with anchor entries for our new widened
    # variants so niqqud attaches at the CENTER of each widened advance,
    # not at the original letter body's position (which after mono
    # translation ends up flush right in the widened glyph).
    if original_gpos_bytes is not None:
        added = _add_widened_variant_anchors(font, config)
        if added:
            print(f"  added GPOS mark anchors on {added} widened variants (centered under advance)")
        # Also add Arabic mark anchors (shadda, sukun, harakat) if we
        # imported them. Same centering as Hebrew niqqud — advance/2.
        if config.get("import_marks"):
            arb_added = _add_arabic_mark_gpos(font, config)
            if arb_added:
                print(f"  added Arabic mark GPOS anchors on {arb_added} widened variants")
            stack_added = _add_arabic_mark_stacking(font)
            if stack_added:
                print(f"  added Arabic mark-to-mark stacking for {stack_added} above-vowels")
    overflow_note = f" + {overflow_rules} overflow chain rules" if overflow_rules else ""
    print(f"  wired {total_rules} multi-component ligature rules via feaLib{overflow_note}")

    # --- 4. Rename per OFL/GPL §3 (must rename derivatives).
    name_table = font["name"]
    RENAMES = {
        1: family,
        4: family + " Regular",
        6: postscript,
        16: family,
        17: "Regular",
    }
    plat_variants = [(3, 1, 0x409), (1, 0, 0x0)]
    for name_id, value in RENAMES.items():
        for plat in plat_variants:
            name_table.setName(value, name_id, plat[0], plat[1], plat[2])
    for plat in plat_variants:
        name_table.setName(internal_id, 3, plat[0], plat[1], plat[2])

    # --- 5. Save.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(out_path))
    size_kb = out_path.stat().st_size / 1024
    print(f"  ✓ Wrote {out_path.name} ({size_kb:.0f} KB)")
    return 0


def main() -> int:
    """Build every font in CONFIGS. Failures don't stop the loop — each
    config is independent."""
    failures = 0
    for cfg in CONFIGS:
        try:
            rc = build_one(cfg)
            if rc != 0:
                failures += 1
        except Exception as e:
            print(f"  ! Build failed for {cfg.get('id')}: {e}")
            failures += 1
    print(f"\nDone. {len(CONFIGS) - failures}/{len(CONFIGS)} fonts built.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
