
// Referências aos elementos do nosso ecrã (HTML)
const fileInput = document.getElementById('pdfInput');
const fileList = document.getElementById('fileList');
const clearBtn = document.getElementById('clearBtn');
const generateBtn = document.getElementById('generateBtn');

// Lista que vai guardar os ficheiros selecionados em memória
let selectedFiles = [];

// Função para criar o elemento visual de cada ficheiro na lista
function createFileItem(name, index) {
  const row = document.createElement('div');
  row.className = 'file-item';
  row.innerHTML = `
      <div class="file-left">
        <span class="pdf-icon"></span>
        <span class="file-name"></span>
      </div>
      <button class="remove-btn" type="button">×</button>
    `;

  row.querySelector('.file-name').textContent = name;

  // Adiciona o evento para remover o ficheiro específico da lista
  row.querySelector('.remove-btn').addEventListener('click', () => {
    selectedFiles.splice(index, 1);
    renderFileList();
  });

  return row;
}

// Função para atualizar a lista de ficheiros no ecrã
function renderFileList() {
  fileList.innerHTML = '';
  selectedFiles.forEach((file, index) => {
    fileList.appendChild(createFileItem(file.name, index));
  });
}

// Evento disparado quando o utilizador escolhe ficheiros no computador
fileInput.addEventListener('change', (event) => {
  const files = Array.from(event.target.files || []);
  selectedFiles.push(...files);
  renderFileList();
  fileInput.value = ''; // Limpa o input para permitir selecionar o mesmo ficheiro novamente
});

// Evento para limpar toda a lista
clearBtn.addEventListener('click', () => {
  selectedFiles = [];
  renderFileList();
});

// ==========================================
// Evento principal: Juntar e Gerar
// ==========================================
generateBtn.addEventListener('click', async () => {
  // Verifica se há ficheiros para processar
  if (!selectedFiles.length) {
    alert('Por favor, adicione pelo menos um ficheiro.');
    return;
  }

  // 1. CAMADA DE SEGURANÇA FRONTEND (Bloqueio de 10MB)
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB em bytes
  let totalSize = 0;
  selectedFiles.forEach(file => {
    totalSize += file.size;
  });

  if (totalSize > MAX_FILE_SIZE) {
    alert('⚠️ O tamanho total dos arquivos excede o limite de 10MB. Por favor, remova alguns arquivos e tente novamente.');
    return; // Corta a execução aqui, nada é apagado e o servidor nem é incomodado!
  }

  // 2. Preparar os dados para enviar ao servidor
  const formData = new FormData();
  selectedFiles.forEach(file => {
    formData.append('files', file);
  });

  try {
    // Desativa o botão para evitar cliques duplos e avisa que está a trabalhar
    generateBtn.disabled = true;
    generateBtn.textContent = 'A processar...';

    // 3. Enviar os ficheiros para o nosso servidor
    const response = await fetch('/api/pdf/merge', {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    // Verifica se o servidor devolveu algum erro
    if (!response.ok) {
      throw new Error(data.detail || 'Erro ao gerar o PDF.');
    }

    // 4. Descarregar o PDF final gerado
    const downloadResponse = await fetch(data.download_url);
    if (!downloadResponse.ok) {
      throw new Error('Erro ao descarregar o PDF gerado.');
    }

    const blob = await downloadResponse.blob();

    // 5. CAMADA DE SEGURANÇA DO DOWNLOAD (O Padrão Blindado)
    // Usando este método, o navegador trata do download. 
    // Se um arquivo com o mesmo nome existir, o navegador cria "Unificado (1).pdf" 
    // ou, se configurado para perguntar, só sobrescreve o arquivo no fim de tudo, com sucesso garantido.
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'Unificado.pdf';
    document.body.appendChild(a);
    a.click();
    
    // Limpeza
    a.remove();
    URL.revokeObjectURL(url);

  } catch (error) {
    // Mostra um alerta caso algo corra mal durante o processo
    alert(error.message);
  } finally {
    // Restaura o botão ao estado original, independentemente de sucesso ou erro
    generateBtn.disabled = false;
    generateBtn.textContent = '🔗 Juntar e Gerar PDF Unificado';
  }
});
