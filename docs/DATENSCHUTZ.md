# DATENSCHUTZ – Datenschutzkonzept (§14)

## 1. Ist-Zustand

- PropertyRL verarbeitet **keine personenbezogenen Daten**. Alle Daten sind synthetische Spielverläufe,
  Trainingsmetriken, Konfigurationen und Hardware-Kennzahlen der eigenen Maschine (CPU-Modell, Kernzahl,
  RAM, GPU-Name in `run.json` zur Reproduzierbarkeit).
- **Keine Telemetrie** und kein Netzwerkzugriff zur Laufzeit. Bibliotheken werden nur bei der Installation
  geladen.
- **Weights & Biases** ist standardmäßig aus. Mit `--wandb` werden ausschließlich technische Skalare
  (Trainings- und Spielstatistiken, Konfigurations-Hash) protokolliert, und zwar im Offline-Modus, solange
  der Nutzer nicht ausdrücklich `WANDB_MODE=online` setzt (A-124).
- Git-Metadaten in `run.json` beschränken sich auf Commit-Hash und dirty-Flag (keine Autorennamen oder
  E-Mail-Adressen).
- Alle Artefakte bleiben lokal (`artifacts/`, `runs/`, `reports/` bzw. `PROPERTYRL_HOME`).

## 2. Vor jedem Test mit Menschen (nicht Teil dieses Projekts, A-08)

Tests mit Menschen, Human-Evaluationen oder Web-Demos sind Nicht-Ziele. Sollten sie später geplant werden
(Risiko R32), gilt vor dem ersten Test:

1. **Einwilligung:** informierte, freiwillige, dokumentierte Einwilligung jeder teilnehmenden Person; für
   Personen unter 16 Jahren gelten die Einwilligungsregeln nach Art. 8 DSGVO (Mitgliedstaaten dürfen die
   Altersgrenze im vorgesehenen Rahmen absenken), d. h. Einwilligung bzw. Zustimmung der Träger der
   elterlichen Verantwortung.
2. **Information:** Zweck, Art der Daten, Speicherdauer, Empfänger, Rechte (Auskunft, Berichtigung,
   Löschung, Widerruf) in verständlicher Sprache.
3. **Datenminimierung:** nur Pseudonyme, keine Klarnamen, keine IP-Adressen, keine Geräte-Kennungen; nur
   die für die Auswertung nötigen Spielzüge.
4. **Löschfristen:** feste Frist (z. B. Projektende), automatisierte Löschung, Dokumentation.
5. **Keine personenbezogenen Daten in externen Diensten** (kein W&B, keine Cloud-Speicher).
6. **Sicherheit:** lokale, verschlüsselte Speicherung; Zugriff nur für die projektverantwortliche Person.
7. Prüfung, ob eine Datenschutz-Folgenabschätzung oder eine Ethik-Stellungnahme erforderlich ist.
