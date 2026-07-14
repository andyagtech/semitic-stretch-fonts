# Semitic Stretch Fonts

Custom Semitic-script fonts with **kashida-style horizontal widening ligatures**
for scribal column justification, plus **GPOS mark-positioning fixes** that
centre Arabic vowels stacked on Hebrew consonants for Judeo-Arabic use.

19 fonts covering **Hebrew, Syriac, and Ethiopic (Ge'ez)**.

Live demo: <https://semitic-search.andy-barr.com/font-lab>

---

## What these fonts do

Three sets of additions on top of well-known open-source Semitic fonts:

### 1. Kashida-style horizontal widening

Each font has a GSUB ligature that turns `letter + N × trigger` into a
horizontally-widened variant of the letter. Traditional Torah scribes
widen specific letters (**ד ה ל ם ר ת**) to justify columns; these fonts
bake that widening into 16 stretch levels per letter (per positional
form for cursive scripts). Same mechanism ported to Syriac (**ܐ ܒ ܕ ܗ ܘ ܡ ܣ ܪ ܫ ܬ**)
and to Ge'ez (**መ ጠ ሠ ሐ ወ** consonant series × 7 vowel orders each).

### 2. Trigger characters

- **Hebrew**: **U+05C6** HEBREW PUNCTUATION NUN HAFUKHA
- **Syriac + Ethiopic**: **U+2060** WORD JOINER (script=Common, stays in the run)

For the Syriac cursive fonts, U+0640 (Arabic tatweel) is also preserved as
the font's native cursive-bridging kashida.

### 3. Centered mark positioning for cross-script use

The Hebrew stretch fonts import Arabic combining marks (shadda, sukun,
harakat, tanwīn) from Amiri and add GPOS anchor entries so:

- Hebrew niqqud (patach, kubutz, chirik, sheva) centres on the widened
  variant's advance instead of clinging to the natural letter position.
- Arabic marks stacked on Hebrew consonants centre on the letter's
  visual midpoint (needed for Judeo-Arabic text like Saadia Gaon's
  Tafsir).
- Final letters (**ך ן ץ ף**) get descender-clearance adjustment for
  below-marks and a proper anchor for U+0307 (dot-above, used by
  Sefaria/Tiberian convention on כ̇ ג̇ ט̇ ץ̇).
- MarkToMark stacking so `shadda + fatha` no longer overlap.

---

## Fonts included

### Hebrew (15 fonts)

| Font | Source | License |
|------|--------|---------|
| Semitic Stretch Hebrew | Frank Ruhl Libre | OFL |
| Semitic Stretch Keter Aram Tsova | Culmus | GPL-2.0 |
| Semitic Stretch Shmulik CLM | Culmus | GPL-2.0 |
| Semitic Stretch Hillel CLM | Culmus | GPL-2.0 |
| Semitic Stretch Gladia CLM | Culmus | GPL-2.0 |
| Semitic Stretch Noto Sans Hebrew | Google Noto | OFL |
| Semitic Stretch Noto Serif Hebrew | Google Noto | OFL |
| Semitic Stretch Shofar | Culmus | GPL-2.0 |
| Semitic Stretch FreeMono | GNU FreeFont | GPL-2.0 |
| Semitic Stretch Nachlieli CLM | Culmus | GPL-2.0 |
| Semitic Stretch Miriam Mono CLM | Culmus | GPL-2.0 |
| Semitic Stretch Ezra SIL SR | SIL | OFL |
| Semitic Stretch Stam Ashkenaz CLM | Culmus | GPL-2.0 |
| Semitic Stretch Shlomo SemiStam | Open Siddur | OFL |
| Semitic Stretch Rashi | Google Noto Rashi Hebrew | OFL |

### Syriac (3 fonts)

| Font | Source | License |
|------|--------|---------|
| Semitic Stretch Noto Sans Syriac | Google Noto | OFL |
| Semitic Stretch Nohadra Sapna | Sargis Yonan | OFL |
| Semitic Stretch Nohadra Amedia | Sargis Yonan | OFL |

### Ethiopic (1 font)

| Font | Source | License |
|------|--------|---------|
| Semitic Stretch Noto Serif Ethiopic | Google Noto | OFL |

---

## Installation

Download the `.ttf` file for whichever font you want and install it like
any other font (double-click on macOS; drop into `Fonts` folder on Linux/Windows).

### Web use

```html
<style>
  @font-face {
    font-family: 'Semitic Stretch Hebrew';
    src: url('SemiticStretchHebrew.ttf') format('truetype');
  }
  .my-scroll {
    font-family: 'Semitic Stretch Hebrew', serif;
    font-feature-settings: 'liga' 1, 'calt' 1;
  }
</style>
```

Then insert stretch triggers between letters to widen them:

```
בְּרֵאשִׁ׆׆׆ית      ← Hebrew: 3× U+05C6 after שׁ
ܪ⁠⁠⁠ܝܫܝܬ         ← Syriac: 3× U+2060 after ܪ
መ⁠⁠⁠              ← Ethiopic: 3× U+2060 after መ
```

---

## Licensing

Each font retains the license of its upstream source. Two licenses cover
the whole set — full texts under `licenses/`:

- **OFL** (SIL Open Font License 1.1) — `licenses/OFL.txt`
- **GPL-2.0** — `licenses/GPL-2.0.txt`

The `manifest.json` at the repo root records the license for every font.

**OFL fonts** may be freely used, embedded, and redistributed. Derivative
works must be under OFL and must not use the reserved font name of the
upstream family.

**GPL fonts** may be freely used and redistributed under the same license.
Derivatives must remain GPL.

---

## Credits

The widening + mark-positioning derivatives are original work built on top
of the following original fonts and their designers/foundries:

- **Frank Ruhl Libre** — Yanek Iontef, based on original Frank Ruhl (1908)
- **Culmus fonts** (Keter Aram Tsova, Shmulik, Hillel, Gladia, Shofar,
  Nachlieli, Miriam Mono, Stam Ashkenaz) — Culmus Project, Yoram Gnat, Maxim Iorsh
- **Noto Hebrew / Serif / Syriac / Serif Ethiopic** — Google's Noto project
- **Ezra SIL SR** — SIL Global (Jonathan Kew, Vic Gaultney)
- **Shlomo SemiStam** — Open Siddur project
- **Nohadra Syriac Sapna / Amedia** — Sargis Yonan
- **GNU FreeMono** — Free Software Foundation

Amiri (imported combining marks + anchor references) — Khaled Hosny, OFL.

---

## Rebuilding

See `build/build_stretch_hebrew_font.py` — a single script generates all 19
fonts from the upstream sources. Requires `fontTools` and `pathops`
(`pip install fonttools skia-pathops`).

Full build documentation and source repo:
<https://github.com/purlpal/semitic-search> (build script lives at
`scripts/build_stretch_hebrew_font.py`).
