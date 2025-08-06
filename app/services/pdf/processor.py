import io
from pathlib import Path

import PyPDF2
from PyPDF2 import PdfReader, PdfWriter


class PDFProcessor:
    @staticmethod
    def extract_text(pdf_content: bytes, start_page: int = 0, end_page: int | None = None) -> str:
        """Extract text from PDF content."""
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        
        text = ""
        total_pages = len(reader.pages)
        
        if end_page is None:
            end_page = total_pages
        else:
            end_page = min(end_page, total_pages)
            
        for page_num in range(start_page, end_page):
            if page_num < total_pages:
                page = reader.pages[page_num]
                text += page.extract_text() + "\n"
                
        return text

    @staticmethod
    def crop_pdf(pdf_content: bytes, start_page: int, end_page: int) -> bytes:
        """Crop PDF to specific page range."""
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        
        # Adjust page numbers (1-indexed to 0-indexed)
        start_page = max(0, start_page - 1)
        end_page = min(total_pages, end_page)
        
        for page_num in range(start_page, end_page):
            if page_num < total_pages:
                writer.add_page(reader.pages[page_num])
        
        output = io.BytesIO()
        writer.write(output)
        output.seek(0)
        return output.read()

    @staticmethod
    def read_pdf_file(file_path: str) -> bytes:
        """Read PDF file from disk."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")
        if not path.suffix.lower() == '.pdf':
            raise ValueError(f"File is not a PDF: {file_path}")
            
        with open(file_path, 'rb') as f:
            return f.read()

    @staticmethod
    def get_page_count(pdf_content: bytes) -> int:
        """Get total number of pages in PDF."""
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        return len(reader.pages)

    @staticmethod
    def extract_text_as_string(pdf_content: bytes) -> str:
        """Extract all text from PDF as a single string for LLM processing."""
        text = PDFProcessor.extract_text(pdf_content)
        # Clean up the text for better LLM processing
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned_lines)