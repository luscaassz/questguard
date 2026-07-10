
from pathlib import Path
import json
import math

import matplotlib.pyplot as plt
import fitz  # PyMuPDF
from PIL import Image, ImageDraw


BASE_DIR = Path(__file__).resolve().parents[1]
SUMMARY_PATH = BASE_DIR / "outputs/experiments/final_30_aggregate_summary.json"

with SUMMARY_PATH.open("r", encoding="utf-8") as f:
    summary = json.load(f)

div = summary["diversity_metrics"]

METRICS = [
    ("unique_structural_signatures", "Unique signatures", "higher"),
    ("duplicate_signature_rate", "Duplicate rate", "lower"),
    ("entity_coverage", "Entity coverage", "higher"),
    ("entity_concentration", "Entity concentration", "lower"),
    ("average_pairwise_similarity", "Pairwise similarity", "lower"),
]

RUN_LABELS = ["Run 1", "Run 2", "Run 3"]


def create_metric_panel(metric_key: str, title: str, direction: str) -> tuple[Path, Path]:
    c4 = div["C4"][metric_key]["values"]
    c5 = div["C5"][metric_key]["values"]

    fig = plt.figure(figsize=(4.2, 3.2))
    ax = fig.add_axes([0.18, 0.18, 0.75, 0.68])

    # Paired points per run
    x_positions = [0, 1]
    for idx, (v4, v5) in enumerate(zip(c4, c5), start=1):
        ax.plot(
            x_positions,
            [v4, v5],
            marker="o",
            linewidth=1.2,
            alpha=0.9,
        )
        # Small labels beside the C5 point
        ax.text(
            1.04,
            v5,
            f"R{idx}",
            va="center",
            fontsize=7,
        )

    # Mean markers
    c4_mean = sum(c4) / len(c4)
    c5_mean = sum(c5) / len(c5)
    ax.scatter([0, 1], [c4_mean, c5_mean], marker="D", s=50)
    ax.text(0, c4_mean, f"  mean={c4_mean:.3f}" if c4_mean < 10 else f"  mean={c4_mean:.2f}",
            va="bottom", fontsize=7)
    ax.text(1, c5_mean, f"  mean={c5_mean:.3f}" if c5_mean < 10 else f"  mean={c5_mean:.2f}",
            va="bottom", fontsize=7)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["C4", "C5"])
    ax.set_title(title)
    ax.set_ylabel("Value")
    ax.grid(axis="y", alpha=0.3)

    # Helpful note on better direction
    note = "Higher is better" if direction == "higher" else "Lower is better"
    ax.text(
        0.5,
        1.03,
        note,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=8,
    )

    # Dynamic limits with padding
    all_vals = c4 + c5
    ymin = min(all_vals)
    ymax = max(all_vals)
    span = ymax - ymin
    pad = 0.12 * span if span > 0 else 0.1 * max(1.0, ymax if ymax != 0 else 1.0)
    ax.set_ylim(ymin - pad, ymax + pad)

    pdf_path = BASE_DIR / f"{metric_key}_panel.pdf"
    png_path = BASE_DIR / f"{metric_key}_panel.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return pdf_path, png_path


def combine_pdfs(panel_pdfs: list[Path], output_pdf: Path) -> None:
    docs = [fitz.open(str(path)) for path in panel_pdfs]
    rects = [doc[0].rect for doc in docs]

    cols = 3
    rows = 2
    gap_x = 14
    gap_y = 18
    margin = 18

    cell_w = max(rect.width for rect in rects)
    cell_h = max(rect.height for rect in rects)

    page_w = margin * 2 + cols * cell_w + (cols - 1) * gap_x
    page_h = margin * 2 + rows * cell_h + (rows - 1) * gap_y

    out = fitz.open()
    page = out.new_page(width=page_w, height=page_h)

    for idx, doc in enumerate(docs):
        row = idx // cols
        col = idx % cols
        x0 = margin + col * (cell_w + gap_x)
        y0 = margin + row * (cell_h + gap_y)
        target = fitz.Rect(x0, y0, x0 + rects[idx].width, y0 + rects[idx].height)
        page.show_pdf_page(target, doc, 0)

    out.save(str(output_pdf))
    out.close()
    for doc in docs:
        doc.close()


def combine_pngs(panel_pngs: list[Path], output_png: Path) -> None:
    imgs = [Image.open(path).convert("RGB") for path in panel_pngs]

    cols = 3
    rows = 2
    gap_x = 40
    gap_y = 50
    margin = 35

    cell_w = max(img.width for img in imgs)
    cell_h = max(img.height for img in imgs)

    canvas_w = margin * 2 + cols * cell_w + (cols - 1) * gap_x
    canvas_h = margin * 2 + rows * cell_h + (rows - 1) * gap_y

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)

    for idx, img in enumerate(imgs):
        row = idx // cols
        col = idx % cols
        x = margin + col * (cell_w + gap_x)
        y = margin + row * (cell_h + gap_y)
        canvas.paste(img, (x, y))

    # optional caption in empty 6th cell
    if len(imgs) < cols * rows:
        empty_idx = len(imgs)
        row = empty_idx // cols
        col = empty_idx % cols
        x = margin + col * (cell_w + gap_x)
        y = margin + row * (cell_h + gap_y)
        text = (
            "Paired plots across the 3 final runs.\n"
            "Lines connect the same run in C4 and C5.\n"
            "Diamond markers denote the mean."
        )
        draw.multiline_text((x + 15, y + 40), text, fill="black", spacing=6)

    canvas.save(output_png, dpi=(300, 300))


def main():
    pdfs = []
    pngs = []

    for metric_key, title, direction in METRICS:
        pdf_path, png_path = create_metric_panel(metric_key, title, direction)
        pdfs.append(pdf_path)
        pngs.append(png_path)

    output_pdf = BASE_DIR / "c4_c5_diversity.pdf"
    output_png = BASE_DIR / "c4_c5_diversity.png"

    combine_pdfs(pdfs, output_pdf)
    combine_pngs(pngs, output_png)

    print(f"Created: {output_pdf}")
    print(f"Created: {output_png}")


if __name__ == "__main__":
    main()
