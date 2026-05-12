from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError 

def merge_pdfs(pdf_list: list[str], output_path: str):
    """
    Junta uma lista de caminhos de PDFs num único ficheiro, mantendo o tamanho original.
    Possui tratamento de erros para PDFs corrompidos ou com senha.
    """
    escritor = PdfWriter()

    for caminho in pdf_list:
        try:
            # TENTA ler o ficheiro PDF
            leitor = PdfReader(caminho)
            
            # 1. Verifica se o PDF está encriptado (com palavra-passe)
            if leitor.is_encrypted:
                raise Exception("Um dos arquivos está protegido com senha e não pode ser unificado.")

            # Percorre todas as páginas do PDF atual
            for pagina in leitor.pages:
                # Adiciona a página exatamente como ela veio, sem redimensionar
                escritor.add_page(pagina)

        # CAPTURA o erro se o PDF estiver corrompido
        except PdfReadError:
            raise Exception("Um dos arquivos selecionados está corrompido ou não é um PDF válido.")
            
        # CAPTURA qualquer outro erro imprevisto
        except Exception as e:
            raise Exception(f"Erro ao processar um arquivo: {str(e)}")

    # Escreve o resultado final no caminho de saída especificado
    try:
        with open(output_path, "wb") as f_out:
            escritor.write(f_out)
    except PermissionError:
        raise Exception("Erro de permissão no servidor ao tentar salvar o arquivo final.")