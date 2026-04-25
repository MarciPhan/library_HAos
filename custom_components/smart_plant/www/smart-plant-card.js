class SmartPlantCard extends HTMLElement {
  set hass(hass) {
    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="container">
            <div class="image-container">
              <img id="plant-image" src="" alt="Rostlina">
              
              <div class="upload-btn-container" title="Změnit fotku">
                <ha-icon icon="mdi:camera-plus"></ha-icon>
                <input type="file" id="image-upload" accept="image/*" />
              </div>

              <div class="overlay">
                <div class="header">
                  <h2 id="plant-name"></h2>
                  <p id="plant-species"></p>
                </div>
                
                <div class="care-tips" id="care-tips-container" style="display: none;">
                  <ha-icon icon="mdi:information-outline"></ha-icon>
                  <span id="care-tips"></span>
                </div>

                <div class="stats">
                  <div class="stat">
                    <ha-icon icon="mdi:water"></ha-icon>
                    <span id="next-watering"></span>
                  </div>
                  <div class="stat">
                    <ha-icon id="health-icon" icon="mdi:heart"></ha-icon>
                    <span id="health-status"></span>
                  </div>
                </div>
                <button id="water-button" class="water-btn">
                  <ha-icon icon="mdi:water-pump"></ha-icon>
                  Rostlina zalita
                </button>
              </div>
            </div>
          </div>
          <style>
            ha-card { overflow: hidden; border-radius: 16px; background: var(--card-background-color); position: relative; height: 100%; }
            .container { position: relative; width: 100%; aspect-ratio: 4 / 5; }
            .image-container { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
            #plant-image { width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s ease; }
            .container:hover #plant-image { transform: scale(1.05); }
            .upload-btn-container { position: absolute; top: 12px; right: 12px; background: rgba(0,0,0,0.5); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; color: white; cursor: pointer; transition: all 0.2s ease; z-index: 10; backdrop-filter: blur(4px); }
            .upload-btn-container:hover { background: rgba(0,0,0,0.8); transform: scale(1.1); }
            #image-upload { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
            .overlay { position: absolute; bottom: 0; left: 0; right: 0; padding: 20px; background: linear-gradient(transparent, rgba(0,0,0,0.85)); color: white; display: flex; flex-direction: column; gap: 12px; }
            .header h2 { margin: 0; font-size: 1.6rem; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
            .header p { margin: 0; font-size: 0.9rem; opacity: 0.8; font-style: italic; }
            .care-tips { display: flex; align-items: flex-start; gap: 6px; font-size: 0.85rem; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 8px; backdrop-filter: blur(4px); white-space: pre-line; line-height: 1.4; }
            .care-tips ha-icon { --mdc-icon-size: 16px; flex-shrink: 0; margin-top: 2px; }
            .stats { display: flex; gap: 16px; flex-wrap: wrap; }
            .stat { display: flex; align-items: center; gap: 6px; font-size: 0.9rem; font-weight: 500; }
            .stat ha-icon { --mdc-icon-size: 18px; }
            .water-btn { background: #03a9f4; color: white; border: none; padding: 10px 16px; border-radius: 12px; font-weight: 600; font-size: 0.95rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.2s ease; box-shadow: 0 4px 12px rgba(3, 169, 244, 0.3); margin-top: 4px; }
            .water-btn:hover { background: #039be5; transform: translateY(-2px); box-shadow: 0 6px 16px rgba(3, 169, 244, 0.4); }
            .water-btn:active { transform: translateY(0); }
          </style>
        </ha-card>
      `;
      this.content = this.querySelector('.container');
      this.querySelector('#water-button').onclick = () => this._waterPlant();
      
      const fileInput = this.querySelector('#image-upload');
      fileInput.addEventListener('change', (e) => this._uploadImage(e));
    }

    const config = this._config;
    const entityId = config.entity;
    const state = hass.states[entityId];

    if (!state) {
      this.content.innerHTML = `<p style="padding: 16px;">Entita nebyla nalezena: ${entityId}</p>`;
      return;
    }

    const name = state.attributes.friendly_name ? state.attributes.friendly_name.split(' ')[0] : "Rostlina";
    const species = state.attributes.species || "";
    
    const imgEntityId = entityId.replace('binary_sensor.', 'image.').replace('_needs_water', '_picture');
    const imgState = hass.states[imgEntityId] || hass.states[config.image_entity];
    const imgUrl = imgState ? imgState.attributes.entity_picture : "";

    const nextWateringId = entityId.replace('binary_sensor.', 'sensor.').replace('_needs_water', '_next_watering');
    const nextWateringState = hass.states[nextWateringId];
    
    const healthId = entityId.replace('binary_sensor.', 'select.').replace('_needs_water', '_health');
    const healthState = hass.states[healthId];

    const careTipsId = entityId.replace('binary_sensor.', 'sensor.').replace('_needs_water', '_care_tips');
    const careTipsState = hass.states[careTipsId];

    this.querySelector('#plant-name').textContent = name;
    this.querySelector('#plant-species').textContent = species;
    this.querySelector('#plant-image').src = imgUrl || "/static/images/card_media_placeholder.png";
    this.querySelector('#next-watering').textContent = nextWateringState ? this._formatDate(nextWateringState.state) : "Neznámo";
    
    const healthMap = {
      "Excellent": "Ukázková",
      "Very Good": "Prosperující",
      "Good": "Spokojená",
      "Fair": "Stagnující",
      "Poor": "Chřadnoucí",
      "Critical": "Skomírající",
      "Needs attention": "Skomírající",
      "Výborné": "Ukázková",
      "Velmi dobré": "Prosperující",
      "Dobré": "Spokojená",
      "Ucházející": "Stagnující",
      "Špatné": "Chřadnoucí",
      "Kritické": "Skomírající"
    };
    let healthStr = healthState ? healthState.state : "Neznámo";
    healthStr = healthMap[healthStr] || healthStr;
    this.querySelector('#health-status').textContent = healthStr;
    
    const healthIcon = this.querySelector('#health-icon');
    if (healthState) {
      const h = healthStr.toLowerCase();
      if (h === 'ukázková' || h === 'prosperující') healthIcon.style.color = '#4caf50'; // Zelená
      else if (h === 'spokojená') healthIcon.style.color = '#8bc34a'; // Světle zelená
      else if (h === 'stagnující') healthIcon.style.color = '#ffeb3b'; // Žlutá
      else if (h === 'chřadnoucí') healthIcon.style.color = '#ff9800'; // Oranžová
      else if (h === 'skomírající') healthIcon.style.color = '#f44336'; // Červená
      else if (h === 'kompost') healthIcon.style.color = '#9e9e9e'; // Šedá
      else healthIcon.style.color = '#fff';
    }

    const careTipsContainer = this.querySelector('#care-tips-container');
    const careTipsSpan = this.querySelector('#care-tips');
    if (careTipsState && careTipsState.state && careTipsState.state !== "unknown") {
      careTipsSpan.textContent = careTipsState.state;
      careTipsContainer.style.display = 'flex';
    } else {
      careTipsContainer.style.display = 'none';
    }

    this._hass = hass;
  }

  _formatDate(dateStr) {
    if (!dateStr || dateStr === 'unknown') return "N/A";
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.ceil((date - now) / (1000 * 60 * 60 * 24));
    
    if (diff === 0) return "Dnes";
    if (diff === 1) return "Zítra";
    
    const absDiff = Math.abs(diff);
    let daysText = "dní";
    if (absDiff === 1) daysText = "den";
    else if (absDiff >= 2 && absDiff <= 4) daysText = "dny";

    if (diff < 0) return `Zpoždění ${absDiff} ${daysText}!`;
    return `za ${absDiff} ${daysText}`;
  }

  async _waterPlant() {
    const buttonId = this._config.entity.replace('binary_sensor.', 'button.').replace('_needs_water', '_mark_watered');
    try {
      await this._hass.callService('button', 'press', { entity_id: buttonId });
      const event = new CustomEvent('hass-notification', {
        detail: { message: "Rostlina zalita 💦" },
        bubbles: true,
        composed: true,
      });
      this.dispatchEvent(event);
    } catch (err) {
      console.error(err);
    }
  }

  _uploadImage(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = async () => {
        const canvas = document.createElement('canvas');
        const MAX_WIDTH = 800;
        const MAX_HEIGHT = 800;
        let width = img.width;
        let height = img.height;

        if (width > height) {
          if (width > MAX_WIDTH) {
            height *= MAX_WIDTH / width;
            width = MAX_WIDTH;
          }
        } else {
          if (height > MAX_HEIGHT) {
            width *= MAX_HEIGHT / height;
            height = MAX_HEIGHT;
          }
        }

        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);

        // Komprese do JPEG 80% kvalita
        const base64Data = canvas.toDataURL('image/jpeg', 0.8);
        this.querySelector('#plant-image').src = base64Data;

        try {
          await this._hass.callService('smart_plant', 'upload_image', {
            entity_id: [this._config.entity],
            image_data: base64Data
          });
          const ev = new CustomEvent('hass-notification', {
            detail: { message: "Fotografie nahrána 📷" },
            bubbles: true,
            composed: true,
          });
          this.dispatchEvent(ev);
        } catch (err) {
          console.error("Failed to upload image:", err);
          const ev = new CustomEvent('hass-notification', {
            detail: { message: "Nahrání obrázku se nezdařilo (možná je soubor stále příliš velký) ❌" },
            bubbles: true,
            composed: true,
          });
          this.dispatchEvent(ev);
        }
      };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Zvolte entitu');
    }
    this._config = config;
  }

  static getStubConfig() {
    return { entity: "binary_sensor.rymovnik_needs_water" };
  }

  static getConfigElement() {
    return document.createElement("smart-plant-card-editor");
  }
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "smart-plant-card",
  name: "Smart Plant Card",
  description: "Krásná česká karta pro vaši rostlinu s fotkou a stavem zálivky.",
  preview: true,
  documentationURL: "https://github.com/MarciPhan/smart-plant",
});

customElements.define('smart-plant-card', SmartPlantCard);

class SmartPlantCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this.content) {
      this.innerHTML = `
        <div class="card-config">
          <div class="row">
            <ha-entity-picker
              .hass=${hass}
              .value=${this._config?.entity}
              .includeDomains=${["binary_sensor"]}
              label="Entita rostliny (potřeba zálivky)"
              @value-changed=${this._valueChanged}
            ></ha-entity-picker>
          </div>
        </div>
      `;
      this.content = this.querySelector(".card-config");
    }
  }

  setConfig(config) {
    this._config = config;
  }

  _valueChanged(ev) {
    if (!this._config || !this._hass) return;
    const value = ev.detail.value;
    const event = new CustomEvent("config-changed", {
      detail: { config: { ...this._config, entity: value } },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

customElements.define("smart-plant-card-editor", SmartPlantCardEditor);
