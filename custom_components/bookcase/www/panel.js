class BookcasePanel extends HTMLElement {
  constructor() {
    super();
    this._loading = false;
    this._pendingAdds = 0; // Kolik ISBN se právě zpracovává
    this._filter = 'all';
    this._searchQuery = '';
    this._optimisticDeleted = new Set();
    this._eventListenerBound = false;
  }

  set hass(hass) {
    const newState = hass.states['sensor.bookcase_total_books'];
    
    if (this._hass && newState && this._lastState === newState) {
      this._hass = hass;
      return;
    }

    this._hass = hass;
    this._lastState = newState;
    
    if (!this.content) {
      this.initStructure();
    }

    // Posloucháme bookcase_error eventy (duplicitní ISBN atd.)
    if (!this._eventListenerBound && hass.connection) {
      this._eventListenerBound = true;
      hass.connection.subscribeEvents((ev) => {
        const msg = ev.data && ev.data.message;
        if (msg) this.showToast(msg, 'warning');
        // Snížíme pending counter i při erroru
        this._pendingAdds = Math.max(0, this._pendingAdds - 1);
        if (this._pendingAdds === 0) this._loading = false;
        this.updateButtons();
      }, 'bookcase_error');
      hass.connection.subscribeEvents((ev) => {
        const msg = ev.data && ev.data.message;
        if (msg) this.showToast(msg, 'info');
      }, 'bookcase_info');
    }

    if (newState && newState.attributes && newState.attributes.books) {
      // Snížíme pending counter při úspěchu (nová kniha přišla ze serveru)
      if (this._pendingAdds > 0) {
        this._pendingAdds = Math.max(0, this._pendingAdds - 1);
        if (this._pendingAdds === 0) this._loading = false;
      }
      
      // Clear optimistic deletions that are now confirmed by the server
      const serverIds = new Set(newState.attributes.books.map(b => b.id));
      for (const id of this._optimisticDeleted) {
        if (!serverIds.has(id)) {
          this._optimisticDeleted.delete(id);
        }
      }

      this.render();
      this.updateButtons();
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
          border-bottom: 1px solid var(--divider-color);
          padding-bottom: 20px;
        }
        .header h1 {
          margin: 0;
          font-size: 2rem;
          font-weight: 700;
          color: var(--primary-text-color);
        }
        
        .toolbar {
          display: flex;
          flex-direction: column;
          gap: 20px;
          margin-bottom: 40px;
        }

        .filter-bar {
          display: flex;
          gap: 8px;
          overflow-x: auto;
          padding-bottom: 5px;
        }
        
        .filter-btn {
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
          padding: 8px 16px;
          border-radius: 8px;
          cursor: pointer;
          white-space: nowrap;
          font-weight: 500;
          transition: all 0.2s;
        }
        .filter-btn.active {
          background: var(--primary-color);
          color: white;
          border-color: var(--primary-color);
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
          border-radius: 8px;
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
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          padding: 4px;
          gap: 5px;
        }
        .add-box input {
          background: transparent;
          border: none;
          padding: 8px 12px;
          width: 200px;
          color: var(--primary-text-color);
          outline: none;
        }
        button.action-btn {
          background: var(--primary-color);
          color: white;
          border: none;
          padding: 8px 16px;
          border-radius: 6px;
          cursor: pointer;
          font-weight: bold;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: opacity 0.2s;
          white-space: nowrap;
        }
        button.action-btn:disabled {
          opacity: 0.5;
          cursor: wait;
        }

        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 25px;
        }
        .book-card {
          background: var(--card-background-color);
          border-radius: 8px;
          padding: 8px;
          box-shadow: none;
          border: 1px solid var(--divider-color);
          transition: border-color 0.2s, transform 0.2s;
          position: relative;
          cursor: pointer;
        }
        .book-card:hover {
          border-color: var(--primary-color);
          transform: translateY(-4px);
        }
        .cover-wrapper {
          position: relative;
          width: 100%;
          aspect-ratio: 2/3;
          border-radius: 4px;
          overflow: hidden;
          background: var(--secondary-background-color);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .book-card img { width: 100%; height: 100%; object-fit: cover; }
        .cover-fallback {
          position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          text-align: center; padding: 10px; font-size: 10px; color: var(--secondary-text-color);
          background: var(--secondary-background-color);
        }
        .book-title {
          font-weight: 600;
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
          top: 6px; right: 6px;
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.6rem;
          font-weight: bold;
          color: white;
          background: rgba(0,0,0,0.6);
          z-index: 2;
        }
        .lent-badge {
          position: absolute;
          bottom: 0; left: 0; right: 0;
          background: #ff9800;
          color: white;
          padding: 4px;
          font-size: 0.6rem;
          font-weight: bold;
          text-align: center;
          z-index: 2;
        }

        /* Modal */
        .modal {
          display: none;
          position: fixed;
          top: 0; left: 0; width: 100%; height: 100%;
          background: rgba(0,0,0,0.7);
          z-index: 1000;
          align-items: center; justify-content: center;
          padding: 20px;
        }
        .modal.open { display: flex; }
        .modal-content {
          background: var(--card-background-color);
          max-width: 850px;
          width: 100%;
          border-radius: 12px;
          display: flex;
          overflow: hidden;
          position: relative;
          max-height: 90vh;
          border: 1px solid var(--divider-color);
        }
        .modal-close {
          position: absolute; top: 15px; right: 15px;
          width: 32px; height: 32px; border-radius: 50%;
          background: var(--secondary-background-color);
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; z-index: 11;
        }
        .modal-body { display: flex; width: 100%; overflow-y: auto; }
        .modal-left { width: 280px; flex-shrink: 0; background: var(--secondary-background-color); position: relative; }
        .modal-left img { width: 100%; height: 100%; object-fit: cover; }
        .modal-right { padding: 30px; flex-grow: 1; display: flex; flex-direction: column; gap: 20px; }
        
        .form-group { display: flex; flex-direction: column; gap: 6px; }
        label { font-size: 0.75rem; font-weight: 700; color: var(--secondary-text-color); text-transform: uppercase; }
        select, textarea, .text-input {
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          color: var(--primary-text-color);
          padding: 10px;
          border-radius: 6px;
          font-size: 0.9rem;
          outline: none;
        }
        
        .rating-stars { display: flex; gap: 4px; font-size: 1.4rem; color: #ffca28; cursor: pointer; }
        
        .toggle-row { display: flex; gap: 10px; }
        .toggle-btn {
          flex: 1;
          padding: 12px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-weight: bold;
          text-align: center;
          transition: all 0.2s;
        }
        .toggle-btn.active-read { background: #4caf50; color: white; border-color: #4caf50; }
        .toggle-btn.active-wish { background: #03a9f4; color: white; border-color: #03a9f4; }
        
        .user-list { font-size: 0.8rem; color: var(--secondary-text-color); margin-top: 4px; }
        
        .spinner {
          width: 14px; height: 14px;
          border: 2px solid rgba(255,255,255,0.3);
          border-radius: 50%; border-top-color: #fff;
          animation: spin 0.8s linear infinite;
          display: none;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .toast {
          position: fixed;
          bottom: 30px;
          left: 50%;
          transform: translateX(-50%) translateY(100px);
          padding: 12px 24px;
          border-radius: 8px;
          color: white;
          font-weight: 600;
          font-size: 0.9rem;
          z-index: 9999;
          pointer-events: none;
          opacity: 0;
          transition: transform 0.3s ease, opacity 0.3s ease;
          max-width: 90vw;
          text-align: center;
        }
        .toast.visible {
          transform: translateX(-50%) translateY(0);
          opacity: 1;
        }
        .toast.success { background: #4caf50; }
        .toast.warning { background: #ff9800; }
        .toast.error { background: #f44336; }
        .toast.info { background: #2196f3; }
      </style>
      
      <div class="container">
        <div class="header">
          <h1>Moje Knihovna</h1>
          <div id="stats" style="font-size: 0.9rem; opacity: 0.6;"></div>
        </div>
        
        <div class="toolbar">
          <div class="search-add-row">
            <div class="search-box">
              <span style="opacity: 0.4;">🔍</span>
              <input type="text" id="search-input" placeholder="Hledat knihu...">
            </div>
            <div class="add-box">
              <input type="text" id="isbn-input" placeholder="ISBN...">
              <button id="add-btn" class="action-btn">
                <span class="spinner" id="add-spinner"></span>
                <span id="add-text">ISBN</span>
              </button>
              <button id="manual-btn" class="action-btn" style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);">
                Ručně
              </button>
            </div>
          </div>
          
          <div class="filter-bar">
            <button class="filter-btn active" data-filter="all">Vše</button>
            <button class="filter-btn" data-filter="to_read">K přečtení</button>
            <button class="filter-btn" data-filter="reading">Rozečtené</button>
            <button class="filter-btn" data-filter="read">Přečtené</button>
            <button class="filter-btn" data-filter="wishlist">Wishlist</button>
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
    this.modal = this.querySelector('#book-modal');
    this.modalClose = this.querySelector('.modal-close');

    this.querySelector('#add-btn').onclick = () => this.handleAdd();
    this.querySelector('#manual-btn').onclick = () => this.openManualAdd();
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
    if (!isbn) return;

    // Povolíme rychlé skenování více ISBN po sobě
    this._pendingAdds++;
    this._loading = true;
    this.updateButtons();
    this._hass.callService('bookcase', 'add_by_isbn', { isbn });
    this.isbnInput.value = '';
    this.isbnInput.focus();
    this.showToast(`Hledám ISBN: ${isbn}…`, 'success');

    // Safety timeout – po 15s resetujeme loading stav
    setTimeout(() => {
      if (this._pendingAdds > 0) {
        this._pendingAdds = 0;
        this._loading = false;
        this.updateButtons();
      }
    }, 15000);
  }

  showToast(message, type = 'success') {
    // Odstraníme předchozí toast pokud existuje
    const old = this.querySelector('.toast');
    if (old) old.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    this.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => {
      toast.classList.add('visible');
    });

    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  updateButtons() {
    const addBtn = this.querySelector('#add-btn');
    const addSpinner = this.querySelector('#add-spinner');
    const addText = this.querySelector('#add-text');
    if (addBtn) {
      // Při ISBN přidávání NEblokujeme tlačítko – umožníme rychlé skenování
      addBtn.disabled = false;
      addSpinner.style.display = this._pendingAdds > 0 ? 'block' : 'none';
      addText.textContent = this._pendingAdds > 0 ? `(${this._pendingAdds})` : 'ISBN';
    }

    const saveBtn = this.querySelector('#save-btn');
    const delBtn = this.querySelector('#modal-delete-btn');
    if (saveBtn) {
      saveBtn.disabled = this._loading && !this._pendingAdds;
      saveBtn.innerText = this._loading && !this._pendingAdds ? '...' : (this._manualMode ? 'Přidat knihu' : 'Uložit změny');
    }
    if (delBtn) {
      delBtn.disabled = this._loading && !this._pendingAdds;
      delBtn.innerText = this._loading && !this._pendingAdds ? '...' : 'Smazat';
    }
  }

  saveBook(bookId) {
    if (this._loading) return;
    this._loading = true;
    this.updateButtons();

    const title = this.querySelector('#edit-title').value.trim();
    const authorStr = this.querySelector('#edit-author').value.trim();
    const status = this.querySelector('#edit-status').value;
    const rating = parseInt(this.querySelector('#edit-rating').dataset.value);
    const notes = this.querySelector('#edit-notes').value;
    const description = this.querySelector('#edit-description')?.value || '';
    const lentTo = this.querySelector('#edit-lent').value.trim() || null;
    const lentUntil = this.querySelector('#edit-lent-until').value || null;
    const coverUrl = this.querySelector('#edit-cover-url').value.trim() || null;
    
    const readBy = JSON.parse(this.querySelector('#modal-body').dataset.readBy || '[]');
    const wishlistBy = JSON.parse(this.querySelector('#modal-body').dataset.wishlistBy || '[]');

    const serviceData = {
      title: title,
      authors: authorStr.split(',').map(s => s.trim()).filter(s => s),
      cover_url: coverUrl,
      status: status,
      rating: rating,
      notes: notes,
      description: description,
      lent_to: lentTo,
      lent_until: lentUntil,
      read_by: readBy,
      wishlist_by: wishlistBy,
      is_read: readBy.length > 0
    };

    if (this._manualMode) {
      this._hass.callService('bookcase', 'add_manual', serviceData);
    } else {
      this._hass.callService('bookcase', 'update_book', {
        ...serviceData,
        book_id: bookId
      });
    }
    
    setTimeout(() => { this.modal.classList.remove('open'); }, 400);
  }

  deleteBook(bookId) {
    if (this._loading) return;
    if (confirm('Opravdu chcete tuto knihu smazat?')) {
      this._loading = true;
      this.updateButtons();
      
      // OPTIMISTIC DELETE: 
      // 1. Hide modal
      this.modal.classList.remove('open');
      // 2. Add to optimistic deleted set
      this._optimisticDeleted.add(bookId);
      // 3. Re-render immediately
      this.render();
      
      // 4. Call server in background
      this._hass.callService('bookcase', 'delete_book', { book_id: bookId });
    }
  }

  openManualAdd() {
    this._manualMode = true;
    this.openDetail({
      title: '',
      authors: [],
      status: 'to_read',
      rating: 0,
      notes: '',
      read_by: [],
      wishlist_by: []
    });
  }

  toggleUser(bookId, type) {
    const userName = this._hass.user.name || 'Uživatel';
    const body = this.querySelector('#modal-body');
    const key = type === 'read' ? 'readBy' : 'wishlistBy';
    let list = JSON.parse(body.dataset[key] || '[]');
    
    if (list.includes(userName)) {
      list = list.filter(u => u !== userName);
    } else {
      list.push(userName);
      if (type === 'read') {
        let wishList = JSON.parse(body.dataset.wishlistBy || '[]');
        wishList = wishList.filter(u => u !== userName);
        body.dataset.wishlistBy = JSON.stringify(wishList);
      }
    }
    
    body.dataset[key] = JSON.stringify(list);
    this.updateToggleButtons();
  }

  updateToggleButtons() {
    const userName = this._hass.user.name || 'Uživatel';
    const body = this.querySelector('#modal-body');
    const readList = JSON.parse(body.dataset.readBy || '[]');
    const wishList = JSON.parse(body.dataset.wishlistBy || '[]');
    
    const readBtn = this.querySelector('#toggle-read');
    const wishBtn = this.querySelector('#toggle-wish');
    
    if (readBtn) readBtn.className = 'toggle-btn' + (readList.includes(userName) ? ' active-read' : '');
    if (wishBtn) wishBtn.className = 'toggle-btn' + (wishList.includes(userName) ? ' active-wish' : '');
    
    this.querySelector('#read-users').innerText = readList.length > 0 ? 'Přečetli: ' + readList.join(', ') : '';
    this.querySelector('#wish-users').innerText = wishList.length > 0 ? 'Chtějí přečíst: ' + wishList.join(', ') : '';
  }

  openDetail(book) {
    if (!this._manualMode) this._manualMode = false;
    const body = this.querySelector('#modal-body');
    body.dataset.readBy = JSON.stringify(Array.isArray(book.read_by) ? book.read_by : (book.read_by ? [book.read_by] : []));
    body.dataset.wishlistBy = JSON.stringify(Array.isArray(book.wishlist_by) ? book.wishlist_by : []);
    
    const rating = book.rating || 0;

    body.innerHTML = `
      <div class="modal-left">
        <img src="${book.cover_url || ''}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
        <div class="cover-fallback" style="display:none; font-size: 14px;">
          <span style="font-size: 40px; margin-bottom: 10px;">📖</span>
          ${book.title || 'Nová kniha'}
        </div>
      </div>
      <div class="modal-right">
        <div class="form-group">
          <label>NÁZEV KNIHY</label>
          <input type="text" id="edit-title" class="text-input" value="${book.title || ''}" placeholder="Titul...">
        </div>
        <div class="form-group">
          <label>AUTOR (oddělit čárkou)</label>
          <input type="text" id="edit-author" class="text-input" value="${(book.authors || []).join(', ')}" placeholder="Jméno...">
        </div>
        <div class="form-group">
          <label>URL OBÁLKY</label>
          <input type="text" id="edit-cover-url" class="text-input" value="${book.cover_url || ''}" placeholder="https://...">
        </div>
        
        <div class="toggle-row">
          <div style="flex:1;">
            <div class="toggle-btn" id="toggle-read">Přečetl jsem</div>
            <div class="user-list" id="read-users"></div>
          </div>
          <div style="flex:1;">
            <div class="toggle-btn" id="toggle-wish">Chci přečíst</div>
            <div class="user-list" id="wish-users"></div>
          </div>
        </div>

        <div class="form-group">
          <label>HODNOCENÍ</label>
          <div class="rating-stars" id="edit-rating" data-value="${rating}">
            ${[1,2,3,4,5].map(n => `<span data-n="${n}">${n <= rating ? '★' : '☆'}</span>`).join('')}
          </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 20px;">
          <div class="form-group">
            <label>STAV KNIHY</label>
            <select id="edit-status">
              <option value="to_read" ${book.status === 'to_read' ? 'selected' : ''}>Máme v knihovně</option>
              <option value="reading" ${book.status === 'reading' ? 'selected' : ''}>Právě čtu</option>
              <option value="read" ${book.status === 'read' ? 'selected' : ''}>Přečteno (všichni)</option>
              <option value="wishlist" ${book.status === 'wishlist' ? 'selected' : ''}>Na Wishlistu (nemáme ji)</option>
            </select>
          </div>
          <div class="form-group">
            <label>PŮJČENO KOMU</label>
            <input type="text" id="edit-lent" class="text-input" value="${book.lent_to || ''}" placeholder="Jméno...">
          </div>
        </div>

        <div class="form-group">
          <label>VRÁTIT DO</label>
          <input type="date" id="edit-lent-until" class="text-input" value="${book.lent_until || ''}">
        </div>

        <div class="form-group">
          <label>POZNÁMKY</label>
          <textarea id="edit-notes" rows="3" placeholder="Vaše poznámky...">${book.notes || ''}</textarea>
        </div>

        <div class="form-group">
          <label>POPIS (Z INTERNETU)</label>
          <textarea id="edit-description" rows="5" placeholder="Popis knihy...">${book.description || ''}</textarea>
        </div>

        <div style="display:flex; gap:12px; margin-top:10px;">
          <button class="action-btn" id="save-btn" style="flex-grow:1; height:45px;">${this._manualMode ? 'Přidat knihu' : 'Uložit změny'}</button>
          ${!this._manualMode ? `<button class="action-btn" id="modal-delete-btn" style="background:#f44336; height:45px;">Smazat</button>` : ''}
        </div>
      </div>
    `;

    body.querySelector('#toggle-read').onclick = () => this.toggleUser(book.id, 'read');
    body.querySelector('#toggle-wish').onclick = () => this.toggleUser(book.id, 'wish');
    
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
    if (!this._manualMode) body.querySelector('#modal-delete-btn').onclick = () => this.deleteBook(book.id);
    
    this.updateToggleButtons();
    this.modal.classList.add('open');
  }

  render() {
    const state = this._hass.states['sensor.bookcase_total_books'];
    if (!state || !state.attributes.books) return;

    let books = state.attributes.books;
    const userName = this._hass.user.name || 'Uživatel';
    
    // Filter out optimistic deletions
    books = books.filter(b => !this._optimisticDeleted.has(b.id));

    if (this._searchQuery) {
      books = books.filter(b => 
        (b.title || '').toLowerCase().includes(this._searchQuery) || 
        (b.authors && b.authors.some(a => a.toLowerCase().includes(this._searchQuery)))
      );
    }

    if (this._filter !== 'all') {
      if (this._filter === 'lent') {
        books = books.filter(b => b.lent_to);
      } else if (this._filter === 'wishlist') {
        books = books.filter(b => b.status === 'wishlist' || (Array.isArray(b.wishlist_by) && b.wishlist_by.includes(userName)));
      } else if (this._filter === 'read') {
        books = books.filter(b => Array.isArray(b.read_by) && b.read_by.includes(userName));
      } else {
        books = books.filter(b => b.status === this._filter);
      }
    }

    this.querySelector('#stats').innerText = `${books.length} knih`;
    this.content.innerHTML = '';
    
    [...books].reverse().forEach(book => {
      const card = document.createElement('div');
      card.className = 'book-card';
      card.onclick = () => { this._manualMode = false; this.openDetail(book); };
      
      const statusColors = { 'to_read': '#2196f3', 'reading': '#4caf50', 'read': '#9c27b0', 'wishlist': '#ff9800' };
      const statusLabels = { 'to_read': 'MÁME', 'reading': 'ČTU', 'read': 'HOTOVO', 'wishlist': 'CHCI' };
      
      card.innerHTML = `
        <div class="cover-wrapper">
          <img src="${book.cover_url || ''}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
          <div class="cover-fallback" style="display:none;">
            <span style="font-size: 24px; margin-bottom: 5px;">📖</span>
            <div style="font-weight:bold; overflow:hidden; text-overflow:ellipsis; width:100%; max-height: 40px;">${book.title}</div>
          </div>
          <div class="status-badge" style="background:${statusColors[book.status] || '#666'}">${statusLabels[book.status] || ''}</div>
          ${book.lent_to ? `<div class="lent-badge">PŮJČENO: ${book.lent_to}</div>` : ''}
        </div>
        <div class="book-title">${book.title}</div>
        <div style="font-size:0.75rem; color:var(--secondary-text-color); margin-top:4px; display:flex; justify-content:space-between;">
          <span>${book.authors ? book.authors[0] : ''}</span>
          ${book.rating > 0 ? `<span style="color:#ffca28;">${'★'.repeat(book.rating)}</span>` : ''}
        </div>
      `;
      this.content.appendChild(card);
    });
  }
}
customElements.define('bookcase-panel', BookcasePanel);
