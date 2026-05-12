// ==========================================
// Dark / Light Mode (Tema)
// ==========================================
const themeToggle = document.getElementById('themeToggle');
const body = document.body;

if (localStorage.getItem('tema') === 'escuro') {
  body.classList.add('dark-mode');
}

themeToggle.addEventListener('click', () => {
  body.classList.toggle('dark-mode');
  localStorage.setItem('tema', body.classList.contains('dark-mode') ? 'escuro' : 'claro');
});

// ==========================================
// Lógica Principal dos PDFs
// ==========================================
const fileInput   = document.getElementById('pdfInput');
const fileList    = document.getElementById('fileList');
const clearBtn    = document.getElementById('clearBtn');
const generateBtn = document.getElementById('generateBtn');

let selectedFiles  = [];
let dragSourceIndex = null;

// ==========================================
// Renderização da lista de cards
// ==========================================
function renderFileList() {
  fileList.innerHTML = '';

  if (selectedFiles.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'file-list-empty';
    empty.textContent = 'Nenhum arquivo adicionado ainda.';
    fileList.appendChild(empty);
    return;
  }

  selectedFiles.forEach((file, index) => {
    fileList.appendChild(createFileCard(file, index));
  });
}

// ==========================================
// Criação de cada card
// ==========================================
function createFileCard(file, index) {
  const card = document.createElement('div');
  card.className = 'file-card';
  card.draggable = true;
  card.dataset.index = index;

  // Número de ordem + ícone + nome + botão remover
  card.innerHTML = `
    <div class="file-card-left">
      <span class="file-order">${index + 1}</span>
      <span class="file-card-icon"></span>
      <span class="file-card-name"></span>
    </div>
    <div class="file-card-right">
      <span class="drag-hint">⠿</span>
      <button class="remove-btn" type="button" title="Remover">×</button>
    </div>
  `;

  card.querySelector('.file-card-name').textContent = file.name;

  card.querySelector('.remove-btn').addEventListener('click', (e) => {
    e.stopPropagation(); // evita disparar eventos de drag ao clicar no botão
    selectedFiles.splice(index, 1);
    renderFileList();
  });

  // ── Eventos de Drag ──────────────────────────────────────

  card.addEventListener('dragstart', (e) => {
    dragSourceIndex = index;
    e.dataTransfer.effectAllowed = 'move';
    // Delay para o "fantasma" nativo do browser ser capturado antes de aplicar o estilo
    setTimeout(() => card.classList.add('dragging'), 0);
  });

  card.addEventListener('dragend', () => {
    card.classList.remove('dragging');
    // Remove highlight de todos os cards ao terminar
    document.querySelectorAll('.file-card').forEach(c => c.classList.remove('drag-over-top', 'drag-over-bottom'));
    dragSourceIndex = null;
  });

  card.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (dragSourceIndex === null || dragSourceIndex === index) return;

    // Descobre se o cursor está na metade de cima ou de baixo do card
    const rect = card.getBoundingClientRect();
    const meio = rect.top + rect.height / 2;

    card.classList.remove('drag-over-top', 'drag-over-bottom');
    if (e.clientY < meio) {
      card.classList.add('drag-over-top');
    } else {
      card.classList.add('drag-over-bottom');
    }
  });

  card.addEventListener('dragleave', (e) => {
    // Só remove o highlight se o cursor realmente saiu do card
    // (dragleave dispara ao entrar em elementos filhos — verificamos o relatedTarget)
    if (!card.contains(e.relatedTarget)) {
      card.classList.remove('drag-over-top', 'drag-over-bottom');
    }
  });

  card.addEventListener('drop', (e) => {
    e.preventDefault();
    if (dragSourceIndex === null || dragSourceIndex === index) return;

    const rect = card.getBoundingClientRect();
    const meio = rect.top + rect.height / 2;
    const inserirAntes = e.clientY < meio;

    // Calcula o índice de destino com base em onde o cursor soltou
    let destinoIndex = inserirAntes ? index : index + 1;

    // Remove o item da posição original
    const [movido] = selectedFiles.splice(dragSourceIndex, 1);

    // Ajusta o destino após a remoção (o array encolheu em 1)
    if (dragSourceIndex < destinoIndex) {
      destinoIndex--;
    }

    selectedFiles.splice(destinoIndex, 0, movido);
    renderFileList();
  });

  return card;
}

// ==========================================
// Eventos de controle da lista
// ==========================================
fileInput.addEventListener('change', (event) => {
  const files = Array.from(event.target.files || []);
  selectedFiles.push(...files);
  renderFileList();
  fileInput.value = '';
});

clearBtn.addEventListener('click', () => {
  selectedFiles = [];
  renderFileList();
});

// ==========================================
// Evento principal: Juntar e Gerar
// ==========================================
generateBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) {
    alert('Por favor, adicione pelo menos um ficheiro.');
    return;
  }

  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  let totalSize = 0;
  selectedFiles.forEach(file => { totalSize += file.size; });

  if (totalSize > MAX_FILE_SIZE) {
    alert('⚠️ O tamanho total dos arquivos excede o limite de 10MB. Por favor, remova alguns arquivos e tente novamente.');
    return;
  }

  const formData = new FormData();
  selectedFiles.forEach(file => { formData.append('files', file); });

  try {
    generateBtn.disabled    = true;
    generateBtn.textContent = 'A processar...';

    const response = await fetch('/api/pdf/merge', {
      method: 'POST',
      body: formData
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Erro ao gerar o PDF.');
    }

    const downloadResponse = await fetch(data.download_url);
    if (!downloadResponse.ok) {
      throw new Error('Erro ao descarregar o PDF gerado.');
    }

    const blob = await downloadResponse.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = 'Mway_unificado.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

  } catch (error) {
    alert(error.message);
  } finally {
    generateBtn.disabled    = false;
    generateBtn.textContent = '🔗 Juntar e Gerar PDF Unificado';
  }
});