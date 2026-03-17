from pathlib import Path
import shutil
import tempfile
import uuid

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

# Importação da conversão de imagens que você já possuía
from services.conversion.image_converter import convert_image_to_pdf
# NOVA IMPORTAÇÃO: Nossa nova função de conversão via LibreOffice
from services.conversion.office_converter import convert_office_to_pdf
from services.pdf.merge import merge_pdfs

router = APIRouter()

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


@router.post("/merge")
async def merge_files(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")

    try:
        pdfs_para_juntar = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            for file in files:
                file_path = temp_path / file.filename

                # Salva o arquivo enviado no diretório temporário
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)

                ext = file_path.suffix.lower()

                # Separação da lógica de conversão dependendo da extensão do arquivo
                if ext == ".pdf":
                    # Se já for PDF, adiciona direto à lista
                    pdfs_para_juntar.append(str(file_path))
                    
                elif ext in [".jpg", ".jpeg", ".png"]:
                    # Se for imagem, converte usando sua função existente
                    pdf_convertido = convert_image_to_pdf(str(file_path), str(temp_path))
                    pdfs_para_juntar.append(pdf_convertido)
                    
                # NOVA CONDIÇÃO: Tratamento para arquivos do Word (DOC e DOCX)
                elif ext in [".doc", ".docx"]:
                    # Converte o arquivo Office para PDF no diretório temporário
                    pdf_convertido = convert_office_to_pdf(str(file_path), str(temp_path))
                    pdfs_para_juntar.append(pdf_convertido)
                    
                else:
                    raise HTTPException(status_code=400, detail=f"Formato não suportado: {ext}")

            # Gera um nome único para o PDF final agrupado
            file_id = f"{uuid.uuid4()}.pdf"
            output_file = OUTPUT_DIR / file_id

            # Faz a junção final
            merge_pdfs(pdfs_para_juntar, str(output_file))

        return {
            "success": True,
            "download_url": f"/api/pdf/download/{file_id}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{file_id}")
async def download_pdf(file_id: str):
    file_path = OUTPUT_DIR / file_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(
        path=file_path,
        filename="Unificado.pdf",
        media_type="application/pdf"
    )