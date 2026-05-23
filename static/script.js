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
// HELPER: formata tamanho de bytes em string legível
// ==========================================
function formatarTamanho(bytes) {
  if (!bytes || bytes < 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 ? 2 : 1)} ${units[i]}`;
}

// ==========================================
// Lógica Principal dos PDFs (Merge)
// ==========================================
const fileInput   = document.getElementById('pdfInput');
const fileList    = document.getElementById('fileList');
const clearBtn    = document.getElementById('clearBtn');
const generateBtn = document.getElementById('generateBtn');

let selectedFiles   = [];
let dragSourceIndex = null;

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

function createFileCard(file, index) {
  const card = document.createElement('div');
  card.className = 'file-card';
  card.draggable = true;
  card.dataset.index = index;
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
    e.stopPropagation();
    selectedFiles.splice(index, 1);
    renderFileList();
  });
  card.addEventListener('dragstart', (e) => {
    dragSourceIndex = index;
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => card.classList.add('dragging'), 0);
  });
  card.addEventListener('dragend', () => {
    card.classList.remove('dragging');
    document.querySelectorAll('.file-card').forEach(c =>
      c.classList.remove('drag-over-top', 'drag-over-bottom')
    );
    dragSourceIndex = null;
  });
  card.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (dragSourceIndex === null || dragSourceIndex === index) return;
    const meio = card.getBoundingClientRect().top + card.getBoundingClientRect().height / 2;
    card.classList.remove('drag-over-top', 'drag-over-bottom');
    card.classList.add(e.clientY < meio ? 'drag-over-top' : 'drag-over-bottom');
  });
  card.addEventListener('dragleave', (e) => {
    if (!card.contains(e.relatedTarget)) {
      card.classList.remove('drag-over-top', 'drag-over-bottom');
    }
  });
  card.addEventListener('drop', (e) => {
    e.preventDefault();
    if (dragSourceIndex === null || dragSourceIndex === index) return;
    const meio = card.getBoundingClientRect().top + card.getBoundingClientRect().height / 2;
    let destinoIndex = e.clientY < meio ? index : index + 1;
    const [movido] = selectedFiles.splice(dragSourceIndex, 1);
    if (dragSourceIndex < destinoIndex) destinoIndex--;
    selectedFiles.splice(destinoIndex, 0, movido);
    renderFileList();
  });
  return card;
}

fileInput.addEventListener('change', (event) => {
  selectedFiles.push(...Array.from(event.target.files || []));
  renderFileList();
  fileInput.value = '';
});

clearBtn.addEventListener('click', () => {
  selectedFiles = [];
  renderFileList();
});

generateBtn.addEventListener('click', async () => {
  if (!selectedFiles.length) {
    alert('Por favor, adicione pelo menos um ficheiro.');
    return;
  }
  const MAX_FILE_SIZE = 10 * 1024 * 1024;
  let totalSize = 0;
  selectedFiles.forEach(file => { totalSize += file.size; });
  if (totalSize > MAX_FILE_SIZE) {
    alert('⚠️ O tamanho total dos arquivos excede o limite de 10MB.');
    return;
  }
  const formData = new FormData();
  selectedFiles.forEach(file => formData.append('files', file));
  try {
    generateBtn.disabled    = true;
    generateBtn.textContent = 'A processar...';
    const response = await fetch('/api/pdf/merge', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Erro ao gerar o PDF.');
    const downloadResponse = await fetch(data.download_url);
    if (!downloadResponse.ok) throw new Error('Erro ao descarregar o PDF gerado.');
    const blob = await downloadResponse.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = 'Mway_unificado.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    alert(error.message);
  } finally {
    generateBtn.disabled    = false;
    generateBtn.textContent = '🔗 Juntar e Gerar PDF Unificado';
  }
});

// ==========================================
// MODAL — Conversor PDF → DOCX
// ==========================================
const convertToDocBtn = document.getElementById('convertToDocBtn');
const modalOverlay    = document.getElementById('modalOverlay');
const modalClose      = document.getElementById('modalClose');
const docInput        = document.getElementById('docInput');
const dropZone        = document.getElementById('dropZone');
const dropZoneText    = document.getElementById('dropZoneText');
const convertBtn      = document.getElementById('convertBtn');

let selectedPdf = null;

convertToDocBtn.addEventListener('click', () => modalOverlay.classList.add('active'));
modalClose.addEventListener('click', fecharModal);
modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) fecharModal(); });

function fecharModal() {
  modalOverlay.classList.remove('active');
  selectedPdf = null;
  docInput.value = '';
  dropZoneText.textContent = 'Clique para selecionar ou arraste o PDF aqui';
  dropZone.classList.remove('drop-zone-ready');
  convertBtn.disabled = true;
  esconderErro('modalErrorBox', '.modal-overlay#modalOverlay');
}

docInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) selecionarPdf(file);
});
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drop-zone-hover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drop-zone-hover'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drop-zone-hover');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    mostrarErro('modalErrorBox', '#modalOverlay .modal-footer',
                '⚠️ Apenas arquivos .pdf são aceitos aqui.');
    return;
  }
  selecionarPdf(file);
});

function selecionarPdf(file) {
  esconderErro('modalErrorBox', '#modalOverlay');
  selectedPdf = file;
  const nomeCurto = file.name.length > 45 ? file.name.substring(0, 42) + '...' : file.name;
  dropZoneText.textContent = `✅ ${nomeCurto}`;
  dropZone.classList.add('drop-zone-ready');
  convertBtn.disabled = false;
}

convertBtn.addEventListener('click', async () => {
  if (!selectedPdf) return;
  const MAX = 10 * 1024 * 1024;
  if (selectedPdf.size > MAX) {
    mostrarErro('modalErrorBox', '#modalOverlay .modal-footer', '⚠️ O arquivo excede o limite de 10MB.');
    return;
  }
  const formData = new FormData();
  formData.append('file', selectedPdf);
  try {
    esconderErro('modalErrorBox', '#modalOverlay');
    convertBtn.disabled    = true;
    convertBtn.textContent = '⏳ Convertendo...';
    const response = await fetch('/api/pdf/convert-to-doc', { method: 'POST', body: formData });
    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Erro ao converter o PDF.');
    }
    const blob = await response.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const nomeBase = selectedPdf.name.replace(/\.pdf$/i, '');
    a.href = url; a.download = `Mway_${nomeBase}.docx`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    fecharModal();
  } catch (error) {
    mostrarErro('modalErrorBox', '#modalOverlay .modal-footer', error.message);
  } finally {
    convertBtn.disabled    = false;
    convertBtn.textContent = '⚙️ Converter para Word';
  }
});

// ==========================================
// HELPERS: caixas de erro genéricas
// (precisamos identificar por seletor pra suportar 2 modais)
// ==========================================
function mostrarErro(boxId, beforeSelector, mensagem) {
  let box = document.getElementById(boxId);
  if (!box) {
    box = document.createElement('div');
    box.id = boxId;
    box.className = 'modal-error-box';
    const ref = document.querySelector(beforeSelector);
    if (ref) ref.before(box);
  }
  box.textContent = mensagem;
  box.style.display = 'block';
}

function esconderErro(boxId, _scopeSelector) {
  const box = document.getElementById(boxId);
  if (box) box.style.display = 'none';
}

// ==========================================
// MODAL — Compressor PDF
// ==========================================
const compressBtn          = document.getElementById('compressBtn');
const compressModalOverlay = document.getElementById('compressModalOverlay');
const compressModalClose   = document.getElementById('compressModalClose');
const compressInput        = document.getElementById('compressInput');
const compressDropZone     = document.getElementById('compressDropZone');
const compressDropZoneText = document.getElementById('compressDropZoneText');
const doCompressBtn        = document.getElementById('doCompressBtn');
const compressResult       = document.getElementById('compressResult');
const statOriginal         = document.getElementById('statOriginal');
const statCompressed       = document.getElementById('statCompressed');
const statReduction        = document.getElementById('statReduction');
const statNote             = document.getElementById('statNote');

let compressFile = null;
let compressedBlob = null;  // guarda o blob para download depois de mostrar stats

compressBtn.addEventListener('click', () => compressModalOverlay.classList.add('active'));
compressModalClose.addEventListener('click', fecharCompressModal);
compressModalOverlay.addEventListener('click', (e) => {
  if (e.target === compressModalOverlay) fecharCompressModal();
});

function fecharCompressModal() {
  compressModalOverlay.classList.remove('active');
  compressFile = null;
  compressedBlob = null;
  compressInput.value = '';
  compressDropZoneText.textContent = 'Clique para selecionar ou arraste o PDF aqui';
  compressDropZone.classList.remove('drop-zone-ready');
  doCompressBtn.disabled = true;
  doCompressBtn.textContent = '⚙️ Comprimir PDF';
  compressResult.style.display = 'none';
  esconderErro('compressErrorBox', '#compressModalOverlay');
}

compressInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) selecionarParaComprimir(file);
});

compressDropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  compressDropZone.classList.add('drop-zone-hover');
});
compressDropZone.addEventListener('dragleave', () =>
  compressDropZone.classList.remove('drop-zone-hover')
);
compressDropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  compressDropZone.classList.remove('drop-zone-hover');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    mostrarErro('compressErrorBox', '#compressModalOverlay .modal-footer',
                '⚠️ Apenas arquivos .pdf são aceitos aqui.');
    return;
  }
  selecionarParaComprimir(file);
});

function selecionarParaComprimir(file) {
  esconderErro('compressErrorBox', '#compressModalOverlay');
  compressFile = file;
  compressedBlob = null;  // reset
  const nomeCurto = file.name.length > 45 ? file.name.substring(0, 42) + '...' : file.name;
  compressDropZoneText.textContent = `✅ ${nomeCurto} (${formatarTamanho(file.size)})`;
  compressDropZone.classList.add('drop-zone-ready');
  doCompressBtn.disabled = false;
  doCompressBtn.textContent = '⚙️ Comprimir PDF';
  compressResult.style.display = 'none';
}

doCompressBtn.addEventListener('click', async () => {
  // Se já temos um blob comprimido, este clique = download
  if (compressedBlob) {
    baixarComprimido(compressedBlob);
    return;
  }

  if (!compressFile) return;
  const MAX = 10 * 1024 * 1024;
  if (compressFile.size > MAX) {
    mostrarErro('compressErrorBox', '#compressModalOverlay .modal-footer',
                '⚠️ O arquivo excede o limite de 10MB.');
    return;
  }

  const formData = new FormData();
  formData.append('file', compressFile);

  try {
    esconderErro('compressErrorBox', '#compressModalOverlay');
    doCompressBtn.disabled    = true;
    doCompressBtn.textContent = '⏳ Comprimindo...';

    const response = await fetch('/api/pdf/compress', { method: 'POST', body: formData });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.detail || 'Erro ao comprimir o PDF.');
    }

    // Lê estatísticas dos headers HTTP customizados
    const originalSize    = parseInt(response.headers.get('X-Original-Size')   || '0');
    const compressedSize  = parseInt(response.headers.get('X-Compressed-Size') || '0');
    const reductionPct    = parseFloat(response.headers.get('X-Reduction-Percent') || '0');
    const wasCompressed   = response.headers.get('X-Was-Compressed') === 'true';

    compressedBlob = await response.blob();

    // ── Atualiza UI com estatísticas ──
    statOriginal.textContent = formatarTamanho(originalSize);
    statCompressed.textContent = formatarTamanho(compressedSize);
    statReduction.textContent = `${reductionPct.toFixed(1)}% de redução`;

    if (wasCompressed) {
      statReduction.classList.remove('stat-reduction-neutral');
      statReduction.classList.add('stat-reduction-good');
      statNote.textContent = '✓ Metadados removidos por privacidade.';
    } else {
      statReduction.textContent = 'Compressão não aplicada';
      statReduction.classList.remove('stat-reduction-good');
      statReduction.classList.add('stat-reduction-neutral');
      statNote.textContent = 'Este PDF já está bem otimizado. O arquivo original será baixado.';
    }

    compressResult.style.display = 'block';

    // Troca o botão para "baixar"
    doCompressBtn.textContent = '⬇️ Baixar PDF';
    doCompressBtn.disabled = false;

  } catch (error) {
    mostrarErro('compressErrorBox', '#compressModalOverlay .modal-footer', error.message);
    doCompressBtn.disabled = false;
    doCompressBtn.textContent = '⚙️ Comprimir PDF';
  }
});

function baixarComprimido(blob) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  const nomeBase = compressFile.name.replace(/\.pdf$/i, '');
  a.href = url; a.download = `Mway_${nomeBase}_comprimido.pdf`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  fecharCompressModal();
}