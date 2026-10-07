# LEGAL – Marken, Lizenzen, Quellen

> Unabhängiges Forschungsprojekt, nicht mit Hasbro verbunden, nicht von Hasbro autorisiert;
> Spielmechaniken nachgebildet, keine geschützten Texte oder Gestaltungen.

Dieses Dokument ist keine Rechtsberatung. Vor einem öffentlichen Release (frühestens nach G5, A-07) ist
eine fachkundige Prüfung von Marken-, Urheber- und Lizenzfragen nötig.

## 1. Abgrenzung zu geschützten Inhalten

- Projektname „PropertyRL“; alle Feld-, Gruppen-, Deck- und Kartenbezeichnungen sind eigene, neutrale
  Namen (z. B. „Braun-1“, „Bahn-2“, „Werk-1“, Decks „Zufall“ und „Fonds“, A-28).
- Kartentexte sind eigene Formulierungen; die Engine verarbeitet nur Effekttyp und Parameter.
- Keine Logos, keine Eckfeld- oder Brettgestaltung, keine Originalillustrationen, keine Originaltexte.
- Nachgebildet werden ausschließlich Spielmechaniken und Zahlenwerte (Preise, Mieten, Kartenbeträge), die
  als Konfiguration in `configs/` liegen und vom Nutzer geprüft werden (V-Punkte V1–V6).
- Der Verbotswörter-Test (`tests/architecture/test_forbidden_words.py`) prüft `src/`, `configs/`,
  `docs/`, `tools/`, `.github/`, `README.md`, `CHANGELOG.md` und `pyproject.toml` auf Marken- und
  Original-Feldnamen. Ausnahmen sind nur dieses Dokument und der markierte Abschnitt der README.

## 2. Quellen zu den Regelheften

Die Regeln (Regelkatalog R, Protokoll-Interpretationen P, Abweichungen K und D, Hausregeln H in
`docs/RULESPEC.md`) wurden aus folgenden Quellen nachgebildet; es wurde kein Text übernommen:

1. Hasbro, Inc.: Spielanleitung zu „Monopoly“, US-Ausgabe „Classic“ (2008), Regelheft der Spielschachtel
   (Hauptquelle für OFFICIAL_US_CLASSIC_2008).
2. Ältere US-Ausgaben derselben Spielfamilie (Parker Brothers / Hasbro) als Referenz für die in RULESPEC
   genannten abweichenden Werte älterer Ausgaben (V1–V3).
3. Eigene Protokoll-Interpretationen für Punkte, die die Regelhefte offen lassen (P-IDs), und eigene
   Research-Varianten (D-IDs).

## 3. Lizenzen

- PropertyRL steht unter der MIT-Lizenz (`LICENSE`).
- Laufzeitabhängigkeiten werden mit `propertyrl license-check` (pip-licenses) geprüft: GPL- und
  AGPL-Lizenzen sind verboten (exakter Bezeichnerabgleich), LGPL und MPL erlaubt; Pakete ohne erkennbare
  Lizenzangabe benötigen einen begründeten Eintrag in `configs/license_allowlist.yaml`.
- `src/propertyrl/training/smdp_ppo.py` enthält eine markierte, angepasste Kopie von
  `collect_rollouts` aus sb3-contrib (MIT-Lizenz); jede Änderung trägt den Kommentar `# SMDP change`.
- Externe Agenten (z. B. aus dem Simulator der Purdue-Arbeit) werden nicht mitgeliefert, nicht
  heruntergeladen und nicht eingebunden; eine Anbindung ist nur nach Lizenzprüfung durch den Nutzer über
  die Adapter-Schnittstelle vorgesehen (`docs/EXTERNAL_ANCHOR.md`, A-14).

## 4. Daten

Das Projekt verarbeitet keine personenbezogenen Daten (siehe `docs/DATENSCHUTZ.md`).
