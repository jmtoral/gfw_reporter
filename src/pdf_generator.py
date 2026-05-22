from fpdf import FPDF
import datetime
from pathlib import Path

class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Reporte de Analisis de Conflictos (ACLED)', 0, 1, 'C')
        self.ln(5)
        
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(country: str, report_text: str, output_path: str):
    pdf = PDFReport()
    pdf.add_page()
    
    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Analisis para: {country}", 0, 1, 'L')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Generado el: {datetime.datetime.now().strftime('%Y-%m-%d')}", 0, 1, 'L')
    pdf.ln(5)
    
    # Body text
    pdf.set_font("Arial", size=11)
    
    # Limpiar caracteres especiales para evitar errores en fuente Arial estándar
    clean_text = report_text.encode('latin-1', 'replace').decode('latin-1')
    
    pdf.multi_cell(0, 7, txt=clean_text)
        
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(output_path)


def generate_pdf_bytes(country: str, report_text: str) -> bytes:
    pdf = PDFReport()
    pdf.add_page()

    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"Analisis para: {country}", 0, 1, 'L')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Generado el: {datetime.datetime.now().strftime('%Y-%m-%d')}", 0, 1, 'L')
    pdf.ln(5)

    pdf.set_font("Arial", size=11)
    clean_text = report_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 7, txt=clean_text)

    return pdf.output(dest="S").encode("latin-1")
