# main.py
import hashlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from routers.pdf_router import router as pdf_router

app = FastAPI()
app.include_router(pdf_router, prefix="/api/pdf", tags=["pdf"])
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def file_hash(path: str) -> str:
    """Gera um hash curto do conteúdo do arquivo — muda só quando o arquivo muda."""
    conteudo = Path(path).read_bytes()
    return hashlib.md5(conteudo).hexdigest()[:8]

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "css_v": file_hash("static/style.css"),
            "js_v":  file_hash("static/script.js"),
        }
    )