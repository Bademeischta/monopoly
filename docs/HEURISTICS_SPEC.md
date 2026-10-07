# HEURISTICS_SPEC v0 – Bewertungsprimitive, Delegation und Benchmark-Policies

Version: Heuristik-Spezifikation v0 (alle Policies `heuristic_version` = `h1.0`, siehe `src/propertyrl/versions.py`).
Parameter stehen je Policy in `configs/policies/<name>.yaml`; die Implementierungen liegen in
`src/propertyrl/agents/`. Jede Policy hat genau eine versionierte Implementierung, die in Training und
Evaluation identisch verwendet wird (Risiko R16). Die `heuristic_version` jeder beteiligten Policy wird in
allen Lauf-, Checkpoint- und Evaluationsmetadaten gespeichert.

## 1. Policy-Protokoll (§5.1)

Jede Policy (`propertyrl.agents.base.Policy`) besitzt `name`, `version` und fünf Methoden:

| Methode | Aufruf für | Rückgabe |
|---|---|---|
| `act_main(view, legal, rng)` | alle MAIN-Phasen inklusive BUY und PLACE_BUILDING | Aktions-ID (0–105) |
| `propose_trades(view, rng)` | Entscheidung TRADE_OFFER (Fenster) | Liste von `TradeOffer` (höchstens das Angebotslimit) |
| `respond_trade(view, offer, rng)` | Entscheidung TRADE_RESPONSE | `bool` (annehmen) |
| `bid(view, auction, rng)` | Grundstücks- und Knappheitsauktion | `Bid` (OFFICIAL, aufsteigend) oder `BidLevel` (RESEARCH, verdeckt) |
| `liquidate(view, legal, debt, rng)` | DEBT-Phase | Aktions-ID (MORTGAGE, SELL_BUILDING, DECLARE_BANKRUPTCY) |

Verbindliche Regeln für alle Policies:

- Policies sehen nur `PublicState` (`propertyrl.engine.view`): kein Deck-Inhalt, kein RNG-Zustand, keine
  Engine-Referenz. Zwischen Spielen sind sie zustandslos; Zufall kommt ausschließlich aus dem `AgentRng`
  des Sitzes.
- Gleichstände werden deterministisch zugunsten der kleinsten Aktions-ID bzw. des kleinsten Index
  entschieden.
- Jedes Gebot wird mit `clamp_bid` auf das höchste legale Gebot aus dem Entscheidungskontext begrenzt;
  liegt die eigene Grenze unter dem Mindestgebot, wird gepasst.
- Die Dispatch-Funktion `respond(policy, engine, rng)` übersetzt die offene Engine-Entscheidung in den
  passenden Methodenaufruf und prüft das Ergebnis (illegale Antworten lösen `IllegalActionError` aus).

### 1.1 Anti-Oszillation (A-36)

Gilt für alle Policies außer `random_legal` (Implementierung `filter_oscillation` / `anti_oscillation` in
`agents/base.py`). Innerhalb eines Managementfensters (`window_actions` der Entscheidung) ist verboten:

1. UNMORTGAGE eines Rechts, das in diesem Fenster belastet wurde,
2. MORTGAGE eines Rechts, das in diesem Fenster abgelöst wurde,
3. SELL_BUILDING in einer Farbgruppe, in der in diesem Fenster gebaut wurde,
4. BUILD in einer Farbgruppe, in der in diesem Fenster verkauft wurde.

Bleibt nach dem Filter keine Aktion übrig, wird die ungefilterte legale Menge verwendet (FINISH ist im
Fenster immer legal, daher tritt dies praktisch nicht auf). Dieselbe Filterung wird als Zusatzmaske für
RL-Lernsitze und für die Auswertung von RL-Agenten verwendet (A-115), damit ein deterministischer,
untrainierter Agent nicht in Belasten-/Ablösen-Schleifen den Fenster-Watchdog (P-16) auslöst.

## 2. Bewertungsprimitive (§5.2, `agents/primitives.py`, Klasse `Valuer`)

Alle Primitive sind deterministisch und werden von allen Heuristiken geteilt; nie geteilt wird die
Gesamtstrategie.

| Primitive | Definition |
|---|---|
| `landing_freq[sq]` | stationäre Landewahrscheinlichkeit je Feld pro Gegnerzug aus der approximativen Markov-Kette (§4.11 b) mit Bewegungskarten und Haft-Policy; je Haft-Policy einmal berechnet und prozessweit gecacht |
| `rent_now(p, state)` | aktuelle Miete bei Landung; Werke mit erwarteter Würfelsumme 7 |
| `expected_rent(p)` | `landing_freq[feld(p)] × rent_now(p)` |
| `income_per_round(s)` | Summe `expected_rent` über eigene unbelastete Rechte × (aktive Spieler − 1) |
| `marginal_income(s, p)` | `income_per_round` mit p − ohne p (erfasst die Gruppenverdopplung) |
| `asset_value(s, p)` | Druckpreis × (0,5 falls belastet, sonst 1) + H × `marginal_income`, H = 10 Runden; vervollständigt p eine Gruppe von s, zusätzlich 0,5 × H × (Gruppeneinkommen auf Stufe 3 − aktuelles Gruppeneinkommen) |
| `value_ratio(trade, s)` | (Wert erhalten + Geld erhalten − sofortiger Zins) / (Wert gegeben + Geld gegeben); Nenner 0 → unendlich |
| `max_opp_rent` | höchste aktuelle Miete eines gegnerischen Rechts |
| `reserve(R_min)` | `max(R_min, ceil(0,25 × max_opp_rent))` |
| `completes_group(s, trade/p)` | der Erwerb vervollständigt eine Farbgruppe von s |
| `blocks_group(s, p)` | ein Gegner hält bereits Gruppengröße − 1 Rechte der Gruppe von p |
| `level_income_gain(s, b)` | Zuwachs von `income_per_round`, wenn Straße b eine Stufe höher wäre |
| `best_build_target(s)` | legales Bauziel b mit maximalem `level_income_gain / Hauspreis` (Gleichstand kleinster b) |
| `building_premium_value(s)` | `max(0, H × level_income_gain(s, b*) − Hauspreis(b*))` für `b* = best_build_target`; 0 ohne Ziel |

`base_income_per_round(p)` (für das ROI-Kriterium) ist das Einkommen von p ohne Gruppeneffekt und ohne
Gebäude; θ ist der Median der Quote `base_income_per_round(p) / Preis(p)` über alle 28 Rechte.

## 3. Delegation `delegation_v1` (§5.3, `agents/delegation.py`)

Technische Policy für delegierte Entscheidungsarten eines Lernsitzes (Standard: TRADE_OFFER,
TRADE_RESPONSE, AUCTION_BID, DEBT; in Ablation N4 zusätzlich MAIN_BUY). Risikoavers.

| Parameter | Wert |
|---|---|
| Reserve | `reserve(150)` |
| Angebote | höchstens 1 pro Fenster |
| Angebotsfaktor | 1,30 × `asset_value(Gegner, p)` (aufgerundet) |
| Annahme | `value_ratio ≥ 1,30` bzw. `≥ 1,0` bei eigener Gruppenvervollständigung |
| Auktionsschritt | `max(1, ceil(0,05 × Druckpreis))` bzw. `× Hauspreis` |
| Knappheitsdivisor | 1,30 |

- **propose_trades:** nur „Geld gegen Recht“ zur Vervollständigung einer eigenen Gruppe (eigener Besitz =
  Gruppengröße − 1, fehlendes Recht bei einem Gegner, Gruppe unbebaut); Betrag
  `ceil(1,30 × asset_value(Gegner, p))`, nur wenn Bargeld − Betrag ≥ Reserve. Gruppenreihenfolge BRAUN bis
  DUNKELBLAU.
- **respond_trade:** annehmen genau dann, wenn Bargeld danach ≥ Reserve UND das Angebot dem Anbietenden
  keine Gruppe vervollständigt (außer es vervollständigt auch eine eigene) UND (eigene Gruppe
  vervollständigt mit `value_ratio ≥ 1,0` ODER `value_ratio ≥ 1,30`).
- **bid (Grundstück):** Bewertung = `min(asset_value, Bargeld − Reserve)`; OFFICIAL erhöht schrittweise,
  solange Höchstgebot + Schritt ≤ Bewertung, sonst passen; RESEARCH wählt die höchste Stufe ≤ Bewertung.
- **bid (Knappheitsauktion):** Prämiengrenze = `min(floor(building_premium_value / 1,30), Bargeld − Reserve
  − Hauspreis(b*))` (für den Auslöser ist b* das gewählte Ziel); OFFICIAL erstes Gebot 0, wenn die Grenze
  ≥ 0 ist, danach Schritte bis zur Grenze; RESEARCH höchste Stufe ≤ Grenze.
- **liquidate:** zuerst MORTGAGE auf das Recht mit kleinstem `marginal_income` außerhalb bebauter Gruppen,
  dann SELL_BUILDING aus der Gruppe mit dem geringsten Einkommensbeitrag.
- **PLACE_BUILDING** nach gewonnener Knappheitsauktion ist eine MAIN-Entscheidung des Lernsitzes und wird
  nicht delegiert.
- **buy (nur N4):** `act_main` ist nur für Phase BUY zulässig (andere Phasen → `RuleViolationError`); kauft,
  wenn Bargeld − Preis ≥ Reserve oder p eine eigene Gruppe vervollständigt (Bargeld ≥ Preis), sonst
  DECLINE.

## 4. Benchmark-Policies (§5.4)

### 4.1 `random_legal`
MAIN gleichverteilt über legale Aktionen (auch PLACE_BUILDING); keine Angebote; Annahme mit
Wahrscheinlichkeit 0,5; Grundstücksauktion OFFICIAL: mit 0,5 passen, sonst zufälliger Betrag zwischen
Höchstgebot + 1 und `min(Bargeld, Höchstgebot + Druckpreis)`; Knappheitsauktion OFFICIAL: mit 0,5 passen,
sonst zufällige Prämie zwischen Mindestgebot und `min(legale Obergrenze, Höchstgebot + Hauspreis)`; RESEARCH
gleichverteilt über legale Stufen inklusive Passen; DEBT gleichverteilt. Dient zugleich als Fuzzing-Agent.
Keine Anti-Oszillation.

### 4.2 `greedy_v1` (ungesehene Evaluations-Policy, A-32)
BUY, wenn legal; baut wo immer legal (kleinste ID zuerst, wiederholt); belastet nie freiwillig; löst ab,
wenn Bargeld ≥ Kosten; Haft: Freikarte, sonst Kaution, sonst Wurf; keine Angebote, lehnt alles ab;
Grundstücksauktion bis Druckpreis; Knappheitsauktion: Prämie 0, wenn noch kein Gebot vorliegt, sonst
passen; Platzierung kleinste legale ID; DEBT: Gebäude der Gruppe mit kleinstem Hauspreis zuerst, dann Rechte
mit kleinstem Hypothekenwert. `greedy_v1` ist nie Trainingsgegner (der Gegner-Sampler lehnt ihn ab).

### 4.3 `roi_markov_v1`
| Parameter | Wert |
|---|---|
| Reserve | 200 (fest) |
| θ | Median von `base_income_per_round / Preis` über 28 Rechte |
| Ablösen | Bargeld − Kosten ≥ 2 × Reserve |
| Haft bleiben | Summe `expected_rent` gegnerischer Rechte ≥ 50 |
| Auktion | bis `asset_value`; Knappheit bis `floor(building_premium_value)` |

Kauf, wenn (Bargeld − Preis ≥ Reserve und ROI ≥ θ) oder Gruppenvervollständigung bei Bargeld ≥ Preis. Im
BUY-Fenster belastet es das Recht mit kleinstem `marginal_income` nur, wenn der Kauf dadurch eine eigene
Gruppe vervollständigt. Baut die legale Option mit höchstem Mietzuwachs / Hauspreis, solange Bargeld −
Hauspreis ≥ Reserve. Belastet nie freiwillig. Haft: bleiben (ROLL) über der Schwelle, sonst Freikarte bzw.
Kaution. Kein Handel. Platzierung `best_build_target`. DEBT: Belasten nach kleinstem `marginal_income`,
Gebäude zuletzt.

### 4.4 `strong_a_v1`
Wie `roi_markov_v1`, zusätzlich:

| Parameter | Wert |
|---|---|
| Reserve | `reserve(150)` (dynamisch) |
| Blockier-Kauf | ja (`blocks_group`) |
| Bauziel | Stufe 3 auf allen Monopolen (Gruppe mit höchstem Mietzuwachs zuerst), danach Hotels bei Bargeld − Kosten ≥ Reserve + 300 |
| Angebote | höchstens 2 pro Fenster, Faktor 1,15 |
| Annahme | `value_ratio ≥ 1,15` und Anbieter wird nicht komplett, oder eigene Gruppe komplett und Anbieter nicht (oder beide) |
| Auktion | bis 1,1 × `asset_value`; Knappheit bis `floor(1,1 × building_premium_value)` |

Freiwilliges Belasten nur, wenn damit sofort eine Gruppe auf Stufe 3 gebracht wird (nur Rechte außerhalb
dieser Gruppe). Angebote: Geld gegen fehlendes Recht mit `ceil(1,15 × asset_value(Gegner, p))` oder
1:1-Tausch gegen ein eigenes Recht, das dem Gegner keine Gruppe vervollständigt (außer beide
vervollständigen). DEBT: erst Belasten außerhalb bebauter Gruppen, dann Gebäude gleichmäßig aus der
einkommensschwächsten Gruppe.

### 4.5 `strong_b_v1` (aggressiv)
| Parameter | Wert |
|---|---|
| Reserve | 50 |
| Kauf | immer, wenn Bargeld ≥ Preis; belastet dafür, wenn der Kauf eine Gruppe vervollständigt |
| Bauen | maximal, Hotels bevorzugt, solange Bargeld − Kosten ≥ Reserve |
| Ablösen | Bargeld − Kosten ≥ 300 und keine legale Bauoption |
| Haft | sofort raus (Freikarte, dann Kaution, sonst Wurf) |
| Angebote / Annahme | Faktor 1,0; `value_ratio ≥ 1,0`, außer der Anbieter wird komplett und man selbst nicht |
| Auktion | bis 1,25 × `asset_value`; Knappheit bis `floor(1,25 × building_premium_value)` |

Belastet freiwillig Rechte außerhalb der Baugruppe, um zu bauen. Platzierung: höchste erreichbare Stufe
zuerst, Gleichstand `best_build_target`. DEBT: erst Gebäude der Gruppe mit kleinster Stufe, dann Belasten.

## 5. Unterschiede zwischen Delegation und Benchmark-Policies (R15)

| Policy | Reserve | Angebotsfaktor | Annahmeschwelle | Auktionsfaktor | Angebote/Fenster |
|---|---|---|---|---|---|
| delegation_v1 | reserve(150) | 1,30 | 1,30 / 1,0 | min(asset_value, Bargeld − Reserve) | 1 |
| roi_markov_v1 | 200 | – | – (lehnt ab) | 1,0 | 0 |
| strong_a_v1 | reserve(150) | 1,15 | 1,15 | 1,1 | 2 |
| strong_b_v1 | 50 | 1,0 | 1,0 | 1,25 | 2 |
| greedy_v1 | – | – | – (lehnt ab) | Druckpreis | 0 |

Jede Benchmark-Policy unterscheidet sich von jeder anderen und von `delegation_v1` in mindestens einer
Schwelle oder Regel; dies prüft `tests/agents/test_policies.py` (Schwellen-Verschiedenheitstest). Die
Kontroll-Ablation „gemeinsame Delegation“ (`ablation_shared_delegation`) ersetzt bei den Benchmark-Gegnern
die delegierten Arten durch `delegation_v1` (`WithDelegation`), um Zirkularität zu messen.

## 6. Zufallsbeimischung und Komposition (§5.5, §5.6)

- `epsilon:<eps>:<spec>` (`EpsilonPolicy`): Trainingsgegner wählen bei MAIN-Entscheidungen mit
  Wahrscheinlichkeit ε (Standard 0,05) eine zufällige legale Aktion (AgentRng). In jeder Evaluation ist
  ε = 0.
- `CompositePolicy(main, delegated)`: MAIN vom Hauptagenten, alle delegierten Arten von der Delegation.
- `WithDelegation(policy, delegation)`: ersetzt die delegierten Arten einer Benchmark-Policy.
- `SB3Agent`: RL-Agent mit identischem Observation-Encoder; deterministisch (`sb3:`) per maskiertem
  `predict`, stochastisch (`sb3s:`, `snapshot:`, `latest:`) per Inversionsmethode mit AgentRng über die
  maskierte Verteilung.

## 7. Registry-Namen (§5.7)

`random_legal`, `greedy_v1`, `roi_markov_v1`, `strong_a_v1`, `strong_b_v1`, `delegation_v1`,
`with_delegation:<spec>`, `epsilon:<eps>:<spec>`, `sb3:<pfad>`, `sb3s:<pfad>`, `snapshot:<pfad>`,
`latest:<pfad>`, `external:<name>`.
