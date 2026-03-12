from pypdf import PdfWriter


def merge_pdfs(pdf_files: list[str], output_path: str) -> str:
    writer = PdfWriter()

    for pdf_file in pdf_files:
        writer.append(pdf_file)

    with open(output_path, "wb") as f:
        writer.write(f)

    return output_path