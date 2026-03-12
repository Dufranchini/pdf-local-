    const fileInput = document.getElementById('pdfInput');
    const fileList = document.getElementById('fileList');
    const clearBtn = document.getElementById('clearBtn');

    function createFileItem(name) {
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
      row.querySelector('.remove-btn').addEventListener('click', () => row.remove());
      return row;
    }

    fileInput.addEventListener('change', (event) => {
      const files = Array.from(event.target.files || []);
      files.forEach(file => fileList.appendChild(createFileItem(file.name)));
      fileInput.value = '';
    });

    document.querySelectorAll('.remove-btn').forEach(btn => {
      btn.addEventListener('click', (e) => e.currentTarget.closest('.file-item').remove());
    });

    clearBtn.addEventListener('click', () => {
      fileList.innerHTML = '';
    });
