# Smart Plant Integration for Home Assistant

Tato integrace je vylepšenou verzí "Simple Plant", která automaticky doplňuje informace o rostlinách z OpenPlantbook.

## Funkce
- **Automatické vyhledávání**: Při přidávání rostliny se stáhnou data z OpenPlantbook.
- **Sledování zalévání**: Výpočet příštího zalévání na základě nároků rostliny.
- **Tipy k péči**: Zobrazuje ideální světlo a teplotu.
- **Historie**: Sledování posledních 10 zalití a změn stavu zdraví.
- **Obrázky**: Automatické načítání fotek rostlin.

## Entity
Integrace vytváří pro každou rostlinu následující entity (příklad pro rostlinu "Ficus"):
- `binary_sensor.ficus_needs_water`
- `binary_sensor.ficus_problem`
- `button.ficus_mark_watered`
- `sensor.ficus_next_watering`
- `sensor.ficus_care_tips`
- `image.ficus_picture`
- `number.ficus_days_between_waterings`
- `select.ficus_health`
- `date.ficus_last_watered`

## Kompatibilita s Simple Plant Card
Pokud chcete použít `simple-plant-card`, stačí v konfiguraci karty nastavit odpovídající entity. Názvy entit jsou navrženy tak, aby byly intuitivní a snadno se párovaly.

## API Klíč
Budete potřebovat Client ID a Client Secret z [OpenPlantbook API](https://open.plantbook.io/).
