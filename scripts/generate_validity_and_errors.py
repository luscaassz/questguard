
from pathlib import Path

import matplotlib.pyplot as plt
import fitz  # PyMuPDF
from PIL import Image


OUTPUT_DIR = Path(__file__).resolve().parent

# Final experimental results: mean ± sample standard deviation across 3 runs.
validity_labels = ["C1", "C2", "C3", "C4", "C5"]
validity_means = [0.0, 0.0, 0.0, 1.0, 1.0]
validity_stds = [0.0, 0.0, 0.0, 0.0, 0.0]

error_labels = ["C1", "C2"]
error_means = [9.6666666667, 3.3777777778]
error_stds = [1.1269427670, 1.3124757493]


def create_validity_panel() -> tuple[Path, Path]:
    fig = plt.figure(figsize=(5.4, 4.0))
    ax = fig.add_axes([0.16, 0.18, 0.80, 0.72])

    ax.bar(
        validity_labels,
        validity_means,
        yerr=validity_stds,
        capsize=4,
    )

    ax.set_ylim(0.0, 1.10)
    ax.set_ylabel("Valid / published yield")
    ax.set_xlabel("Configuration")
    ax.set_title("(a) Valid/published yield")
    ax.set_yticks([0.0, 0.25, 0.50, 0.75, 1.0])
    ax.grid(axis="y", alpha=0.3)

    for index, value in enumerate(validity_means):
        ax.text(
            index,
            value + 0.035,
            f"{value:.0%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    pdf_path = OUTPUT_DIR / "validity_panel.pdf"
    png_path = OUTPUT_DIR / "validity_panel.png"

    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return pdf_path, png_path


def create_errors_panel() -> tuple[Path, Path]:
    fig = plt.figure(figsize=(5.4, 4.0))
    ax = fig.add_axes([0.18, 0.18, 0.78, 0.72])

    ax.bar(
        error_labels,
        error_means,
        yerr=error_stds,
        capsize=5,
    )

    ax.set_ylim(0.0, 12.5)
    ax.set_ylabel("Mean validation errors per quest")
    ax.set_xlabel("Configuration")
    ax.set_title("(b) Error density")
    ax.grid(axis="y", alpha=0.3)

    for index, value in enumerate(error_means):
        ax.text(
            index,
            value + error_stds[index] + 0.35,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    pdf_path = OUTPUT_DIR / "errors_panel.pdf"
    png_path = OUTPUT_DIR / "errors_panel.png"

    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    return pdf_path, png_path


def combine_pdfs(left_pdf: Path, right_pdf: Path, output_pdf: Path) -> None:
    left_doc = fitz.open(left_pdf)
    right_doc = fitz.open(right_pdf)

    left_page = left_doc[0]
    right_page = right_doc[0]

    left_rect = left_page.rect
    right_rect = right_page.rect

    margin = 18
    gap = 12
    page_height = max(left_rect.height, right_rect.height) + 2 * margin
    page_width = left_rect.width + right_rect.width + gap + 2 * margin

    output_doc = fitz.open()
    output_page = output_doc.new_page(width=page_width, height=page_height)

    left_target = fitz.Rect(
        margin,
        margin,
        margin + left_rect.width,
        margin + left_rect.height,
    )
    right_target = fitz.Rect(
        margin + left_rect.width + gap,
        margin,
        margin + left_rect.width + gap + right_rect.width,
        margin + right_rect.height,
    )

    output_page.show_pdf_page(left_target, left_doc, 0)
    output_page.show_pdf_page(right_target, right_doc, 0)

    output_doc.save(output_pdf)

    output_doc.close()
    left_doc.close()
    right_doc.close()


def combine_pngs(left_png: Path, right_png: Path, output_png: Path) -> None:
    left = Image.open(left_png).convert("RGB")
    right = Image.open(right_png).convert("RGB")

    gap = 40
    background = Image.new(
        "RGB",
        (left.width + right.width + gap, max(left.height, right.height)),
        "white",
    )

    background.paste(left, (0, 0))
    background.paste(right, (left.width + gap, 0))
    background.save(output_png, dpi=(300, 300))


def main() -> None:
    validity_pdf, validity_png = create_validity_panel()
    errors_pdf, errors_png = create_errors_panel()

    combined_pdf = OUTPUT_DIR / "validity_and_errors.pdf"
    combined_png = OUTPUT_DIR / "validity_and_errors.png"

    combine_pdfs(validity_pdf, errors_pdf, combined_pdf)
    combine_pngs(validity_png, errors_png, combined_png)

    print(f"Created: {combined_pdf}")
    print(f"Created: {combined_png}")


if __name__ == "__main__":
    main()
