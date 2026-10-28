"""Add reading-guide callouts to existing Lab 4 captures; no browser or model calls.

    python demos/annotate-lab4-screenshots.py

Uses Pillow, already required by the slide-building dependencies. Original screenshots are left unchanged.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHOTS = Path(__file__).resolve().parents[1] / "content" / "labs" / "screenshots" / "lab-04"
GUIDES = {
    "10-devui-sequential": [
        ((0.025, 0.21), "Graph: locate Nutrition, Activity and Coach; edges alone do not prove a run."),
        ((0.75, 0.18), "Timeline: read each agent's Output; Coach produces the merged evidence JSON."),
    ],
    "11-devui-handoff": [
        ((0.025, 0.21), "Graph: displayed connections are not the actual execution history."),
        ((0.75, 0.18), "Timeline: expand Output; repeated Run entries can be message broadcasts."),
        ((0.97, 0.14), "Tools: two hand-off calls + two results = four entries; not four hand-offs."),
    ],
}


def annotate(stem: str, callouts: list[tuple[tuple[float, float], str]]) -> Path:
    with Image.open(SHOTS / f"{stem}.png") as source:
        image = source.convert("RGB")
    width, height = image.size
    scale = width / 1600
    row = round(38 * scale)
    margin = round(20 * scale)
    radius = round(17 * scale)
    result = Image.new("RGB", (width, height + margin * 2 + row * len(callouts)), "#102c46")
    result.paste(image, (0, 0))
    draw = ImageDraw.Draw(result)
    font = ImageFont.load_default(size=round(22 * scale))
    for index, ((x, y), caption) in enumerate(callouts, 1):
        cx, cy = round(x * width), round(y * height)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill="#102c46", outline="#ffffff", width=round(2 * scale))
        draw.text((cx, cy), str(index), fill="#ffffff", font=font, anchor="mm")
        draw.text((margin, height + margin + (index - 1) * row), f"{index}. {caption}",
                  fill="#ffffff", font=font)
    target = SHOTS / f"{stem}-annotated.png"
    result.save(target)
    return target


if __name__ == "__main__":
    for stem, callouts in GUIDES.items():
        print(annotate(stem, callouts).name)
