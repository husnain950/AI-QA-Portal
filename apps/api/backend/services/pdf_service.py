from pypdf import PdfReader


def get_pdf_page_count(file_path: str) -> int:
    try:
        reader = PdfReader(file_path)
        return len(reader.pages)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return 0
