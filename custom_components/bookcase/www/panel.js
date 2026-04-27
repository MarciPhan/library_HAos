class BookcasePanel extends HTMLElement {
  constructor() {
    super();
    this._loading = false;
    this._pendingAdds = 0; // Kolik ISBN se právě zpracovává
    this._filter = 'all';
    this._searchQuery = '';
    this._optimisticDeleted = new Set();
    this._eventListenerBound = false;
    this._sortKey = 'added_at';
  }

  _formatTitle(book) {
    if (!book) return '';
    let title = (book.title || '').toString();
    let subtitle = (book.subtitle || '').toString();
    
    // Pokud je v hlavním názvu dvojtečka, rozdělíme ji (často se to stává po importu)
    if (title.includes(':')) {
      const parts = title.split(':');
      title = parts[0].trim();
      const extraSub = parts.slice(1).join(':').trim();
      // Pokud nemáme podnázev, použijeme ten z titulu. Jinak ho tam necháme.
      if (!subtitle) subtitle = extraSub;
    }
    
    if (subtitle) {
      return `${title}<br><span style="font-size:0.8em; font-weight:400; opacity:0.7; display:block; margin-top:2px; line-height:1.2;">${subtitle}</span>`;
    }
    
    return title;
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
      try {
        this.initStructure();
      } catch (err) {
        console.error("Bookcase structure init failed:", err);
      }
    }

    try {
      this.render();
    } catch (err) {
      console.error("Bookcase render failed:", err);
    }
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
        * { box-sizing: border-box; }
        :host {
          background-color: var(--primary-background-color);
          display: block;
          height: 100%;
          color: var(--primary-text-color);
          font-family: 'Outfit', 'Roboto', -apple-system, BlinkMacSystemFont, sans-serif;
          overflow-x: hidden;
        }
        .container {
          max-width: 1400px;
          margin: 0 auto;
          padding: 32px 24px;
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: flex-end;
          margin-bottom: 30px;
          border-bottom: 1px solid var(--divider-color);
          padding-bottom: 20px;
        }
        .header h1 {
          margin: 0;
          font-size: 2.4rem;
          font-weight: 800;
          color: var(--primary-color);
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
          padding-bottom: 8px;
          scrollbar-width: none;
        }
        .filter-bar::-webkit-scrollbar { display: none; }
        
        .filter-btn {
          background: var(--card-background-color);
          color: var(--primary-text-color);
          border: 1px solid var(--divider-color);
          padding: 10px 20px;
          border-radius: 12px;
          cursor: pointer;
          white-space: nowrap;
          font-weight: 600;
          font-size: 0.9rem;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .filter-btn:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 8px rgba(0,0,0,0.1);
          border-color: var(--primary-color);
        }
        .filter-btn.active {
          background: var(--primary-color);
          color: white;
          border-color: var(--primary-color);
          box-shadow: 0 4px 12px rgba(33, 150, 243, 0.4);
        }

        .search-add-row {
          display: flex;
          gap: 16px;
          flex-wrap: wrap;
        }
        .search-box {
          flex: 2;
          min-width: 280px;
          display: flex;
          align-items: center;
          background: var(--card-background-color);
          border-radius: 14px;
          padding: 0 18px;
          border: 1px solid var(--divider-color);
          transition: border-color 0.2s, box-shadow 0.2s;
        }
        .search-box:focus-within {
          border-color: var(--primary-color);
          box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
        }
        .search-box input {
          background: transparent;
          border: none;
          padding: 14px 10px;
          width: 100%;
          color: var(--primary-text-color);
          outline: none;
          font-size: 1rem;
        }

        .add-box {
          flex: 3;
          min-width: 300px;
          display: flex;
          background: var(--card-background-color);
          border-radius: 14px;
          border: 1px solid var(--divider-color);
          padding: 6px;
          gap: 6px;
        }
        .add-box input {
          background: transparent;
          border: none;
          padding: 8px 14px;
          flex-grow: 1;
          color: var(--primary-text-color);
          outline: none;
          font-size: 1rem;
        }
        .action-btn {
          background: var(--primary-color);
          color: white;
          border: none;
          padding: 10px 18px;
          border-radius: 10px;
          cursor: pointer;
          font-weight: 700;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: all 0.2s;
          white-space: nowrap;
        }
        .action-btn:hover {
          opacity: 0.9;
          transform: scale(1.02);
        }
        .action-btn:active {
          transform: scale(0.98);
        }
        button.action-btn:disabled {
          opacity: 0.5;
          cursor: wait;
        }

        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
          gap: 24px;
        }
        .book-card {
          background: var(--card-background-color);
          border-radius: 16px;
          padding: 12px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.08);
          border: 1px solid var(--divider-color);
          transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
          position: relative;
          cursor: pointer;
          display: flex;
          flex-direction: column;
        }
        .book-card:hover {
          border-color: var(--primary-color);
          transform: translateY(-8px) scale(1.02);
          box-shadow: 0 12px 30px rgba(0,0,0,0.15);
        }
        .cover-wrapper {
          position: relative;
          width: 100%;
          aspect-ratio: 2/3;
          border-radius: 10px;
          overflow: hidden;
          background: var(--secondary-background-color);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 4px 10px rgba(0,0,0,0.2);
        }
        .book-card img { width: 100%; height: 100%; object-fit: cover; }
        .cover-fallback {
          position: absolute; top: 0; left: 0; width: 100%; height: 100%;
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          text-align: center; padding: 15px; font-size: 11px; color: var(--secondary-text-color);
          background: var(--secondary-background-color);
        }
        .book-title {
          font-weight: 700;
          margin-top: 14px;
          font-size: 0.95rem;
          line-height: 1.3;
          color: var(--primary-text-color);
        }
        .status-badge {
          position: absolute;
          top: 8px; right: 8px;
          padding: 4px 8px;
          border-radius: 6px;
          font-size: 0.65rem;
          font-weight: 800;
          color: white;
          background: rgba(0,0,0,0.7);
          backdrop-filter: blur(4px);
          z-index: 2;
          letter-spacing: 0.5px;
        }
        .lent-badge {
          position: absolute;
          bottom: 0; left: 0; right: 0;
          background: #ff9800;
          color: white;
          padding: 6px;
          font-size: 0.65rem;
          font-weight: 800;
          text-align: center;
          z-index: 2;
        }

        /* Modal */
        .modal {
          display: none;
          position: fixed;
          top: 0; left: 0; width: 100%; height: 100%;
          background: rgba(0,0,0,0.6);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          z-index: 1000;
          align-items: center; justify-content: center;
          padding: 20px;
          transition: opacity 0.3s;
        }
        .modal.open { display: flex; animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        
        .modal-content {
          background: var(--card-background-color);
          max-width: 1000px;
          width: 100%;
          border-radius: 24px;
          display: flex;
          overflow: hidden;
          position: relative;
          max-height: 94vh;
          border: 1px solid rgba(255,255,255,0.1);
          box-shadow: 0 30px 90px rgba(0,0,0,0.6);
          animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes slideUp { from { transform: translateY(30px) scale(0.95); opacity: 0; } to { transform: translateY(0) scale(1); opacity: 1; } }

        .modal-close {
          position: absolute; top: 16px; right: 16px;
          width: 40px; height: 40px; border-radius: 50%;
          background: rgba(0,0,0,0.3);
          backdrop-filter: blur(10px);
          color: white; font-size: 22px;
          display: flex; align-items: center; justify-content: center;
          cursor: pointer; z-index: 11;
          transition: all 0.2s;
        }
        .modal-close:hover { background: rgba(0,0,0,0.6); transform: rotate(90deg); }
        
        .modal-body { display: flex; width: 100%; }
        
        .modal-left {
          width: 340px; flex-shrink: 0;
          background: var(--secondary-background-color);
          position: relative;
          display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
          padding: 30px;
          border-right: 1px solid var(--divider-color);
        }
        .modal-left img { 
          width: 100%; 
          border-radius: 12px; 
          box-shadow: 0 15px 35px rgba(0,0,0,0.4);
          transition: transform 0.3s;
        }
        .modal-left img:hover { transform: scale(1.03); }
        
        .modal-right {
          padding: 35px;
          flex-grow: 1;
          display: flex; flex-direction: column; gap: 0;
          overflow-y: auto;
          max-height: 94vh;
          background: var(--card-background-color);
          overflow-x: hidden;
        }

        .section-title {
          font-size: 0.75rem; font-weight: 800; text-transform: uppercase;
          letter-spacing: 2px; color: var(--primary-color);
          margin: 28px 0 16px 0; padding-bottom: 8px;
          border-bottom: 2px solid var(--divider-color);
          display: flex; align-items: center; gap: 8px;
        }
        .section-title:first-child { margin-top: 0; }
        
        .form-group { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
        .form-row { display: grid; gap: 16px; margin-bottom: 16px; }
        .form-row.cols-2 { grid-template-columns: 1fr 1fr; }
        .form-row.cols-3 { grid-template-columns: 1fr 1fr 1fr; }
        
        label {
          font-size: 0.7rem; font-weight: 700;
          color: var(--secondary-text-color);
          text-transform: uppercase; letter-spacing: 0.8px;
        }
        select, textarea, .text-input {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          color: var(--primary-text-color);
          padding: 12px 14px;
          border-radius: 12px;
          font-size: 0.95rem;
          outline: none;
          transition: all 0.2s;
          box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
          width: 100%;
          max-width: 100%;
          overflow-wrap: break-word;
        }
        select:focus, textarea:focus, .text-input:focus {
          border-color: var(--primary-color);
          box-shadow: 0 0 0 3px rgba(33, 150, 243, 0.1);
        }
        .text-input:disabled {
          opacity: 0.6; cursor: not-allowed; background: var(--secondary-background-color);
        }
        textarea { resize: vertical; font-family: inherit; line-height: 1.5; }
        
        .meta-chips {
          display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px;
        }
        .meta-chip {
          background: var(--secondary-background-color);
          border: 1px solid var(--divider-color);
          padding: 6px 14px; border-radius: 20px;
          font-size: 0.8rem; color: var(--secondary-text-color);
          white-space: nowrap;
          transition: all 0.2s;
        }
        .meta-chip:hover { border-color: var(--primary-color); color: var(--primary-text-color); }
        .meta-chip b { color: var(--primary-text-color); margin-left: 5px; }
        
        .rating-stars { display: flex; gap: 6px; font-size: 1.8rem; color: #ffca28; cursor: pointer; }
        .rating-stars span { transition: transform 0.2s; }
        .rating-stars span:hover { transform: scale(1.2); }
        
        .toggle-row { display: flex; gap: 12px; margin-bottom: 16px; }
        .toggle-btn {
          flex: 1;
          padding: 14px;
          border-radius: 14px;
          border: 1px solid var(--divider-color);
          background: var(--card-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
          font-weight: 700; font-size: 0.9rem;
          text-align: center;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          box-shadow: 0 2px 5px rgba(0,0,0,0.05);
          display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .toggle-btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        .toggle-btn.active-read { background: #10b981; color: white; border-color: #10b981; box-shadow: 0 5px 15px rgba(16, 185, 129, 0.4); }
        .toggle-btn.active-wish { background: #0ea5e9; color: white; border-color: #0ea5e9; box-shadow: 0 5px 15px rgba(14, 165, 233, 0.4); }
        
        .user-list { font-size: 0.8rem; color: var(--secondary-text-color); margin-top: 6px; text-align: center; font-style: italic; }
        
        .spinner {
          width: 18px; height: 18px;
          border: 3px solid rgba(255,255,255,0.3);
          border-radius: 50%; border-top-color: #fff;
          animation: spin 0.8s linear infinite;
          display: none;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .toast {
          position: fixed; bottom: 40px; left: 50%;
          transform: translateX(-50%) translateY(100px);
          padding: 14px 28px; border-radius: 16px;
          color: white; font-weight: 700; font-size: 1rem;
          z-index: 9999; pointer-events: none; opacity: 0;
          transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
          max-width: 90vw; text-align: center;
          box-shadow: 0 10px 40px rgba(0,0,0,0.3);
          backdrop-filter: blur(10px);
        }
        .toast.visible { transform: translateX(-50%) translateY(0); opacity: 1; }
        .toast.success { background: rgba(16, 185, 129, 0.9); }
        .toast.warning { background: rgba(245, 158, 11, 0.9); }
        .toast.error { background: rgba(239, 68, 68, 0.9); }
        .toast.info { background: rgba(59, 130, 246, 0.9); }

        @media (max-width: 768px) {
          .container { padding: 20px 16px; }
          .header { flex-direction: column; align-items: flex-start; gap: 10px; }
          .header h1 { font-size: 1.8rem; }
          .grid {
            grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
            gap: 16px;
          }
          .book-card { padding: 8px; border-radius: 12px; }
          .book-title { font-size: 0.85rem; margin-top: 8px; }
          .search-add-row { gap: 12px; }
          .add-box, .search-box { width: 100%; min-width: 0; }
          
          .modal { padding: 0; }
          .modal-content { 
            height: 100%; max-height: 100%; border-radius: 0; border: none;
            flex-direction: column;
          }
          .modal-body { flex-direction: column; height: 100%; overflow-y: auto; }
          .modal-left { 
            width: 100%; height: auto; padding: 20px; 
            border-right: none; border-bottom: 1px solid var(--divider-color);
            background: linear-gradient(to bottom, var(--secondary-background-color), var(--card-background-color));
          }
          .modal-left img { max-width: 180px; margin: 0 auto; display: block; }
          .modal-right { padding: 20px; overflow-y: visible; max-height: none; }
          .form-row.cols-3, .form-row.cols-2 { grid-template-columns: 1fr; gap: 8px; }
          .form-group { margin-bottom: 12px; }
          .toggle-row { flex-direction: column; gap: 8px; }
          .section-title { margin-top: 20px; }
          .modal-close { top: 12px; right: 12px; width: 36px; height: 36px; background: rgba(0,0,0,0.5); }
        }

        #scanner-modal {
          display:none; position:fixed; top:0; left:0; width:100%; height:100%;
          background:rgba(0,0,0,0.95); z-index:2000;
          align-items:center; justify-content:center; flex-direction:column;
          backdrop-filter: blur(15px);
        }
        #scanner-modal.open { display:flex; }
        #scanner-reader { width:min(450px, 95vw); min-height: 300px; background: #000; border-radius: 20px; overflow: hidden; box-shadow: 0 0 50px rgba(33, 150, 243, 0.3); }
        #scanner-close {
          position:absolute; top:30px; right:30px;
          width:50px; height:50px; border-radius:50%; background:rgba(255,255,255,0.1);
          color:white; font-size:28px; border:none; cursor:pointer;
          display:flex; align-items:center; justify-content:center;
          transition: all 0.2s;
        }
        #scanner-close:hover { background: rgba(255,255,255,0.2); transform: rotate(90deg); }
        
        .scan-btn {
          background: var(--primary-color); 
          color:white; border:none;
          width:46px; height:46px; border-radius:12px; cursor:pointer;
          font-size:1.4rem; display:flex; align-items:center; justify-content:center;
          transition: all 0.2s;
          box-shadow: 0 4px 10px rgba(var(--rgb-primary-color, 33, 150, 243), 0.3);
        }
        .scan-btn:hover { transform: scale(1.05); box-shadow: 0 6px 15px rgba(168, 85, 247, 0.4); }
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
              <button id="scan-btn" class="scan-btn" title="Skenovat čárový kód">📷</button>
              <button id="add-btn" class="action-btn">
                <span class="spinner" id="add-spinner"></span>
                <span id="add-text">ISBN</span>
              </button>
              <button id="manual-btn" class="action-btn" style="background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color);">
                Ručně
              </button>
              <a href="/bookcase_static/export.csv" target="_blank" class="action-btn" style="background:#4caf50; text-decoration:none;" title="Exportovat knihovnu do CSV">
                📥 Export
              </a>
            </div>
          </div>
          
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;">
            <div class="filter-bar" style="flex-grow: 1;">
              <button class="filter-btn active" data-filter="all">Vše</button>
              <button class="filter-btn" data-filter="to_read">K přečtení</button>
              <button class="filter-btn" data-filter="reading">Rozečtené</button>
              <button class="filter-btn" data-filter="read">Přečtené</button>
              <button class="filter-btn" data-filter="wishlist">Wishlist</button>
              <button class="filter-btn" data-filter="lent">Půjčené</button>
            </div>
            
            <div class="sort-box" style="display: flex; align-items: center; gap: 8px;">
              <label style="font-size: 0.7rem; white-space: nowrap;">ŘADIT:</label>
              <select id="sort-select" style="padding: 6px; border-radius: 6px; background: var(--card-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); font-size: 0.8rem;">
                <option value="added_at">Od nejnovějších</option>
                <option value="authors">Autor</option>
                <option value="title">Název</option>
                <option value="publisher">Nakladatelství</option>
                <option value="page_count">Počet stran</option>
                <option value="rating">Hodnocení</option>
              </select>
            </div>
          </div>
        </div>

        <div class="grid" id="book-grid"></div>
      </div>

      <div id="scanner-modal">
        <button id="scanner-close">&times;</button>
        <div id="scanner-reader"></div>
        <p style="color:white; margin-top:16px; font-size:0.9rem;">Namiřte kameru na čárový kód knihy (ISBN)</p>
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
    this.querySelector('#scan-btn').onclick = () => this.startScanner();
    this.querySelector('#scanner-close').onclick = () => this.stopScanner();
    this.isbnInput.onkeypress = (e) => { if (e.key === 'Enter') this.handleAdd(); };
    this.searchInput.oninput = (e) => {
      this._searchQuery = (e.target.value || '').trim().toLowerCase();
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

    this.querySelector('#sort-select').onchange = (e) => {
      this._sortKey = e.target.value;
      this.render();
    };

    this.modalClose.onclick = () => this.modal.classList.remove('open');
    this.modal.onclick = (e) => { if (e.target === this.modal) this.modal.classList.remove('open'); };
  }

  async startScanner() {
    const scannerModal = this.querySelector('#scanner-modal');
    scannerModal.classList.add('open');

    // Dynamicky načteme html5-qrcode pokud ještě není
    if (!window.Html5Qrcode) {
      try {
        await new Promise((resolve, reject) => {
          const s = document.createElement('script');
          s.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
          s.onload = resolve;
          s.onerror = reject;
          document.head.appendChild(s);
        });
      } catch {
        this.showToast('Nepodařilo se načíst skener', 'error');
        scannerModal.classList.remove('open');
        return;
      }
    }

    const onScanSuccess = (decodedText) => {
      const isbn = decodedText.replace(/[^0-9X]/gi, '');
      if (isbn.length >= 10) {
        this.stopScanner();
        this.isbnInput.value = isbn;
        this.handleAdd();
      }
    };

    // 1. POKUS: Živý přenos kamery (funguje pouze na HTTPS nebo localhost)
    if (window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        this._scanner = new Html5Qrcode('scanner-reader');
        // Přidána podpora pro EAN-13 (8), EAN-8 (7), Code 128 (5) a další pro ISBN
        const config = { 
          fps: 15, 
          qrbox: { width: 280, height: 150 }, 
          formatsToSupport: [0, 5, 7, 8, 14, 15] 
        };
        
        try {
          await this._scanner.start({ facingMode: 'environment' }, config, onScanSuccess);
        } catch (errFallback) {
          await this._scanner.start({ facingMode: 'user' }, config, onScanSuccess).catch(() => {
            return this._scanner.start({ cameraId: true }, config, onScanSuccess);
          });
        }
        return; // Úspěch, konec metody
      } catch (err) {
        console.warn('Live stream selhal, zkusíme fallback na focení', err);
      }
    }

    // 2. FALLBACK (BEZ HTTPS): Otevře nativní systémový foťák
    this.stopScanner(); // Zavřeme modal, nativní foťák ho nahradí
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment'; // Vynutí zadní kameru na mobilu
    
    input.onchange = async (e) => {
      if (e.target.files && e.target.files.length > 0) {
        this.showToast('Zpracovávám fotku...', 'info');
        scannerModal.classList.add('open');
        
        // Malá pauza pro zobrazení toastu
        await new Promise(r => setTimeout(r, 500));
        
        const html5QrCode = new Html5Qrcode('scanner-reader');
        try {
          const decodedText = await html5QrCode.scanFile(e.target.files[0], false);
          onScanSuccess(decodedText);
        } catch (err) {
          console.error('Scan error:', err);
          this.showToast('Čárový kód nebyl na fotce nalezen. Zkuste to znovu z větší dálky a zaostřit.', 'warning');
        }
        html5QrCode.clear();
        scannerModal.classList.remove('open');
      }
    };
    
    input.click();
  }

  stopScanner() {
    if (this._scanner) {
      this._scanner.stop().catch(() => {});
      this._scanner.clear();
      this._scanner = null;
    }
    this.querySelector('#scanner-modal').classList.remove('open');
  }

  handleAdd() {
    const isbn = this.isbnInput.value.trim();
    if (!isbn) return;

    this._pendingAdds++;
    this._loading = true;
    this.updateButtons();
    this._hass.callService('bookcase', 'add_by_isbn', { isbn });
    this.isbnInput.value = '';
    this.isbnInput.focus();
    this.showToast(`Hledám ISBN: ${isbn}…`, 'success');

    setTimeout(() => {
      if (this._pendingAdds > 0) {
        this._pendingAdds = 0;
        this._loading = false;
        this.updateButtons();
      }
    }, 15000);
  }

  showToast(message, type = 'success') {
    const old = this.querySelector('.toast');
    if (old) old.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    this.appendChild(toast);

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

  saveBook(bookId, specificUpdates = null) {
    this._loading = true;
    this.updateButtons();

    const userName = this._hass.user.name || this._hass.user.id || 'Uživatel';
    let serviceData = { book_id: bookId };

    if (specificUpdates) {
      Object.assign(serviceData, specificUpdates);
    } else {
      const v = id => (this.querySelector(id)?.value ?? '').trim();
      const body = this.querySelector('#modal-body');
      const readBy = JSON.parse(body.dataset.readBy || '[]');
      const wishlistBy = JSON.parse(body.dataset.wishlistBy || '[]');
      const genreStr = v('#edit-genre');

      Object.assign(serviceData, {
        title: v('#edit-title'),
        subtitle: v('#edit-subtitle'),
        authors: v('#edit-author').split(',').map(s => s.trim()).filter(s => s),
        cover_url: v('#edit-cover-url') || null,
        publisher: v('#edit-publisher'),
        year: v('#edit-year'),
        language: v('#edit-language'),
        page_count: parseInt(v('#edit-pages')) || 0,
        count: parseInt(v('#edit-count')) || 1,
        genre: genreStr ? genreStr.split(',').map(s => s.trim()).filter(s => s) : [],
        url: v('#edit-url'),
        ratings_by: { [userName]: parseInt(this.querySelector('#edit-rating')?.dataset?.value) || 0 },
        notes_by: { [userName]: v('#edit-notes') },
        statuses_by: { [userName]: v('#edit-status') },
        condition: v('#edit-condition'),
        description: v('#edit-description'),
        date_read: v('#edit-date-read'),
        read_by: readBy,
        wishlist_by: wishlistBy,
      });
      
      const lentInput = this.querySelector('#edit-lent');
      if (lentInput) {
          serviceData.lent_to = lentInput.value || null;
          serviceData.lent_until = this.querySelector('#edit-lent-until')?.value || null;
      }
    }

    if (this._manualMode) {
      this._hass.callService('bookcase', 'add_manual', serviceData);
    } else {
      this._hass.callService('bookcase', 'update_book', serviceData);
    }

    if (!specificUpdates || this._manualMode) {
      setTimeout(() => { this.modal.classList.remove('open'); }, 400);
    }
  }

  deleteBook(bookId) {
    if (confirm('Opravdu chcete tuto knihu smazat?')) {
      this.modal.classList.remove('open');
      this._optimisticDeleted.add(bookId);
      this.render();
      this._hass.callService('bookcase', 'delete_book', { book_id: bookId });
    }
  }

  openManualAdd() {
    this._manualMode = true;
    this.openDetail({
      id: 'manual-' + Date.now(),
      title: '', subtitle: '', authors: [], status: 'to_read',
      rating: 0, notes: '', description: '', publisher: '', year: '',
      language: 'Čeština', page_count: 0, count: 1, genre: [],
      url: '', cover_url: '', isbn: '', date_read: '',
      read_by: [], wishlist_by: [], statuses_by: {}, condition: ''
    });
  }

  toggleUser(bookId, type) {
    const userName = this._hass.user.name || this._hass.user.id || 'Uživatel';
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
    
    const statusSelect = this.querySelector('#edit-status');
    if (statusSelect) {
      if (type === 'read') {
        statusSelect.value = list.includes(userName) ? 'read' : (statusSelect.value === 'read' ? 'to_read' : statusSelect.value);
      } else if (type === 'wishlist') {
        statusSelect.value = list.includes(userName) ? 'wishlist' : (statusSelect.value === 'wishlist' ? 'to_read' : statusSelect.value);
      }
    }

    this.updateToggleButtons();
    this.saveBook(bookId, { 
      read_by: list, 
      wishlist_by: JSON.parse(body.dataset.wishlistBy || '[]'),
      statuses_by: { [userName]: statusSelect ? statusSelect.value : 'to_read' }
    });
  }

  updateToggleButtons() {
    const userName = this._hass.user.name || this._hass.user.id || 'Uživatel';
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
    const userName = this._hass.user.name || this._hass.user.id || 'Uživatel';
    const statusLabels = { 'to_read': 'MÁME', 'reading': 'ČTU', 'read': 'PŘEČTENO', 'wishlist': 'CHCI' };
    
    body.dataset.readBy = JSON.stringify(Array.isArray(book.read_by) ? book.read_by : (book.read_by ? [book.read_by] : []));
    body.dataset.wishlistBy = JSON.stringify(Array.isArray(book.wishlist_by) ? book.wishlist_by : []);
    
    const rating = (book.ratings_by && book.ratings_by[userName]) || 0;
    const notes = (book.notes_by && book.notes_by[userName]) || "";
    const status = (book.statuses_by && book.statuses_by[userName]) || book.status || 'to_read';
    const condition = book.condition || "";
    const genres = Array.isArray(book.genre) ? book.genre.join(', ') : (book.genre || '');
    const isLent = !!(book.lent_to);

    let otherUsersHtml = "";
    if (book.ratings_by || book.notes_by || book.statuses_by) {
        const users = new Set([
            ...Object.keys(book.ratings_by || {}), 
            ...Object.keys(book.notes_by || {}),
            ...Object.keys(book.statuses_by || {})
        ]);
        users.delete(userName);
        if (users.size > 0) {
            otherUsersHtml = `<div class="user-list" style="margin-top:10px; border-top:1px solid var(--divider-color); padding-top:10px;">`;
            users.forEach(u => {
                const uRating = book.ratings_by?.[u] ? '★'.repeat(book.ratings_by[u]) : '';
                const uNote = book.notes_by?.[u] || '';
                const uStatus = book.statuses_by?.[u] ? ` (${statusLabels[book.statuses_by[u]] || ''})` : '';
                otherUsersHtml += `<div style="margin-bottom:5px;"><b>${u}:</b> <span style="color:#ffca28;">${uRating}</span> ${uNote}${uStatus}</div>`;
            });
            otherUsersHtml += `</div>`;
        }
    }

    body.innerHTML = `
      <div class="modal-left">
        <img src="${book.cover_url || `/bookcase_covers/${book.id}.jpg`}" onerror="if(!this.dataset.triedFallback){this.dataset.triedFallback=true; this.src='/bookcase_covers/${book.id}.jpg';}else{this.style.display='none'; this.nextElementSibling.style.display='flex';}">
        <div class="cover-fallback" style="display:none; font-size: 14px;">
          <span style="font-size: 48px; margin-bottom: 10px;">📖</span>
          ${book.title || 'Nová kniha'}
        </div>
      </div>
      <div class="modal-right">
        <div class="section-title"><span>📚</span> Základní informace</div>
        <div class="form-group">
          <label>Název</label>
          <input type="text" id="edit-title" class="text-input" value="${book.title || ''}" placeholder="Titul knihy...">
        </div>
        <div class="form-row cols-2">
          <div class="form-group">
            <label>Podnázev</label>
            <input type="text" id="edit-subtitle" class="text-input" value="${book.subtitle || ''}" placeholder="Podnázev...">
          </div>
          <div class="form-group">
            <label>Autor</label>
            <input type="text" id="edit-author" class="text-input" value="${(book.authors || []).join(', ')}" placeholder="Jméno (čárkou oddělit)">
          </div>
        </div>
        <div class="form-row cols-3">
          <div class="form-group">
            <label>Nakladatelství</label>
            <input type="text" id="edit-publisher" class="text-input" value="${book.publisher || ''}" placeholder="Nakladatel...">
          </div>
          <div class="form-group">
            <label>Rok vydání</label>
            <input type="text" id="edit-year" class="text-input" value="${book.year || ''}" placeholder="2024">
          </div>
          <div class="form-group">
            <label>Jazyk</label>
            <input type="text" id="edit-language" class="text-input" value="${book.language || ''}" placeholder="Čeština">
          </div>
        </div>
        <div class="form-row cols-2">
          <div class="form-group">
            <label>Žánr</label>
            <input type="text" id="edit-genre" class="text-input" value="${genres}" placeholder="Fantasy, Sci-fi...">
          </div>
          <div class="form-group">
            <label>ISBN</label>
            <input type="text" id="edit-isbn" class="text-input" value="${book.isbn || ''}" disabled>
          </div>
        </div>

        <div class="section-title"><span>📖</span> Detaily</div>
        <div class="form-row cols-3">
          <div class="form-group">
            <label>Počet stran</label>
            <input type="number" id="edit-pages" class="text-input" value="${book.page_count || 0}" min="0" step="1">
          </div>
          <div class="form-group">
            <label>Počet výtisků</label>
            <input type="number" id="edit-count" class="text-input" value="${book.count || 1}" min="0" step="1">
          </div>
          <div class="form-group">
            <label>Datum přečtení</label>
            <input type="date" id="edit-date-read" class="text-input" value="${book.date_read || ''}">
          </div>
        </div>
        <div class="form-row cols-2">
          <div class="form-group">
            <label>Obálka (nahrát / vyfotit)</label>
            <div style="display:flex; gap:8px;">
              <button id="upload-cover-btn" class="action-btn" style="flex:1; padding:0 12px; height:42px; background:var(--secondary-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color);" title="Vybrat soubor z galerie">📁 Nahrát</button>
              <button id="camera-cover-btn" class="action-btn" style="flex:1; padding:0 12px; height:42px; background:var(--secondary-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color);" title="Vyfotit obálku">📸 Vyfotit</button>
            </div>
            <input type="file" id="cover-upload-input" style="display:none;" accept="image/*">
            <input type="file" id="cover-camera-input" style="display:none;" accept="image/*" capture="environment">
            <div style="margin-top:8px;">
              <label style="font-size:0.6rem; opacity:0.6;">NEBO URL ADRESA:</label>
              <input type="text" id="edit-cover-url" class="text-input" value="${book.cover_url || ''}" placeholder="https://..." style="width:100%; margin-top:4px;">
            </div>
          </div>
          <div class="form-group">
            <label>Odkaz na knihu</label>
            <input type="text" id="edit-url" class="text-input" value="${book.url || ''}" placeholder="https://...">
          </div>
        </div>

        <div class="section-title"><span>⭐</span> Stav a hodnocení</div>
        <div class="toggle-row">
          <div style="flex:1;"><div class="toggle-btn" id="toggle-read">✓ Přečetl jsem</div><div class="user-list" id="read-users"></div></div>
          <div style="flex:1;"><div class="toggle-btn" id="toggle-wish">♡ Chci přečíst</div><div class="user-list" id="wish-users"></div></div>
        </div>
        <div class="form-row cols-2">
          <div class="form-group">
            <label>Hodnocení</label>
            <div class="rating-stars" id="edit-rating" data-value="${rating}">
              ${[1,2,3,4,5].map(n => `<span data-n="${n}">${n <= rating ? '★' : '☆'}</span>`).join('')}
            </div>
          </div>
          <div class="form-group">
            <label>Status čtení</label>
            <select id="edit-status">
              <option value="to_read" ${status === 'to_read' ? 'selected' : ''}>📗 Máme v knihovně</option>
              <option value="reading" ${status === 'reading' ? 'selected' : ''}>📖 Právě čtu</option>
              <option value="read" ${status === 'read' ? 'selected' : ''}>✅ Přečteno</option>
              <option value="wishlist" ${status === 'wishlist' ? 'selected' : ''}>💫 Wishlist</option>
            </select>
          </div>
        </div>
        <div class="form-row cols-2">
          <div class="form-group">
            <label>Stav fyzické knihy</label>
            <select id="edit-condition">
              <option value="" ${condition === '' ? 'selected' : ''}>-- neuvedeno --</option>
              <option value="nová" ${condition === 'nová' ? 'selected' : ''}>✨ Nová</option>
              <option value="opotřebená" ${condition === 'opotřebená' ? 'selected' : ''}>📖 Opotřebená</option>
              <option value="zničená" ${condition === 'zničená' ? 'selected' : ''}>⚠️ Zničená</option>
            </select>
          </div>
          <div class="form-group">
            <label>Půjčení</label>
            ${isLent
              ? `<div style="display:flex; align-items:center; gap:10px;">
                   <span style="background:#ff9800; color:white; padding:8px 14px; border-radius:8px; font-size:0.85rem; font-weight:600; flex:1;">
                     📦 ${book.lent_to}${book.lent_until ? ' · do ' + book.lent_until : ''}
                   </span>
                   <button class="action-btn" id="btn-return" style="background:#4caf50; padding:8px 16px; font-size:0.85rem;">✓ Vráceno</button>
                 </div>`
              : `<div class="form-row cols-2" style="margin:0;">
                   <input type="text" id="edit-lent" class="text-input" value="" placeholder="Komu půjčit...">
                   <input type="date" id="edit-lent-until" class="text-input" value="" placeholder="Do kdy...">
                 </div>`
            }
          </div>
        </div>

        <div class="section-title"><span>📝</span> Poznámky</div>
        <div class="form-group">
          <textarea id="edit-notes" rows="2" placeholder="Moje osobní poznámky...">${notes}</textarea>
          ${otherUsersHtml}
        </div>
        <div class="form-group">
          <label>Popis</label>
          <textarea id="edit-description" rows="3" placeholder="Popis knihy...">${book.description || ''}</textarea>
        </div>

        <div style="display:flex; gap:12px; margin-top:16px; flex-wrap: wrap;">
          <button class="action-btn" id="save-btn" style="flex: 2; height:48px; font-size:0.95rem; border-radius:10px;">${this._manualMode ? '＋ Přidat knihu' : '💾 Uložit změny'}</button>
          ${!this._manualMode ? `<button class="action-btn" id="refresh-btn" style="background:var(--secondary-background-color); border:1px solid var(--divider-color); height:48px; border-radius:10px; padding:0 15px;" title="Aktualizovat metadata z internetu">🔄</button>` : ''}
          ${!this._manualMode ? `<button class="action-btn" id="modal-delete-btn" style="background:#f44336; height:48px; border-radius:10px; padding:0 15px;">🗑</button>` : ''}
        </div>
      </div>
    `;

    body.querySelector('#toggle-read').onclick = () => this.toggleUser(book.id, 'read');
    body.querySelector('#toggle-wish').onclick = () => this.toggleUser(book.id, 'wish');

    const statusSelect = body.querySelector('#edit-status');
    if (statusSelect) {
      statusSelect.onchange = (e) => {
        const val = e.target.value;
        let readList = JSON.parse(body.dataset.readBy || '[]');
        let wishList = JSON.parse(body.dataset.wishlistBy || '[]');
        readList = readList.filter(u => u !== userName);
        wishList = wishList.filter(u => u !== userName);
        if (val === 'read') readList.push(userName);
        if (val === 'wishlist') wishList.push(userName);
        body.dataset.readBy = JSON.stringify(readList);
        body.dataset.wishlistBy = JSON.stringify(wishList);
        this.updateToggleButtons();
        this.saveBook(book.id, { statuses_by: { [userName]: val }, read_by: readList, wishlist_by: wishList });
      };
    }

    body.querySelectorAll('#edit-rating span').forEach(star => {
      star.onclick = () => {
        const n = parseInt(star.dataset.n);
        body.querySelector('#edit-rating').dataset.value = n;
        body.querySelectorAll('#edit-rating span').forEach(s => s.innerText = parseInt(s.dataset.n) <= n ? '★' : '☆');
        this.saveBook(book.id, { ratings_by: { [userName]: n } });
      };
    });

    const conditionSelect = body.querySelector('#edit-condition');
    if (conditionSelect) conditionSelect.onchange = () => this.saveBook(book.id, { condition: conditionSelect.value });

    const notesArea = body.querySelector('#edit-notes');
    if (notesArea) notesArea.onblur = () => this.saveBook(book.id, { notes_by: { [userName]: notesArea.value.trim() } });

    const returnBtn = body.querySelector('#btn-return');
    if (returnBtn) {
      returnBtn.onclick = () => {
        this.modal.classList.remove('open');
        book.lent_to = null;
        book.lent_until = null;
        this.render();
        this.showToast('Kniha vrácena!', 'success');
        this._hass.callService('bookcase', 'update_book', { book_id: book.id, lent_to: null, lent_until: null });
      };
    }

    body.querySelector('#save-btn').onclick = () => this.saveBook(book.id);
    if (!this._manualMode) {
        body.querySelector('#modal-delete-btn').onclick = () => this.deleteBook(book.id);
        const refreshBtn = body.querySelector('#refresh-btn');
        if (refreshBtn) {
            refreshBtn.onclick = () => {
                this._hass.callService('bookcase', 'refresh_book', { book_id: book.id });
                this.modal.classList.remove('open');
                this.showToast('Aktualizuji metadata...', 'info');
            };
        }
    }

    const uploadBtn = body.querySelector('#upload-cover-btn');
    const cameraBtn = body.querySelector('#camera-cover-btn');
    const uploadInput = body.querySelector('#cover-upload-input');
    const cameraInput = body.querySelector('#cover-camera-input');

    const handleFileUpload = async (file) => {
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        this.showToast('Nahrávám obálku...', 'info');
        const response = await fetch(`/bookcase_covers/${book.id}.jpg`, {
          method: 'POST',
          body: formData,
          headers: {
            'Authorization': `Bearer ${this._hass.auth.data.access_token}`
          }
        });
        if (response.ok) {
          const newUrl = `/bookcase_covers/${book.id}.jpg?v=${Date.now()}`;
          this.showToast('Obálka byla uložena', 'success');
          const urlInput = body.querySelector('#edit-cover-url');
          if (urlInput) urlInput.value = newUrl;
          const img = body.querySelector('.modal-left img');
          if (img) {
            img.style.display = 'block';
            img.src = `${newUrl}`;
            const fallback = body.querySelector('.cover-fallback');
            if (fallback) fallback.style.display = 'none';
          }
        } else {
          const errText = await response.text();
          console.error('Upload failed:', response.status, errText);
          this.showToast(`Nahrávání selhalo (${response.status})`, 'error');
        }
      } catch (err) {
        console.error('Upload error:', err);
        this.showToast('Chyba při nahrávání', 'error');
      }
    };

    if (uploadBtn && uploadInput) {
      uploadBtn.onclick = () => uploadInput.click();
      uploadInput.onchange = (e) => handleFileUpload(e.target.files[0]);
    }
    if (cameraBtn && cameraInput) {
      cameraBtn.onclick = () => cameraInput.click();
      cameraInput.onchange = (e) => handleFileUpload(e.target.files[0]);
    }

    this.updateToggleButtons();
    this.modal.classList.add('open');
  }

  render() {
    if (!this._hass) return;
    let state = this._hass.states['sensor.bookcase_total_books'];
    if (!state) {
      const sensorId = Object.keys(this._hass.states).find(s => s.startsWith('sensor.bookcase_') && this._hass.states[s].attributes && this._hass.states[s].attributes.books);
      if (sensorId) state = this._hass.states[sensorId];
    }
    if (!state || !state.attributes || !state.attributes.books) {
      if (this.querySelector('#stats')) this.querySelector('#stats').innerText = 'Načítám data...';
      return;
    }
    let books = state.attributes.books;
    const userName = this._hass.user ? (this._hass.user.name || this._hass.user.id || 'Uživatel') : 'Uživatel';
    books = books.filter(b => !this._optimisticDeleted.has(b.id));
    if (this._searchQuery) {
      books = books.filter(b => 
        (b.title || '').toLowerCase().includes(this._searchQuery) || 
        (b.authors && Array.isArray(b.authors) && b.authors.some(a => a && typeof a === 'string' && a.toLowerCase().includes(this._searchQuery))) ||
        (b.isbn && b.isbn.toLowerCase().includes(this._searchQuery))
      );
    }
    if (this._filter !== 'all') {
      books = books.filter(b => {
        if (this._filter === 'lent') return b.lent_to;
        const userStatus = (b.statuses_by && b.statuses_by[userName]) || b.status || 'to_read';
        return userStatus === this._filter;
      });
    }
    books.sort((a, b) => {
      let valA, valB;
      const userRating = b => (b.ratings_by && b.ratings_by[userName]) || 0;
      if (this._sortKey === 'added_at') {
        valA = a.added_at || '';
        valB = b.added_at || '';
        return valB.localeCompare(valA);
      } else if (this._sortKey === 'rating') {
        valA = userRating(a);
        valB = userRating(b);
        return valB - valA;
      } else if (this._sortKey === 'page_count') {
        valA = a.page_count || 0;
        valB = b.page_count || 0;
        return valB - valA;
      } else if (this._sortKey === 'authors') {
        valA = (a.authors && a.authors[0]) || '';
        valB = (b.authors && b.authors[0]) || '';
        return valA.localeCompare(valB, 'cs');
      } else {
        valA = a[this._sortKey] || '';
        valB = b[this._sortKey] || '';
        if (typeof valA === 'string') return valA.localeCompare(valB, 'cs');
        return valA - valB;
      }
    });
    this.querySelector('#stats').innerText = `${books.length} knih`;
    this.content.innerHTML = '';
    books.forEach(book => {
      const userStatus = (book.statuses_by && book.statuses_by[userName]) || book.status || 'to_read';
      const card = document.createElement('div');
      card.className = 'book-card';
      card.onclick = () => { this._manualMode = false; this.openDetail(book); };
      const statusColors = { 'to_read': '#2196f3', 'reading': '#4caf50', 'read': '#9c27b0', 'wishlist': '#ff9800' };
      const statusLabels = { 'to_read': 'MÁME', 'reading': 'ČTU', 'read': 'PŘEČTENO', 'wishlist': 'CHCI' };
      card.innerHTML = `
        <div class="cover-wrapper">
          <img src="${book.cover_url || `/bookcase_covers/${book.id}.jpg`}" onerror="if(!this.dataset.triedFallback){this.dataset.triedFallback=true; this.src='/bookcase_covers/${book.id}.jpg';}else{this.style.display='none'; this.nextElementSibling.style.display='flex';}">
          <div class="cover-fallback" style="display:none;">
            <span style="font-size: 24px; margin-bottom: 5px;">📖</span>
            <div style="font-weight:bold; width:100%;">${this._formatTitle(book)}</div>
          </div>
          <div class="status-badge" style="background:${statusColors[userStatus] || '#666'}">${statusLabels[userStatus] || ''}</div>
          ${book.lent_to ? `<div class="lent-badge">📦 ${book.lent_to}${book.lent_until ? ' · do ' + book.lent_until : ''}</div>` : ''}
        </div>
        <div class="book-title">${this._formatTitle(book)}</div>
        <div class="book-isbn" style="font-size:0.7rem; opacity:0.6; margin-top:2px;">${book.isbn || ''}</div>
        <div style="font-size:0.75rem; color:var(--secondary-text-color); margin-top:4px; display:flex; justify-content:space-between;">
          <span class="book-author">${(book.authors && book.authors[0]) ? book.authors[0] : ''}</span>
          ${(book.ratings_by && book.ratings_by[userName]) ? `<span style="color:#ffca28;">${'★'.repeat(book.ratings_by[userName])}</span>` : ''}
        </div>
      `;
      this.content.appendChild(card);
    });
  }
}
customElements.define('bookcase-panel', BookcasePanel);
