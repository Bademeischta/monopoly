# EXTERNAL_ANCHOR – Anbindung eines externen Agenten (§5.8)

PropertyRL enthält nur die **Schnittstelle** `ExternalAgentAdapter` (`src/propertyrl/agents/external.py`).
Es wird kein fremder Code mitgeliefert und nichts heruntergeladen. Fehlt ein Adapter, entfällt der externe
Anker ohne Auswirkung auf die Gates; `external:<name>` löst dann einen `ConfigError` aus.

## 1. Zweck

Ein externer Referenzagent (z. B. ein Agent aus dem GNOME-p3-Simulator der Purdue-Arbeit) kann als
zusätzlicher, unabhängiger Maßstab für die Stärke der Baselines dienen (Risiko R17). Voraussetzung ist eine
Lizenzprüfung durch den Nutzer (A-14): Der Code des externen Projekts wird nur lokal und nur nach dieser
Prüfung verwendet und nicht in dieses Repository übernommen.

## 2. Schritte der Anbindung

1. **Lizenz prüfen** (Lizenztext des externen Projekts, Verträglichkeit mit MIT, keine GPL/AGPL-Bindung des
   eigenen Codes). Ergebnis in diesem Dokument festhalten.
2. **Adapter-Klasse schreiben** (außerhalb von `src/propertyrl` oder in einem privaten Modul), abgeleitet
   von `ExternalAgentAdapter`:
   - `translate_state(view: PublicState)`: Übersetzung des öffentlichen Zustands in die Zustandsdarstellung
     des externen Agenten (Positionen, Bargeld, Besitz, Hypotheken, Gebäude, Haftstatus, Freikarten).
     Feldindizes über die Index-Abbildungen aus `docs/RULESPEC.md` bzw. `engine/constants.py` abbilden.
   - `external_decide(state, rng)`: Aufruf des externen Agenten; Zufall nur über den übergebenen
     `AgentRng`, damit Spiele reproduzierbar bleiben.
   - `translate_action(action, view, legal)`: Rückübersetzung in eine **legale** Aktions-ID (0–105). Nicht
     abbildbare Aktionen werden auf die nächstliegende legale Aktion abgebildet und gezählt.
   - `propose_trades`, `respond_trade`, `bid`, `liquidate`: entsprechend übersetzen; fehlt eine Fähigkeit,
     sind neutrale Antworten zulässig (keine Angebote, ablehnen, passen, Liquidation nach festem Schema).
3. **Registrieren:** `register_external("anchor", MyAdapter)`; danach ist `external:anchor` in Evaluation
   und Round-Robin verwendbar (z. B. `propertyrl evaluate --agent strong_a_v1 --opponents external:anchor`).
4. **Regelabweichungen dokumentieren:** Jede Abweichung des externen Simulators von
   OFFICIAL_US_CLASSIC_2008 wird hier aufgeführt. Bekannt ist, dass der Purdue-Simulator **Pasche wie normale
   Würfe** behandelt (kein Zusatzwurf, keine Haft nach dem dritten Pasch). Weitere typische Prüfpunkte:
   Auktionsform, Hausknappheit, Hypothekenzins bei Übertragung, Handelsprotokoll, Bankrottablauf.
5. **Ergebnisse kennzeichnen:** Vergleiche mit dem externen Anker werden im Report als „externer Anker“
   markiert und nicht für Gates verwendet.

## 3. Optionaler Differential-Test

Für Regeln, die beide Simulatoren identisch umsetzen, kann ein Differential-Test die Engine gegen den
externen Simulator prüfen:

1. Szenarien mit festen Würfelfolgen (`EngineOptions.dice_script`) und fester Kartenreihenfolge
   (`card_order`) erzeugen, die nur überlappende Regeln berühren (Bewegung ohne Pasch, Kauf, Miete inklusive
   Gruppenverdopplung, Bahnen, Werke, Steuern, Hypotheken ohne Übertragung).
2. Dieselben Züge im externen Simulator ausführen (über den Adapter, lokal).
3. Nach jedem Zug Bargeld, Positionen, Besitz und Gebäude vergleichen; Abweichungen mit Regel-ID protokollieren.
4. Der Test ist optional, wird übersprungen, wenn kein Adapter registriert ist, und ist kein Gate-Kriterium.
