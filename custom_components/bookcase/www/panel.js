class BookcasePanel extends HTMLElement {
  constructor() {
    super();
    this._loading = false;
    this._filter = 'all';
    this._searchQuery = '';
  }

  set hass(hass) {
    const oldBooks = this._hass?.states['sensor.bookcase_total_books']?.attributes?.books;
    this._hass = hass;
    const newBooks = hass.states['sensor.bookcase_total_books']?.attributes?.books;

    if (!this.content) {
      this.initStructure();
    }

    if (JSON.stringify(oldBooks) !== JSON.stringify(newBooks)) {
      this._loading = false;
      this.render();
      this.updateAddButton();
    }
  }

  initStructure() {
    this.innerHTML = `
      <style>
        :host {
          background-color: var(--primary-background-color);
          display: block;
          height: 100%;
          color: var(--primary-text-color);
          font-family: 'Roboto', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }
        .container {
          max-width: 1200px;
          margin: 0 auto;
          padding: 32px 16px;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 30px;
        }
        .header h1 {
          margin: 0;
          font-size: 2.5rem;
          font-weight: 800;
          background: linear-gradient(135deg, var(--primary-color), #ff9800);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
        }
        
        .toolbar {
          display: flex;
          flex-direction: column;
          gap: 20px;
          margin-bottom: 40px;
        }

        .filter-bar {
          display: flex;
          gap: 10px;
          overflow-x: auto;
          padding-bottom: 5px;
          scrollbar-width: none;
        }
        .filter-bar::-webkit-scrollbar { display: none; }
        
        .filter-btn {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
          padding: 8px 16px;
          border-radius: 20px;
          cursor: pointer;
          white-space: nowrap;
          font-weight: 500;
          transition: all 0.2s;
        }
        .filter-btn.active {
          background: var(--primary-color);
          color: white;
          border-color: var(--primary-color);
          box-shadow: 0 4px 10px var(--primary-color-alpha, rgba(3, 169, 244, 0.3));
        }

        .search-add-row {
          display: flex;
          gap: 15px;
        }
        .search-box {
          flex-grow: 1;
          display: flex;
          align-items: center;
          background: var(--card-background-color);
          border-radius: 12px;
          padding: 0 15px;
          border: 1px solid var(--divider-color);
        }
        .search-box input {
          background: transparent;
          border: none;
          padding: 12px;
          width: 100%;
          color: var(--primary-text-color);
          outline: none;
        }

        .add-box {
          display: flex;
          background: var(--card-background-color);
          border-radius: 12px;
          border: 1px solid var(--divider-color);
          padding: 5px;
          width: 350px;
        }
        .add-box input {
          background: transparent;
          border: none;
          padding: 10px;
          flex-grow: 1;
          color: var(--primary-text-color);
          outline: none;
        }
        button#add-btn {
          background: var(--primary-color);
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 8px;
          cursor: pointer;
          font-weight: bold;
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 25px;
        }
        .book-card {
          background: var(--card-background-color);
          border-radius: 12px;
          padding: 10px;
          box-shadow: 0 4px 15px rgba(0,0,0,0.05);
          transition: all 0.3s;
          position: relative;
          cursor: pointer;
          border: 1px solid transparent;
        }
        .book-card:hover {
          transform: translateY(-8px);
          box-shadow: 0 12px 25px rgba(0,0,0,0.1);
          border-color: var(--primary-color);
        }
        .cover-wrapper {
          position: relative;
          width: 100%;
          aspect-ratio: 2/3;
          border-radius: 8px;
          overflow: hidden;
        }
        .book-card img { width: 100%; height: 100%; object-fit: cover; }
        .book-title {
          font-weight: 700;
          margin-top: 10px;
          font-size: 0.9rem;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
          min-height: 2.4rem;
        }
        .status-badge {
          position: absolute;
          top: 8px;
          right: 8px;
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.6rem;
          font-weight: bold;
          color: white;
          background: rgba(0,0,0,0.7);
        }
        .lent-badge {
          position: absolute;
          bottom: 8px;
          left: 8px;
          background: #ff9800;
          color: white;
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.6rem;
          font-weight: bold;
        }

        /* Modal Styles */
        .modal {
          display: none;
          position: fixed;
          top: 0; left: 0; width: 100%; height: 100%;
          background: rgba(0,0,0,0.85);
          z-index: 1000;
          align-items: center; justify-content: center;
          padding: 20px;
        }
        .modal.open { display: flex; }
        .modal-content {
          background: var(--card-background-color);
          max-width: 900px;
          width: 100%;
          border-radius: 20px;
          display: flex;
          overflow: hidden;
          position: relative;
          max-height: 90vh;
        }
        .modal-close {
          position: absolute; top: 15px; right: 15px;
          width: 35px; height: 35px; border-radius: 50%;
          background: var(--secondary-background-color);
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; font-size: 20px; z-index: 11;
        }
        .modal-body { display: flex; width: 100%; overflow-y: auto; }
        .modal-left { width: 300px; flex-shrink: 0; background: #111; }
        .modal-left img { width: 100%; height: 100%; object-fit: cover; }
        .modal-right { padding: 30px; flex-grow: 1; display: flex; flex-direction: column; gap: 20px; }
        
        .form-group { display: flex; flex-direction: column; gap: 8px; }
        label { font-size: 0.8rem; font-weight: bold; color: var(--secondary-text-color); text-transform: uppercase; }
        select, textarea, .text-input {
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          color: var(--primary-text-color);
          padding: 10px;
          border-radius: 8px;
          font-size: 1rem;
        }
        .rating-stars { display: flex; gap: 5px; font-size: 1.5rem; color: #ffca28; cursor: pointer; }
        
        .save-btn {
          background: var(--primary-color);
          color: white;
          border: none;
          padding: 12px;
          border-radius: 10px;
          font-weight: bold;
          cursor: pointer;
          margin-top: 10px;
        }
        
        .loading-spinner {
          display: none; width: 16px; height: 16px;
          border: 2px solid rgba(255,255,255,0.3);
          border-radius: 50%; border-top-color: #fff;
          animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        @media (max-width: 768px) {
          .modal-body { flex-direction: column; }
          .modal-left { width: 100%; height: 250px; }
          .search-add-row { flex-direction: column; }
          .add-box { width: 100%; }
        }
      </style>
      
      <div class="container">
        <div class="header">
          <h1>📚 Knihovnička</h1>
          <div id="stats" style="opacity: 0.7;"></div>
        </div>
        
        <div class="toolbar">
          <div class="search-add-row">
            <div class="search-box">
              <span style="opacity: 0.5;">🔍</span>
              <input type="text" id="search-input" placeholder="Hledat podle názvu nebo autora...">
            </div>
            <div class="add-box">
              <input type="text" id="isbn-input" placeholder="ISBN...">
              <button id="add-btn">
                <span class="loading-spinner" id="btn-spinner"></span>
                <span id="btn-text">Přidat</span>
              </button>
            </div>
          </div>
          
          <div class="filter-bar">
            <button class="filter-btn active" data-filter="all">Vše</button>
            <button class="filter-btn" data-filter="to_read">K přečtení</button>
            <button class="filter-btn" data-filter="reading">Rozečtené</button>
            <button class="filter-btn" data-filter="read">Přečtené</button>
            <button class="filter-btn" data-filter="lent">Půjčené</button>
          </div>
        </div>

        <div class="grid" id="book-grid"></div>
      </div>

      <div id="book-modal" class="modal">
        <div class="modal-content">
          <div class="modal-close">&times;</div>
          <div class="modal-body" id="modal-body"></div>
        </div>
      </div>
    `;

    this.content = this.querySelector('#book-grid');
    this.isbnInput = this.querySelector('#isbn-input');
    this.searchInput = this.querySelector('#search-input');
    this.addBtn = this.querySelector('#add-btn');
    this.modal = this.querySelector('#book-modal');
    this.modalClose = this.querySelector('.modal-close');

    this.addBtn.onclick = () => this.handleAdd();
    this.isbnInput.onkeypress = (e) => { if (e.key === 'Enter') this.handleAdd(); };
    this.searchInput.oninput = (e) => {
      this._searchQuery = e.target.value.toLowerCase();
      this.render();
    };

    this.querySelectorAll('.filter-btn').forEach(btn => {
      btn.onclick = () => {
        this.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this._filter = btn.dataset.filter;
        this.render();
      };
    });

    this.modalClose.onclick = () => this.modal.classList.remove('open');
    this.modal.onclick = (e) => { if (e.target === this.modal) this.modal.classList.remove('open'); };
  }

  handleAdd() {
    const isbn = this.isbnInput.value.trim();
    if (isbn && !this._loading) {
      this._loading = true;
      this.updateAddButton();
      this._hass.callService('bookcase', 'add_by_isbn', { isbn });
      this.isbnInput.value = '';
    }
  }

  updateAddButton() {
    const btnText = this.querySelector('#btn-text');
    const spinner = this.querySelector('#btn-spinner');
    if (this._loading) {
      this.addBtn.disabled = true;
      btnText.innerText = '...';
      spinner.style.display = 'block';
    } else {
      this.addBtn.disabled = false;
      btnText.innerText = 'Přidat';
      spinner.style.display = 'none';
    }
  }

  saveBook(bookId) {
    const status = this.querySelector('#edit-status').value;
    const rating = parseInt(this.querySelector('#edit-rating').dataset.value);
    const notes = this.querySelector('#edit-notes').value;
    const lentTo = this.querySelector('#edit-lent').value.trim() || null;
    const lentUntil = this.querySelector('#edit-lent-until').value || null;
    const readBy = this.querySelector('#edit-read-by').value.trim() || null;

    this._hass.callService('bookcase', 'update_book', {
      book_id: bookId,
      status: status,
      rating: rating,
      notes: notes,
      lent_to: lentTo,
      lent_until: lentUntil,
      is_read: status === 'read',
      read_by: readBy
    });
    
    this.modal.classList.remove('open');
  }

  deleteBook(bookId) {
    if (confirm('Opravdu chcete tuto knihu smazat?')) {
      this._hass.callService('bookcase', 'delete_book', { book_id: bookId });
      this.modal.classList.remove('open');
    }
  }

  openDetail(book) {
    const body = this.querySelector('#modal-body');
    const rating = book.rating || 0;
    const readBy = book.read_by || (book.is_read ? (this._hass.user.name || 'Uživatel') : '');

    body.innerHTML = `
      <div class="modal-left">
        <img src="${book.cover_url || ''}" onerror="this.src='https://via.placeholder.com/400x600?text=Bez+obalky'">
      </div>
      <div class="modal-right">
        <h2 style="margin:0;">${book.title}</h2>
        <div style="color:var(--primary-color); font-weight:500;">${book.authors ? book.authors.join(', ') : 'Neznámý autor'}</div>
        
        <div class="form-group">
          <label>Hodnocení</label>
          <div class="rating-stars" id="edit-rating" data-value="${rating}">
            ${[1,2,3,4,5].map(n => `<span data-n="${n}">${n <= rating ? '★' : '☆'}</span>`).join('')}
          </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 15px;">
          <div class="form-group">
            <label>Stav</label>
            <select id="edit-status">
              <option value="to_read" ${book.status === 'to_read' ? 'selected' : ''}>K přečtení</option>
              <option value="reading" ${book.status === 'reading' ? 'selected' : ''}>Rozečteno</option>
              <option value="read" ${book.status === 'read' ? 'selected' : ''}>Přečteno</option>
            </select>
          </div>
          <div class="form-group">
            <label>Přečetl(a)</label>
            <input type="text" id="edit-read-by" class="text-input" value="${readBy}" placeholder="Jméno uživatele...">
          </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 15px;">
          <div class="form-group">
            <label>Půjčeno komu</label>
            <input type="text" id="edit-lent" class="text-input" value="${book.lent_to || ''}" placeholder="Jméno osoby...">
          </div>
          <div class="form-group">
            <label>Vrátit do</label>
            <input type="date" id="edit-lent-until" class="text-input" value="${book.lent_until || ''}">
          </div>
        </div>

        <div class="form-group">
          <label>Poznámky</label>
          <textarea id="edit-notes" rows="3">${book.notes || ''}</textarea>
        </div>

        <div style="display:flex; gap:10px; margin-top:10px;">
          <button class="save-btn" id="save-btn" style="flex-grow:1;">Uložit změny</button>
          <button class="save-btn" id="modal-delete-btn" style="background:#ff5252;">Smazat</button>
        </div>
      </div>
    `;

    // Rating stars logic
    const starContainer = body.querySelector('#edit-rating');
    starContainer.querySelectorAll('span').forEach(star => {
      star.onclick = () => {
        const n = parseInt(star.dataset.n);
        starContainer.dataset.value = n;
        starContainer.querySelectorAll('span').forEach(s => {
          s.innerText = parseInt(s.dataset.n) <= n ? '★' : '☆';
        });
      };
    });

    body.querySelector('#save-btn').onclick = () => this.saveBook(book.id);
    body.querySelector('#modal-delete-btn').onclick = () => this.deleteBook(book.id);
    
    this.modal.classList.add('open');
  }

  render() {
    const state = this._hass.states['sensor.bookcase_total_books'];
    if (!state || !state.attributes.books) return;

    let books = state.attributes.books;
    
    // Search filter
    if (this._searchQuery) {
      books = books.filter(b => 
        b.title.toLowerCase().includes(this._searchQuery) || 
        (b.authors && b.authors.some(a => a.toLowerCase().includes(this._searchQuery)))
      );
    }

    // Tab filter
    if (this._filter !== 'all') {
      if (this._filter === 'lent') {
        books = books.filter(b => b.lent_to);
      } else {
        books = books.filter(b => b.status === this._filter);
      }
    }

    this.querySelector('#stats').innerText = `${books.length} knih`;
    this.content.innerHTML = '';
    
    [...books].reverse().forEach(book => {
      const card = document.createElement('div');
      card.className = 'book-card';
      card.onclick = () => this.openDetail(book);
      
      const statusLabels = { 'to_read': 'CHCI PŘEČÍST', 'reading': 'ROZEČTENO', 'read': 'PŘEČTENO' };
      const statusColors = { 'to_read': '#03a9f4', 'reading': '#4caf50', 'read': '#9c27b0' };
      
      card.innerHTML = `
        <div class="cover-wrapper">
          <img src="${book.cover_url || ''}" onerror="this.style.opacity='0.2';">
          <div class="status-badge" style="background:${statusColors[book.status] || '#555'}">${statusLabels[book.status] || ''}</div>
          ${book.lent_to ? `<div class="lent-badge">PŮJČENO: ${book.lent_to}</div>` : ''}
        </div>
        <div class="book-title">${book.title}</div>
        <div style="font-size:0.75rem; color:var(--secondary-text-color); margin-top:4px;">
          ${book.rating > 0 ? `<span style="color:#ffca28;">${'★'.repeat(book.rating)}</span> ` : ''}
          ${book.authors ? book.authors[0] : ''}
        </div>
      `;
      this.content.appendChild(card);
    });
  }
}
customElements.define('bookcase-panel', BookcasePanel);
