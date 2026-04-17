from pypdf import PdfReader, PdfWriter

# DEFINE O TAMANHO DA PÁGINA PARA A4
A4_LARGURA = 595.28
A4_ALTURA = 841.89

def merge_pdfs(pdf_list: list[str], output_path: str):
    """
    Junta uma lista de caminhos de PDFs em um único arquivo PDF.
    Também padroniza todas as páginas geradas para o tamanho A4.
    """
    escritor = PdfWriter()

    for caminho in pdf_list:
        leitor = PdfReader(caminho)
        
        # Percorre todas as páginas do PDF atual
        for pagina in leitor.pages:
            # A MÁGICA DO A4: Redimensiona a página para caber no formato A4
            pagina.scale_to(width=A4_LARGURA, height=A4_ALTURA)
            
            # Adiciona a página formatada ao documento final
            escritor.add_page(pagina)

    # Escreve o resultado final no caminho de saída especificado
    with open(output_path, "wb") as f_out:
        escritor.write(f_out)