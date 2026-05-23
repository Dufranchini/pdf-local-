import os
import tempfile
import uuid

from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from services.conversion.image_converter import convert_image_to_pdf
from services.conversion.office_converter import convert_office_to_pdf
from services.conversion.word_converter import convert_pdf_to_doc
from services.pdf.merge import merge_pdfs
from services.pdf.compressor import compress_pdf

from logger import get_logger
log = get_logger("pdf_router")

router = APIRouter()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════
#  REGRAS DE SEGURANÇA (compartilhadas)
# ══════════════════════════════════════════════════════
MAX_FILES = 10
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

EXTENSOES_MERGE        = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx",
                          ".xls", ".xlsx", ".ppt", ".pptx"}
EXTENSOES_CONVERT_DOC  = {".pdf"}
EXTENSOES_COMPRESS     = {".pdf"}

PDF_MAGIC = b"%PDF-" #verifica os primeiros bytes do arquivo para confirmar que é um PDF (anti-fake)


def remover_arquivo_seguro(path: str):
    """Limpeza pós-download. Executada em background."""
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info(f"Arquivo temporário removido: {path}")
    except Exception as e:
        log.error(f"Erro ao limpar arquivo {path}: {e}")


def validar_nome_seguro(file_id: str) -> bool:
    """Bloqueia path traversal no parâmetro de URL."""
    if ".." in file_id or "/" in file_id or "\\" in file_id:
        return False
    if not (file_id.endswith(".pdf") or file_id.endswith(".docx")):
        return False
    nome_sem_ext = file_id.rsplit(".", 1)[0]
    if not (len(nome_sem_ext) == 32 and all(c in "0123456789abcdef" for c in nome_sem_ext)):
        return False
    return True


async def _salvar_upload_validado(file: UploadFile, destino: Path, max_size: int) -> bytes:
    """
    Helper compartilhado: salva upload em chunks, valida tamanho e magic bytes.
    Retorna os primeiros 5 bytes pra confirmação de tipo.

    Toda rota que aceita PDF passa por aqui — DRY + segurança padronizada.
    """
    tamanho_acumulado = 0
    magic_check = b""

    with destino.open("wb") as buffer:
        while content := await file.read(1024 * 1024):
            tamanho_acumulado += len(content)
            if tamanho_acumulado > max_size:
                buffer.close()
                remover_arquivo_seguro(str(destino))
                raise HTTPException(
                    status_code=413,
                    detail=f"O arquivo excede o limite de {max_size // (1024*1024)}MB."
                )
            if len(magic_check) < 5:
                magic_check += content[:5 - len(magic_check)]
            buffer.write(content)

    return magic_check


# ══════════════════════════════════════════════════════
#  ROTA 1 — Juntar múltiplos arquivos em 1 PDF
# ══════════════════════════════════════════════════════
@router.post("/merge")
async def merge_files(files: list[UploadFile] = File(...)):
    log.info(f"Nova requisição de merge | Arquivos: {len(files)}")

    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=413, detail="Número máximo de arquivos excedido.")

    pdfs_para_juntar = []

    try:
        tamanho_acumulado = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            for file in files:
                ext = Path(file.filename).suffix.lower()
                if ext not in EXTENSOES_MERGE:
                    raise HTTPException(status_code=415, detail=f"Formato não suportado: {ext}")

                nome_seguro = f"{uuid.uuid4().hex}{ext}"
                uploaded_path = temp_dir_path / nome_seguro

                with uploaded_path.open("wb") as buffer:
                    while content := await file.read(1024 * 1024):
                        tamanho_acumulado += len(content)
                        if tamanho_acumulado > MAX_FILE_SIZE:
                            raise HTTPException(status_code=413, detail="Tamanho total dos arquivos excedeu 10MB.")
                        buffer.write(content)

                if ext == ".pdf":
                    pdfs_para_juntar.append(str(uploaded_path))
                elif ext in [".jpg", ".jpeg", ".png"]:
                    pdf_path = await run_in_threadpool(convert_image_to_pdf, str(uploaded_path), str(temp_dir_path))
                    pdfs_para_juntar.append(pdf_path)
                elif ext in [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]:
                    pdf_path = await run_in_threadpool(convert_office_to_pdf, str(uploaded_path), str(temp_dir_path))
                    pdfs_para_juntar.append(pdf_path)

            if not pdfs_para_juntar:
                raise HTTPException(status_code=400, detail="Nenhum arquivo válido para mesclar.")

            file_id = f"{uuid.uuid4().hex}.pdf"
            output_file = OUTPUT_DIR / file_id

            log.info(f"Iniciando merge de {len(pdfs_para_juntar)} PDFs")
            await run_in_threadpool(merge_pdfs, pdfs_para_juntar, str(output_file))
            log.info(f"Merge concluído | Arquivo: {file_id}")

        return {"success": True, "download_url": f"/api/pdf/download/{file_id}"}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Erro interno no merge: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao processar arquivos.")


# ══════════════════════════════════════════════════════
#  ROTA 2 — Converter 1 PDF em DOCX
# ══════════════════════════════════════════════════════
@router.post("/convert-to-doc")
async def convert_to_doc(file: UploadFile = File(...)):
    log.info(f"Nova requisição de conversão PDF→DOCX | Arquivo: {file.filename}")

    ext = Path(file.filename).suffix.lower()
    if ext not in EXTENSOES_CONVERT_DOC:
        raise HTTPException(status_code=415, detail="Apenas arquivos .pdf são aceitos para conversão.")

    nome_pdf_seguro = f"{uuid.uuid4().hex}.pdf"
    temp_pdf = OUTPUT_DIR / nome_pdf_seguro

    try:
        magic_check = await _salvar_upload_validado(file, temp_pdf, MAX_FILE_SIZE)

        if not magic_check.startswith(PDF_MAGIC):
            log.warning(f"Arquivo rejeitado: não é PDF válido")
            remover_arquivo_seguro(str(temp_pdf))
            raise HTTPException(status_code=415, detail="O arquivo enviado não é um PDF válido.")

        try:
            docx_path = await run_in_threadpool(convert_pdf_to_doc, str(temp_pdf), str(OUTPUT_DIR))
        except ValueError as ve:
            log.warning(f"PDF inválido: {ve}")
            remover_arquivo_seguro(str(temp_pdf))
            raise HTTPException(status_code=422, detail=str(ve))

        remover_arquivo_seguro(str(temp_pdf))

        nome_original = Path(file.filename).stem
        nome_original = "".join(c for c in nome_original if c.isalnum() or c in "._- ")[:80]
        nome_download = f"Mway_{nome_original}.docx"

        log.info(f"Conversão concluída | Entregando: {nome_download}")

        background_tasks = BackgroundTasks()
        background_tasks.add_task(remover_arquivo_seguro, docx_path)

        return FileResponse(
            path=docx_path,
            filename=nome_download,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=background_tasks,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Erro na conversão PDF→DOCX: {str(e)}", exc_info=True)
        if temp_pdf.exists():
            remover_arquivo_seguro(str(temp_pdf))
        raise HTTPException(status_code=500, detail="Erro interno ao converter o arquivo.")


# ══════════════════════════════════════════════════════
#  ROTA 3 — Comprimir PDF
# ══════════════════════════════════════════════════════
@router.post("/compress")
async def compress_pdf_route(file: UploadFile = File(...)):
    
    log.info(f"Nova requisição de compressão | Arquivo: {file.filename}")

    ext = Path(file.filename).suffix.lower()
    if ext not in EXTENSOES_COMPRESS:
        log.warning(f"Compressão rejeitada: extensão inválida ({ext})")
        raise HTTPException(status_code=415, detail="Apenas arquivos .pdf podem ser comprimidos.")

    # Nomes únicos para input e output (UUID — sem caracteres injetáveis)
    uid = uuid.uuid4().hex
    temp_pdf   = OUTPUT_DIR / f"{uid}_in.pdf"
    output_pdf = OUTPUT_DIR / f"{uid}.pdf"

    try:
        # ─── Salva e valida o upload ───
        magic_check = await _salvar_upload_validado(file, temp_pdf, MAX_FILE_SIZE)

        if not magic_check.startswith(PDF_MAGIC):
            log.warning(f"Compressão rejeitada: não é PDF válido (magic: {magic_check!r})")
            remover_arquivo_seguro(str(temp_pdf))
            raise HTTPException(status_code=415, detail="O arquivo enviado não é um PDF válido.")

        # ─── Comprime em threadpool ───
        # Toda a lógica de bomba/encriptação/etc. está dentro do compress_pdf
        try:
            result = await run_in_threadpool(
                compress_pdf,
                str(temp_pdf),
                str(output_pdf),
            )
        except ValueError as ve:
            # Erros de validação semântica: criptografado, bomba, corrompido
            log.warning(f"PDF rejeitado na compressão: {ve}")
            remover_arquivo_seguro(str(temp_pdf))
            if output_pdf.exists():
                remover_arquivo_seguro(str(output_pdf))
            raise HTTPException(status_code=422, detail=str(ve))

        # ─── Remove o arquivo de entrada (já temos o output) ───
        remover_arquivo_seguro(str(temp_pdf))

        # ─── Prepara nome de download (sanitizado) ───
        nome_original = Path(file.filename).stem
        nome_original = "".join(c for c in nome_original if c.isalnum() or c in "._- ")[:80]
        nome_download = f"Mway_{nome_original}_comprimido.pdf"

        log.info(
            f"Compressão entregue | {result.original_size} → {result.compressed_size} bytes "
            f"({result.reduction_percent}%) | comprimido={result.was_compressed}"
        )

        # ─── BackgroundTask remove o output após download ───
        background_tasks = BackgroundTasks()
        background_tasks.add_task(remover_arquivo_seguro, str(output_pdf))

        # ─── Resposta com estatísticas nos headers customizados ───
        # Como devolvemos FileResponse (não JSON), as estatísticas vão
        # em headers HTTP customizados (X-*). Frontend lê e exibe.
        return FileResponse(
            path=str(output_pdf),
            filename=nome_download,
            media_type="application/pdf",
            background=background_tasks,
            headers={
                "X-Original-Size": str(result.original_size),
                "X-Compressed-Size": str(result.compressed_size),
                "X-Reduction-Percent": str(result.reduction_percent),
                "X-Was-Compressed": "true" if result.was_compressed else "false",
                "X-Pages": str(result.pages),
                # Importantíssimo: navegador precisa expor headers customizados via CORS
                "Access-Control-Expose-Headers": (
                    "X-Original-Size, X-Compressed-Size, X-Reduction-Percent, "
                    "X-Was-Compressed, X-Pages"
                ),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Erro na compressão: {str(e)}", exc_info=True)
        if temp_pdf.exists():
            remover_arquivo_seguro(str(temp_pdf))
        if output_pdf.exists():
            remover_arquivo_seguro(str(output_pdf))
        raise HTTPException(status_code=500, detail="Erro interno ao comprimir o arquivo.")


# ══════════════════════════════════════════════════════
#  ROTA 4 — Download do PDF unificado (merge)
# ══════════════════════════════════════════════════════
@router.get("/download/{file_id}")
async def download_pdf(file_id: str, background_tasks: BackgroundTasks):
    log.info(f"Download solicitado | file_id: {file_id}")

    if not validar_nome_seguro(file_id):
        log.warning(f"Download negado: nome inválido | ID: {file_id}")
        raise HTTPException(status_code=400, detail="Identificador de arquivo inválido.")

    file_path = OUTPUT_DIR / file_id

    if not file_path.exists():
        log.warning(f"Download negado: arquivo não encontrado | ID: {file_id}")
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    log.info(f"Download iniciado | Arquivo: {file_id}")
    background_tasks.add_task(remover_arquivo_seguro, str(file_path))

    return FileResponse(
        path=file_path,
        filename="Mway_unificado.pdf",
        media_type="application/pdf"
    )