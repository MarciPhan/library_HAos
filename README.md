# 📚 Knihovnička (Bookcase) pro Home Assistant

Profesionální integrace pro správu vaší osobní knihovny přímo v Home Assistantovi. Sledujte své knihy, hodnoťte je a sdílejte svou vášeň pro čtení s ostatními členy domácnosti.

![Knihovnička Icon](custom_components/bookcase/icon.png)

## ✨ Hlavní funkce
- **Automatické načítání metadat**: Stačí zadat ISBN nebo starý kód publikace (např. 23-058-65). Integrace čerpá z mnoha zdrojů:
  - **Národní knihovna ČR (NKP)**
  - **Knihovny.cz**
  - **Databazeknih.cz**
  - **Google Books** a **Open Library**
  - **Martinus.cz** a **Didasko.cz**
- **Podpora více uživatelů**: Každý člen domácnosti může mít vlastní hodnocení, poznámky a status u stejné knihy. Data se inteligentně slučují.
- **Sledování stavu**: Mějte přehled o tom, co máte v knihovně, co právě čtete, co je na vašem wishlistu nebo co jste už přečetli.
- **Evidence půjčování**: Sledujte, komu a do kdy jste své knihy půjčili.
- **Statistiky a senzory**: Automatické senzory pro celkový počet knih, přečtené kusy, oblíbené autory atd.
- **Moderní UI**: Krásný, responsivní panel s podporou tmavého režimu a okamžitou odezvou (Optimistic UI).

## 🚀 Instalace
1. Zkopírujte složku `custom_components/bookcase` do vašeho adresáře `config` v HA.
2. Restartujte Home Assistant.
3. Přidejte integraci "Knihovnička" v nastavení (Nastavení -> Zařízení a služby -> Přidat integraci).

## 🛠 Služby
- `bookcase.add_by_isbn`: Přidá knihu pomocí ISBN nebo jiného identifikátoru.
- `bookcase.add_manual`: Ruční přidání knihy bez identifikátoru.
- `bookcase.update_book`: Aktualizace statusu, hodnocení nebo poznámek.
- `bookcase.delete_book`: Odstranění knihy z knihovny.

## 📄 Licence
Tento projekt je licencován pod MIT licencí.

