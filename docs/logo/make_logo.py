"""Erzeugt die Logo-Dateien (SVG) in docs/logo.

Die Formen des Zeichens stecken auch in catprinter/logo.py (Tray- und exe-Icon)
und in catprinter/statuspage.py - bei Änderungen dort mitziehen.
"""
import math, os
OUT = os.path.dirname(os.path.abspath(__file__))
ROSE, INK, WHITE = "#C94F68", "#22252B", "#FFFFFF"

def f(v): return f"{v:.2f}".rstrip("0").rstrip(".")

# ---- Zeichen: Bon mit Katzenohren -------------------------------------
def symbol_path(small=False):
    if small:  # Kleinversion: größere Augen, eine Druckzeile, gröbere Zähne
        top = "M64,44 Q64,28 76,36 L98,58 Q102,62 108,62 H148 Q154,62 158,58 L180,36 Q192,28 192,44"
        teeth = "V232 L176,212 L160,232 L144,212 L128,232 L112,212 L96,232 L80,212 L64,232 Z"
        eyes = [(100, 116, 20), (156, 116, 20)]
        lines = [(88, 164, 168, 184)]
    else:
        top = "M64,44 Q64,28 76,37 L100,57 Q104,61 110,61 H146 Q152,61 156,57 L180,37 Q192,28 192,44"
        teeth = "V232 L176,216 L160,232 L144,216 L128,232 L112,216 L96,232 L80,216 L64,232 Z"
        eyes = [(104, 110, 14), (152, 110, 14)]
        lines = [(88, 150, 168, 164), (88, 178, 144, 192)]
    d = top + " " + teeth
    for cx, cy, r in eyes:
        d += f" M{cx - r},{cy} a{r},{r} 0 1 0 {2*r},0 a{r},{r} 0 1 0 {-2*r},0 Z"
    for x0, y0, x1, y1 in lines:
        d += f" M{x0},{y0} H{x1} V{y1} H{x0} Z"
    return d

# ---- Schriftzug "catprinter": konstruierte geometrische Kleinbuchstaben --
W, R, r = 20, 50, 30   # Strichstärke, Außen-/Innenradius der Rundungen; x-Höhe 100

def pt(cx, cy, rad, a):
    return cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a))

def band(cx, cy, a0, a1):
    large = 1 if (a1 - a0) % 360 > 180 else 0
    x0, y0 = pt(cx, cy, R, a0); x1, y1 = pt(cx, cy, R, a1)
    x2, y2 = pt(cx, cy, r, a1); x3, y3 = pt(cx, cy, r, a0)
    return (f"M{f(x0)},{f(y0)} A{R},{R} 0 {large} 1 {f(x1)},{f(y1)} L{f(x2)},{f(y2)} "
            f"A{r},{r} 0 {large} 0 {f(x3)},{f(y3)} Z")

def ring(cx, cy):
    return (f"M{cx-R},{cy} A{R},{R} 0 1 1 {cx+R},{cy} A{R},{R} 0 1 1 {cx-R},{cy} Z "
            f"M{cx-r},{cy} A{r},{r} 0 1 0 {cx+r},{cy} A{r},{r} 0 1 0 {cx-r},{cy} Z")

def rect(x0, y0, x1, y1):
    return f"M{f(x0)},{f(y0)} H{f(x1)} V{f(y1)} H{f(x0)} Z"

def dot(cx, cy, rad):
    return f"M{cx-rad},{cy} A{rad},{rad} 0 1 1 {cx+rad},{cy} A{rad},{rad} 0 1 1 {cx-rad},{cy} Z"

B = 0  # Grundlinie
def glyph(ch, o):
    """(Pfad, Breite) eines Buchstabens bei x = o."""
    if ch == "c": return band(o + 50, B - 50, 45, 315), 86
    if ch == "a": return ring(o + 50, B - 50) + " " + rect(o + 80, B - 100, o + 100, B), 100
    if ch == "t": return rect(o + 14, B - 134, o + 34, B) + " " + rect(o, B - 100, o + 52, B - 80), 52
    if ch == "p": return rect(o, B - 100, o + 20, B + 48) + " " + ring(o + 50, B - 50), 100
    if ch == "r": return rect(o, B - 100, o + 20, B) + " " + band(o + 50, B - 50, 180, 292), 68
    if ch == "i": return rect(o, B - 100, o + 20, B) + " " + dot(o + 10, B - 128, 12), 20
    if ch == "n": return (rect(o, B - 100, o + 20, B) + " " + band(o + 50, B - 50, 180, 360) + " "
                          + rect(o + 80, B - 50, o + 100, B), 100)
    if ch == "e": return band(o + 50, B - 50, 45, 360) + " " + rect(o + 4, B - 60, o + 96, B - 40), 100
    raise ValueError(ch)

# Abstände nach Buchstabenpaar (optisch: rund an rund enger)
GAP = {"ca": 12, "at": 14, "tp": 16, "pr": 18, "ri": 16, "in": 20, "nt": 16, "te": 12, "er": 16}

def word(text, x=0):
    paths, o = [], x
    for i, ch in enumerate(text):
        p, w = glyph(ch, o)
        paths.append((ch, p))
        o += w + (GAP.get(text[i:i+2], 16) if i + 1 < len(text) else 0)
    return paths, o - x

WORD_TOP, WORD_BOTTOM = -140, 48   # i-Punkt / p-Unterlänge

def wordmark_group(x, y, s, cat_color, rest_color):
    paths, width = word("catprinter")
    cat = " ".join(p for i, (_, p) in enumerate(paths) if i < 3)
    rest = " ".join(p for i, (_, p) in enumerate(paths) if i >= 3)
    g = (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})">'
         f'<path fill="{cat_color}" d="{cat}"/><path fill="{rest_color}" d="{rest}"/></g>')
    return g, width

def symbol_group(x, y, s, color, small=False):
    return (f'<g transform="translate({f(x)},{f(y)}) scale({f(s)})">'
            f'<path fill="{color}" fill-rule="evenodd" d="{symbol_path(small)}"/></g>')

def svg(w, h, body, title, bg=None):
    rect_bg = f'<rect width="{f(w)}" height="{f(h)}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}">'
            f'<title>{title}</title>{rect_bg}{body}</svg>\n')

def save(name, text):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(text)

# Farbvarianten: (Suffix, Zeichen, "cat", "printer", Hintergrund)
SCHEMES = [("", ROSE, ROSE, INK, None), ("-black", INK, INK, INK, None),
           ("-white", WHITE, WHITE, WHITE, None),
           ("-on-dark", ROSE, ROSE, WHITE, None)]

# Zeichen (Symbol) – quadratisch 256
for suf, sc, *_ in SCHEMES:
    if suf == "-on-dark":
        continue  # Zeichen ist auf dunklem Grund unverändert rosé
    save(f"catprinter-symbol{suf}.svg", svg(256, 256, symbol_group(0, -4, 1, sc), "Cat Printer"))
    save(f"catprinter-symbol-small{suf}.svg", svg(256, 256, symbol_group(0, -4, 1, sc, True), "Cat Printer"))

# Schriftzug allein
_, WW = word("catprinter")
PAD = 8
for suf, _, cc, rc, _bg in SCHEMES:
    g, _ = wordmark_group(PAD, PAD - WORD_TOP, 1, cc, rc)
    save(f"catprinter-wordmark{suf}.svg", svg(WW + 2 * PAD, WORD_BOTTOM - WORD_TOP + 2 * PAD, g, "Cat Printer"))

# Quer: Zeichen (Bon 64..192 × 28..232) links, Schriftzug rechts
# Bon-Höhe = 204 Einheiten; wir bringen ihn auf Höhe 196 zwischen -144 und +52 um die x-Mitte (-50)
sh = 200 / 204
sym_left, sym_top = -64 * sh, -146 - 28 * sh   # Bonkante bei x=0
gap_h = 56
for suf, sc, cc, rc, _bg in SCHEMES:
    body = symbol_group(PAD + sym_left, PAD + 146 + sym_top, sh, sc)
    g, _ = wordmark_group(PAD + 128 * sh + gap_h, PAD + 146, 1, cc, rc)
    w = PAD * 2 + 128 * sh + gap_h + WW
    save(f"catprinter-horizontal{suf}.svg", svg(w, 200 + 2 * PAD, body + g, "Cat Printer"))

# Gestapelt: Zeichen oben mittig, Schriftzug darunter
ss = 1.6
stack_w = WW + 2 * PAD
for suf, sc, cc, rc, _bg in SCHEMES:
    sym_w = 128 * ss
    sx = (stack_w - sym_w) / 2 - 64 * ss
    body = symbol_group(sx, PAD - 28 * ss, ss, sc)
    word_y = PAD + 204 * ss + 64 - WORD_TOP
    g, _ = wordmark_group(PAD, word_y, 1, cc, rc)
    save(f"catprinter-stacked{suf}.svg", svg(stack_w, word_y + WORD_BOTTOM + PAD, body + g, "Cat Printer"))

# App-Icon: weißer Bon auf rosé Kachel (Kleinversion ab 48 px nutzen)
for name, small in (("catprinter-app-icon.svg", False), ("catprinter-app-icon-small.svg", True)):
    tile = f'<rect width="256" height="256" rx="56" fill="{ROSE}"/>'
    s = 0.86
    save(name, svg(256, 256, tile + symbol_group(128 - 128 * s, 128 - 130 * s, s, WHITE, small), "Cat Printer"))

print("SVGs in", OUT)
