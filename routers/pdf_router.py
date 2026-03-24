import os
from pathlib import Path
import tempfile
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
# IMPORTANTE: Importamos o threadpool para evitar que o servidor trave
from starlette.concurrency import run_in_threadpool 

from services.conversion.image_converter import convert_image_to_pdf
from services.conversion.office_converter import convert_office_to_pdf
from services.pdf.merge import merge_pdfs

router = APIRouter()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# --- REGRAS DE SEGURANÇA (DoS) ---
MAX_FILES = 10
MAX_FILE_SIZE = 10 * 1024 * 1024 # 10 megabytes em bytes

def remover_arquivo_seguro(path: str):
    """
    Função de limpeza. Será executada em segundo plano após o download.
    Resolve a falha de 'Persistência Indesejada'.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Erro ao limpar arquivo {path}: {e}")

@router.post("/merge")
async def merge_files(files: list[UploadFile] = File(...)):
    # 1. VALIDAÇÃO DE QUANTIDADE (Prevenção de DoS)
    if not files or len(files) == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Máximo de {MAX_FILES} arquivos permitidos por vez.")

    try:
        pdfs_para_juntar = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for file in files:
                # 2. SANITIZAÇÃO DE NOMES (Prevenção de Path Traversal e RCE)
                # Ignoramos o nome original e criamos um UUID (hash) seguro.
                ext = Path(file.filename).suffix.lower()
                nome_seguro = f"{uuid.uuid4().hex}{ext}"
                file_path = temp_path / nome_seguro

                # 3. VALIDAÇÃO DE TAMANHO (Prevenção de DoS em Disco/RAM)
                tamanho_total = 0
                with open(file_path, "wb") as buffer:
                    # Lemos o arquivo em pedaços (chunks) de 1MB por vez
                    while chunk := await file.read(1024 * 1024):
                        tamanho_total += len(chunk)
                        if tamanho_total > MAX_FILE_SIZE:
                            raise HTTPException(status_code=400, detail=f"Um dos arquivos excede o limite de 50MB.")
                        buffer.write(chunk)

                # Processamento com concorrência segura (run_in_threadpool)
                if ext == ".pdf":
                    pdfs_para_juntar.append(str(file_path))
                    
                elif ext in [".jpg", ".jpeg", ".png"]:
                    # Joga o processo da imagem para uma thread em background
                    pdf_convertido = await run_in_threadpool(convert_image_to_pdf, str(file_path), str(temp_path))
                    pdfs_para_juntar.append(pdf_convertido)
                    
                elif ext in [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
                    # Joga o subprocess do LibreOffice para uma thread, evitando travar o FastAPI
                    pdf_convertido = await run_in_threadpool(convert_office_to_pdf, str(file_path), str(temp_path))
                    pdfs_para_juntar.append(pdf_convertido)
                    
                else:
                    raise HTTPException(status_code=400, detail=f"Formato não suportado: {ext}")

            # Gera ID seguro para o arquivo final
            file_id = f"{uuid.uuid4().hex}.pdf"
            output_file = OUTPUT_DIR / file_id

            # O merge também é pesado, executamos em threadpool
            await run_in_threadpool(merge_pdfs, pdfs_para_juntar, str(output_file))

        return {
            "success": True,
            "download_url": f"/api/pdf/download/{file_id}"
        }

    except HTTPException:
        # Repassa os erros HTTP controlados (como arquivo muito grande)
        raise
    except Exception as e:
        # 4. OCULTAÇÃO DE ERROS (Segurança de Infraestrutura)
        # Não mostramos o erro bruto (que contém caminhos de pastas) para o usuário.
        print(f"Erro interno de processamento: {str(e)}") # Log apenas para nós desenvolvedores
        raise HTTPException(status_code=500, detail="Erro interno ao processar arquivos. Tente novamente.")

@router.get("/download/{file_id}")
async def download_pdf(file_id: str, background_tasks: BackgroundTasks):
    file_path = OUTPUT_DIR / file_id

    # Verificação extra contra Path Traversal no momento do download
    if not file_path.exists() or ".." in file_id or "/" in file_id:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    # 5. GARBAGE COLLECTION: Agenda a exclusão para DEPOIS que o usuário baixar
    background_tasks.add_task(remover_arquivo_seguro, str(file_path))

    return FileResponse(
        path=file_path,
        filename="Unificado.pdf",
        media_type="application/pdf"
    )