"""Two controls that differ only in paint order, to isolate what each parser does.

Control A paints the right-to-left runs at ascending X in LOGICAL order - the
shape a producer that does no bidi layout emits.

Control B paints the same characters at ascending X in VISUAL order - the shape
a bidi-aware typesetter emits, where the first character read sits rightmost.

Same characters, same font, same ToUnicode, same page geometry. The only
difference is the order the glyphs were painted in. A parser that inspects the
evidence gets both right; a parser applying a fixed policy gets exactly one
right, and which one tells you what the policy is.

Shaping is deliberately not applied: it changes which glyph is drawn, not which
character it maps back to, and the ToUnicode CMap is what extraction reads.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent

ARABIC = "\u062c\u062f\u0648\u0644 \u0627\u0644\u0645\u062e\u0627\u0644\u0641\u0627\u062a"
HEBREW = "\u05e9\u05dc\u05d5\u05dd \u05e2\u05d5\u05dc\u05dd"

FONT_CANDIDATES = [
    ("Arial", r"C:\Windows\Fonts\arial.ttf"),
    ("Tahoma", r"C:\Windows\Fonts\tahoma.ttf"),
]


def _register_font() -> str:
    for name, path in FONT_CANDIDATES:
        if Path(path).exists():
            pdfmetrics.registerFont(TTFont(name, path))
            return name
    raise SystemExit("no Unicode TrueType font available")


def write(out: Path, arabic: str, hebrew: str) -> None:
    font = _register_font()
    page = canvas.Canvas(str(out), pagesize=A4)
    page.setFont(font, 18)
    page.drawString(72, 760, "Control document")
    page.drawString(72, 720, arabic)
    page.drawString(72, 680, hebrew)
    page.drawString(72, 640, "End of control")
    page.showPage()
    page.save()
    print(f"wrote {out.name}")


if __name__ == "__main__":
    # A: paint order == logical order.
    write(HERE / "control_logical_order.pdf", ARABIC, HEBREW)
    # B: paint order == visual order, i.e. reversed relative to logical.
    write(HERE / "control_visual_order.pdf", ARABIC[::-1], HEBREW[::-1])
