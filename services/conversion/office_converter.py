import subprocess
import os
from pathlib import Path

def convert_office_to_pdf(input_path: str, output_dir: str) -> str:
    """
    Converte arquivos do pacote Office (como DOC e DOCX) para PDF usando LibreOffice no Windows.
    
    Parâmetros:
    - input_path (str): Caminho completo do arquivo original.
    - output_dir (str): Diretório onde o PDF gerado será salvo.
    
    Retorno:
    - str: O caminho completo do arquivo PDF gerado.
    """
    
    # Caminho padrão de instalação do LibreOffice no Windows 64 bits.
    # O "r" antes das aspas indica uma "raw string", evitando que as barras invertidas (\) causem erros.
    libreoffice_exec = r"C:\Program Files\LibreOffice\program\soffice.exe"
    
    # Verificação de segurança: checa se o executável realmente existe neste caminho
    if not os.path.exists(libreoffice_exec):
        raise FileNotFoundError(
            f"O executável do LibreOffice não foi encontrado em: {libreoffice_exec}. "
            "Verifique se ele está instalado neste diretório."
        )
    
    try:
        # Montamos a lista de comandos que será enviada ao terminal do Windows (CMD/PowerShell)
        comando = [
            libreoffice_exec,
            "--headless",       # Executa de forma invisível (sem abrir a janela do Word/LibreOffice)
            "--convert-to",     # Comando de conversão
            "pdf",              # Formato de saída
            "--outdir",         # Define o diretório de destino
            output_dir,         # A variável com a pasta temporária
            input_path          # O arquivo DOC/DOCX de origem
        ]
        
        # Executa o comando. O check=True faz com que o Python lance um erro se o LibreOffice falhar.
        subprocess.run(comando, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # O LibreOffice salva o PDF com o mesmo nome do arquivo original. 
        # Vamos descobrir o nome correto para retornar ao nosso roteador.
        base_name = Path(input_path).stem  # Ex: pega 'contrato' de 'contrato.docx'
        output_pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        
        # Verificamos se o arquivo PDF foi realmente criado fisicamente na pasta
        if not os.path.exists(output_pdf_path):
            raise FileNotFoundError("A conversão parece ter ocorrido, mas o PDF não foi encontrado na pasta de destino.")
            
        return output_pdf_path
        
    except subprocess.CalledProcessError as e:
        # Pega a mensagem de erro exata que o LibreOffice jogaria no terminal
        erro_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        raise Exception(f"Falha na conversão via LibreOffice: {erro_msg}")
    except Exception as e:
        raise Exception(f"Erro inesperado ao converter Office para PDF: {str(e)}")