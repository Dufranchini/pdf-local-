# 📄 Unificador de PDFs Corporativo

Um sistema web rápido, seguro e eficiente desenvolvido para unificar múltiplos arquivos (PDFs, Imagens, Word e Excel) num único documento PDF padronizado (A4). 

Criado com foco em segurança de infraestrutura e usabilidade, este projeto processa ficheiros localmente no servidor, garantindo a privacidade dos dados corporativos.

---

## ✨ Funcionalidades Principais

* **Múltiplos Formatos:** Suporta `.pdf`, `.jpg`, `.png`, `.docx`, `.xlsx`, entre outros.
* **Conversão Automática (Headless):** Converte nativamente arquivos do pacote Office em PDF utilizando o LibreOffice em background.
* **Padronização A4:** Redimensiona todas as páginas de origens diferentes para o formato padrão A4 perfeitamente.
* **Segurança e Anti-DoS:** Bloqueio no Frontend e Backend para arquivos que excedam 10MB no total ou uploads com mais de 10 ficheiros de uma vez.
* **Garbage Collection:** Limpeza automática de arquivos temporários e do PDF final logo após o download do utilizador.
* **Interface Moderna:** UI limpa com suporte nativo a **Dark Mode** salvo na memória do navegador (LocalStorage).

---

## 🛠️ Tecnologias Utilizadas

**Backend:**
* [Python 3](https://www.python.org/)
* [FastAPI](https://fastapi.tiangolo.com/) (Framework Web assíncrono de alta performance)
* [Uvicorn](https://www.uvicorn.org/) (Servidor ASGI)
* [pypdf](https://pypi.org/project/pypdf/) (Manipulação avançada de PDFs)

**Frontend:**
* HTML5, CSS3 (Vanilla)
* JavaScript Assíncrono (Fetch API)

**Infraestrutura / Deploy:**
* Linux (Ubuntu)
* Nginx (Proxy Reverso)
* Systemd (Gerenciamento de Serviços em Background)
* LibreOffice Core (Motor de conversão de documentos)

---

## 🚀 Como Rodar Localmente (Ambiente de Desenvolvimento)

### 1. Pré-requisitos
Certifique-se de que tem o Python instalado e o LibreOffice configurado no seu sistema para que as conversões de Excel/Word funcionem. No Ubuntu/WSL:
```bash
sudo apt update
sudo apt install libreoffice-core libreoffice-writer libreoffice-calc --no-install-recommends

2. Instalação
Clone o repositório e crie o ambiente virtual:

Bash
# Clone o repositório
git clone [https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git](https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git)
cd NOME_DO_REPOSITORIO

# Crie e ative o ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt
3. Configuração
Crie um arquivo .env na raiz do projeto e defina o caminho do LibreOffice:

Snippet de código
LIBREOFFICE_PATH="libreoffice"
4. Executando a Aplicação
Inicie o servidor de desenvolvimento:

Bash
uvicorn main:app --reload
Acesse no seu navegador: http://localhost:8000
