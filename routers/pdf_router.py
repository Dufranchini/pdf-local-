import os
import tempfile
import uuid


from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
# IMPORTANTE: Importamos o threadpool para evitar que o servidor trave
from starlette.concurrency import run_in_threadpool

from services.conversion.image_converter import convert_image_to_pdf
from services.conversion.office_converter import convert_office_to_pdf
from services.pdf.merge import merge_pdfs

from logger import get_logger
log = get_logger("pdf_router")

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
    log.info(f"Nova requisição recebida | Arquivos: {len(files)}")

    if not files:
        log.warning("Requisição rejeitada: nenhum arquivo enviado")
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    if len(files) > MAX_FILES:
        log.warning(f"Requisição rejeitada: {len(files)} arquivos (limite: {MAX_FILES})")
        raise HTTPException(status_code=413, detail="Número máximo de arquivos excedido.")

    pdf_convertido = []

    try:
        tamanho_acumulado = 0

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            for file in files:
                ext = Path(file.filename).suffix.lower()
                log.debug(f"Processando arquivo: {file.filename} | Tipo: {ext}")

                uploaded_path = temp_dir_path / Path(file.filename).name
                with uploaded_path.open("wb") as buffer:
                    while content := await file.read(1024 * 1024):
                        buffer.write(content)

                tamanho_acumulado += uploaded_path.stat().st_size
                if tamanho_acumulado > MAX_FILE_SIZE:
                    log.warning(f"Rejeitado: tamanho total excedeu 10MB")
                    raise HTTPException(status_code=413, detail="Tamanho total dos arquivos excedeu 10MB.")

                if ext == ".pdf":
                    log.debug(f"PDF direto: {file.filename}")
                    pdf_convertido.append(str(uploaded_path))

                elif ext in [".jpg", ".jpeg", ".png"]:
                    log.info(f"Convertendo imagem: {file.filename}")
                    pdf_path = await run_in_threadpool(convert_image_to_pdf, str(uploaded_path), str(temp_dir_path))
                    pdf_convertido.append(pdf_path)
                    log.info(f"Imagem convertida com sucesso: {file.filename}")

                elif ext in [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
                    log.info(f"Convertendo Office: {file.filename}")
                    pdf_path = await run_in_threadpool(convert_office_to_pdf, str(uploaded_path), str(temp_dir_path))
                    pdf_convertido.append(pdf_path)
                    log.info(f"Office convertido com sucesso: {file.filename}")

                else:
                    log.warning(f"Formato não suportado recebido: {ext}")
                    raise HTTPException(status_code=415, detail=f"Formato de arquivo não suportado: {ext}")

            if not pdf_convertido:
                raise HTTPException(status_code=400, detail="Nenhum arquivo válido para mesclar.")

            file_id = f"{uuid.uuid4().hex}.pdf"
            output_file = OUTPUT_DIR / file_id

            log.info(f"Iniciando merge de {len(pdf_convertido)} PDFs")
            await run_in_threadpool(merge_pdfs, pdf_convertido, str(output_file))
            log.info(f"Merge concluído com sucesso | Arquivo: {file_id}")

        return {"success": True, "download_url": f"/api/pdf/download/{file_id}"}

    except HTTPException:
        raise

    except Exception as e:
        log.error(f"Erro interno inesperado: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar arquivos.")

@router.get("/download/{file_id}")
async def download_pdf(file_id: str, background_tasks: BackgroundTasks):
    log.info(f"Download solicitado | file_id: {file_id}")
    file_path = OUTPUT_DIR / file_id

    # Verificação extra contra Path Traversal no momento do download
    if not file_path.exists() or ".." in file_id or "/" in file_id:
        log.warning(f"Download negado: arquivo não encontrado  ou path inválido | ID: {file_id}")
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    log.info(f"Download iniciado | Arquivo: {file_id}")
    # 5. GARBAGE COLLECTION: Agenda a exclusão para DEPOIS que o usuário baixar
    background_tasks.add_task(remover_arquivo_seguro, str(file_path))

    return FileResponse(
        path=file_path,
        filename="Mway_unificado.pdf",
        media_type="application/pdf"
    )