from pathlib import Path
from PIL import Image


def convert_image_to_pdf(image_path: str, output_dir: str) -> str:
    image_path = Path(image_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / f"{image_path.stem}.pdf"

    with Image.open(image_path) as img:
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.save(pdf_path, "PDF")

    return str(pdf_path)