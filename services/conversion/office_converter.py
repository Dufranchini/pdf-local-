import subprocess
import os
import platform
from pathlib import Path
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do ficheiro .env para a memória do Python
load_dotenv()

def convert_office_to_pdf(input_path: str, output_dir: str) -> str:
    """
    Converte arquivos do pacote Office para PDF usando LibreOffice.
    """
    
    # 1. Tenta ler o caminho do LibreOffice a partir do ficheiro .env
    libreoffice_exec = os.getenv("LIBREOFFICE_PATH")
    
    # 2. LÓGICA DE FALLBACK (Plano B de Segurança)
    # Se por algum motivo o .env não existir ou a variável estiver vazia,
    # usamos o comportamento padrão (inteligente) baseado no Sistema Operativo.
    if not libreoffice_exec:
        if platform.system() == "Windows":
            libreoffice_exec = r"C:\Program Files\LibreOffice\program\soffice.exe"
        else:
            libreoffice_exec = "libreoffice"
    
    # Validação para garantir que não tentamos executar um caminho que não existe
    if platform.system() == "Windows" and not os.path.exists(libreoffice_exec) and libreoffice_exec != "libreoffice":
         raise FileNotFoundError(
            f"O executável do LibreOffice não foi encontrado em: {libreoffice_exec}. "
            "Verifique o ficheiro .env ou a instalação."
        )

    try:
        comando = [
            libreoffice_exec,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            output_dir,
            input_path
        ]
        
        # Executa o comando
        subprocess.run(comando, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # O LibreOffice salva com o mesmo nome original, mas extensão .pdf
        base_name = Path(input_path).stem
        output_pdf_path = os.path.join(output_dir, f"{base_name}.pdf")
        
        if not os.path.exists(output_pdf_path):
            raise FileNotFoundError("A conversão falhou: o ficheiro PDF não foi encontrado no diretório de destino.")
            
        return output_pdf_path
        
    except subprocess.CalledProcessError as e:
        erro_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
        raise Exception(f"Falha na execução do LibreOffice: {erro_msg}")
    except Exception as e:
        raise Exception(f"Erro inesperado ao converter documento Office: {str(e)}")