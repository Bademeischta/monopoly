"""Source of truth for docs/RULESPEC.md: every rule, protocol, deviation and house-rule ID with its text."""

from __future__ import annotations

SRC_RULEBOOK = "Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md)"
SRC_PROTOCOL = "Protokoll-Interpretation dieses Projekts (Masterplan v1.4)"
SRC_K = "Bekannte Abweichung von OFFICIAL"
SRC_D = "Research-Abweichung (nur RESEARCH-Rulesets)"
SRC_H = "Hausregel, bewusst nicht implementiert"

R_RULES: list[tuple[str, str]] = [
    ("R-001", "Startgeld 1.500 je Spieler."),
    ("R-002", "Brett gemäß §3.2 (configs/board/board_us_neutral.yaml) mit neutralen Namen."),
    ("R-003", "Spielerzahl 2–8 (Engine); RL-Environments 2–4."),
    ("R-101", "Zwei faire sechsseitige Würfel; Zug im Uhrzeigersinn um die Augensumme."),
    ("R-102", "START überqueren oder betreten: +200; nicht beim Schicken in Haft."),
    ("R-103", "Pasch: nach Auflösung des Feldes erneut würfeln."),
    ("R-104", "Dritter Pasch in Folge: sofort in Haft ohne Bewegung; Zug endet."),
    ("R-105", "ARREST-Feld: in Haft ohne Gehalt; Zug endet."),
    (
        "R-106",
        "In Haft: vor dem Wurf Kaution zahlen (Haftzug 1 oder 2), Freikarte nutzen (in jedem Haftzug) "
        "oder auf Pasch würfeln; Pasch → frei und Bewegung um diesen Wurf, kein weiterer Wurf.",
    ),
    (
        "R-107",
        "Dritter erfolgloser Haftwurf: Kaution 50 zahlen (notfalls über die Schuldenphase), dann "
        "Bewegung um diesen Wurf.",
    ),
    ("R-108", "In Haft darf man Miete kassieren, bauen, belasten, handeln und bieten."),
    ("R-109", "Landen auf HAFT ohne Haftstrafe = nur zu Besuch."),
    ("R-110", "Reihenfolge nach Sitz im Uhrzeigersinn; bankrotte Sitze werden übersprungen."),
    ("R-201", "Landen auf unbesessenem Besitzrecht: Kauf zum Druckpreis möglich."),
    (
        "R-202",
        "Abgelehnt: Auktion unter allen aktiven Spielern inklusive Ablehnendem; ohne Gebot bleibt es bei der Bank.",
    ),
    ("R-203", "Käufer zahlt an die Bank."),
    (
        "R-301",
        "Straße unbebaut: Grundmiete; doppelt, wenn der Besitzer die ganze Farbgruppe hält (gilt für "
        "unbelastete Straßen auch dann, wenn eine andere Straße der Gruppe belastet ist).",
    ),
    ("R-302", "Miete mit Häusern oder Hotel laut Tabelle."),
    ("R-303", "Bahnmiete 25/50/100/200 je nach Zahl der Bahnen des Besitzers."),
    ("R-304", "Werk: 4 × Würfelsumme, mit beiden Werken 10 ×."),
    ("R-305", "Keine Miete auf belastete Besitzrechte."),
    ("R-306", "Keine Miete auf eigenen Besitz."),
    ("R-307", "Besitzer in Haft kassiert weiter."),
    ("R-308", "Steuer-1 zahlt 200."),
    ("R-309", "Steuer-2 zahlt 100."),
    ("R-310", "Ruhefeld ohne Wirkung."),
    ("R-401", "Bauen nur mit vollständiger Farbgruppe, kein Mitglied belastet."),
    (
        "R-402",
        "Gleichmäßig bauen: Stufendifferenz innerhalb der Gruppe höchstens 1; gebaut wird nur auf der "
        "niedrigsten Stufe.",
    ),
    (
        "R-403",
        "Hotel: alle Straßen der Gruppe auf mindestens 4; ein Hotel kostet einen Hauspreis, die 4 Häuser "
        "der Straße gehen an die Bank zurück.",
    ),
    ("R-404", "Bauen nur bei Bankbestand (Haus ≥ 1 bzw. Hotel ≥ 1)."),
    (
        "R-405",
        "Verkauf von Gebäuden an die Bank zum halben Kaufpreis, gleichmäßig von der höchsten Stufe abwärts.",
    ),
    (
        "R-406",
        "Hotelverkauf: zurück auf 4 Häuser (Erstattung halber Hauspreis), wenn die Bank 4 Häuser hat; sonst P-08.",
    ),
    (
        "R-407",
        "Knappheit: Übersteigt die Nachfrage mehrerer Spieler den Bankbestand, wird versteigert; Protokoll P-19.",
    ),
    (
        "R-501",
        "Belasten nur unbebauter Besitzrechte; ist irgendeine Straße der Gruppe bebaut, ist Belasten für "
        "die ganze Gruppe gesperrt; Auszahlung = Hypothekenwert.",
    ),
    ("R-502", "Ablösen: Hypothekenwert plus 10 % Zins (P-05)."),
    (
        "R-503",
        "Erwerb eines belasteten Besitzrechts (Handel, Bankrott): Empfänger zahlt sofort 10 %; danach "
        "optional Ablösung nur zum Kapital (P-13), sonst später Kapital plus erneut 10 %.",
    ),
    (
        "R-601",
        "Deckmechanik: je Deck 16 Karten, zu Spielbeginn gemischt; gezogene Karte unter den Stapel; "
        "Freikarte bleibt beim Spieler bis zur Nutzung oder zum Bankrott und geht dann unter ihr Deck.",
    ),
    ("R-602", "ADVANCE_TO(feld) mit Gehalt beim Überqueren von START."),
    (
        "R-603",
        "NEAREST_RAIL: nächste Bahn vorwärts; unbesessen → Kaufentscheidung; besessen → doppelte reguläre Bahnmiete.",
    ),
    (
        "R-604",
        "NEAREST_UTIL: nächstes Werk vorwärts; unbesessen → Kaufentscheidung; besessen → neuer Wurf × 10.",
    ),
    ("R-605", "MOVE_BACK(3): drei Felder zurück, nie über START."),
    ("R-606", "SEND_TO_JAIL: direkt in Haft ohne Gehalt."),
    ("R-607", "JAIL_FREE: Freikarte, behalten bis zur Nutzung."),
    ("R-608", "COLLECT(betrag): Bank zahlt."),
    ("R-609", "PAY(betrag): Zahlung an die Bank."),
    ("R-610", "PAY_EACH(betrag): Zahlung an jeden aktiven Mitspieler."),
    ("R-611", "COLLECT_EACH(betrag): jeder aktive Mitspieler zahlt."),
    ("R-612", "REPAIRS(je Haus, je Hotel): Zahlung nach Gebäudebestand; ein Hotel zählt als Hotel."),
    (
        "R-701",
        "Zahlungspflicht; reicht das Bargeld nicht, wird Geld durch Gebäudeverkauf und Belasten "
        "beschafft (Schuldenphase, P-06).",
    ),
    (
        "R-702",
        "Bankrott gegenüber einem Spieler: Gebäude zum halben Preis an die Bank, Erlös an den Gläubiger; "
        "gesamtes Bargeld, alle Besitzrechte (belastete mit R-503) und Freikarten an den Gläubiger.",
    ),
    (
        "R-703",
        "Bankrott gegenüber der Bank: Gebäude an die Bank; Besitzrechte gehen an die Bank und werden "
        "sofort einzeln in Brettreihenfolge versteigert (P-12); Freikarten zurück unter ihr Deck.",
    ),
    ("R-704", "Bankrotte Spieler scheiden aus."),
    ("R-705", "Die Bank geht nie pleite."),
    (
        "R-801",
        "Handel: Geld, unbebaute Besitzrechte, Bahnen, Werke und Freikarten zu beliebigen Konditionen; "
        "Gebäude sind nicht handelbar.",
    ),
    ("R-802", "Belastete Besitzrechte sind handelbar (R-503)."),
    ("R-901", "Spielende, wenn nur noch ein Spieler nicht bankrott ist; er gewinnt."),
    ("R-902", "Platzierung nach umgekehrter Bankrottreihenfolge."),
]

P_RULES: list[tuple[str, str]] = [
    (
        "P-01",
        "Entscheidungsfenster OFFICIAL: (a) Pre-Roll des aktiven Spielers; (b) Post-Move nach allen "
        "Würfen; (c) Out-of-Turn-Fenster für jeden anderen aktiven Spieler in Sitzreihenfolge ab dem "
        "nächsten Sitz. Zwischen Pasch-Würfen kein Fenster. Managementaktionen: BUILD, SELL_BUILDING, "
        "MORTGAGE, UNMORTGAGE.",
    ),
    (
        "P-02",
        "Handelsangebote zu Beginn jedes Fensters des Inhabers, höchstens 2, je an genau einen Empfänger; "
        "Antwort nur Annehmen/Ablehnen; Gegenangebot = neues Angebot im eigenen Fenster; mehr als 2 oder "
        "P-14-widrige Angebote → IllegalActionError.",
    ),
    (
        "P-03",
        "Auktion OFFICIAL aufsteigend offen; Reihenfolge ab dem Ablehnenden; Gebot ≥ Höchstgebot + 1 "
        "(erstes ≥ 1) und ≤ eigenes Bargeld oder endgültiges Passen; Ende, wenn nach einem Gebot alle "
        "anderen gepasst haben oder alle ohne Gebot passen; nach 200 Bietaktionen Zuschlag an das "
        "Höchstgebot.",
    ),
    ("P-04", "Miete wird automatisch kassiert."),
    ("P-05", "Rundung: 10-%-Zins wird auf ganze Zahl aufgerundet."),
    (
        "P-06",
        "Schuldenphase: nur MORTGAGE und SELL_BUILDING; bei Bargeld ≥ Schuld automatische Zahlung; ohne "
        "legale Liquidationsaktion automatischer Bankrott.",
    ),
    (
        "P-07",
        "Mehrere Gläubiger durch eine Karte (PAY_EACH): Zahlung in Sitzreihenfolge; Bankrott währenddessen "
        "gilt gegenüber der Bank; bereits Gezahltes bleibt beim Empfänger.",
    ),
    (
        "P-08",
        "Hotelabbau ohne 4 Häuser in der Bank: atomarer Verkauf der Gruppe bis auf die höchste "
        "gleichmäßige Stufe, die der Bankbestand zulässt; Erstattung halber Kaufpreis je Einheit.",
    ),
    (
        "P-09",
        "Kaufentscheidung: vor BUY/DECLINE sind MORTGAGE und SELL_BUILDING erlaubt; BUY nur bei Bargeld ≥ Preis.",
    ),
    ("P-10", "Startspieler ist Sitz 0; Positionsvorteil durch Sitzrotation in der Evaluation neutralisiert."),
    ("P-11", "Belastete Bahnen und Werke zählen bei der Besitzzahl für die Miete mit."),
    (
        "P-12",
        "An die Bank gefallene belastete Rechte verlieren die Belastung und werden unbelastet versteigert.",
    ),
    (
        "P-13",
        "Option „Ablösung nur zum Kapital“ nach R-503 gilt bis zum Ende des nächsten eigenen "
        "Managementfensters des Empfängers (Feld interest_prepaid).",
    ),
    (
        "P-14",
        "Handel nur legal, wenn keine Straße in den Gruppen gehandelter Straßen bebaut ist, Geldbeträge ≤ "
        "Bargeld des Zahlenden, kein Beteiligter bankrott und jeder Empfänger belasteter Rechte den "
        "sofortigen Zins aus seinem Bargeld nach dem Handel zahlen kann.",
    ),
    ("P-15", "Runde: Zähler steigt, wenn der Zug an einen Sitz mit kleinerem oder gleichem Index übergeht."),
    (
        "P-16",
        "Watchdogs: höchstens 1.000 Entscheidungen pro Fenster (inkl. Kauf- und Schuldenphase), 5.000 "
        "Events pro Zug, 2.000.000 Entscheidungen pro Spiel → EngineWatchdogError mit Spiel-Log.",
    ),
    (
        "P-17",
        "Kaution beim dritten erfolglosen Haftwurf bei zu wenig Bargeld → Schuldenphase gegenüber der Bank.",
    ),
    ("P-18", "Nach PAY_JAIL_FINE oder USE_JAIL_CARD ist der Spieler frei und im normalen Pre-Roll."),
    (
        "P-19",
        "Knappheitsauktion: Nachfrage d_H/d_T aus legalen, bezahlbaren Bauoptionen; Auslöser bei BUILD, "
        "wenn Summe der Nachfrage > Bankbestand und mindestens zwei Interessenten; Prämie zusätzlich zum "
        "Hauspreis; ohne Gebot erhält der Auslöser das Gebäude; Fremdgewinner setzt in PLACE_BUILDING.",
    ),
]

K_RULES: list[tuple[str, str]] = [
    ("K-01", "Kein Handel während einer Schuldenphase."),
    ("K-02", "Auktionsgebote sind auf das aktuelle Bargeld begrenzt."),
    ("K-03", "Knappheits-Nachfrage nach P-19 berechnet statt angesagt; Spieler ohne Interesse passen."),
    ("K-04", "„Jederzeit“ bauen, belasten und handeln ist auf die diskreten Fenster nach P-01 abgebildet."),
    (
        "K-05",
        "(nur scarcity_auction = false, Fallback) Keine Knappheitsauktion; wer zuerst baut, erhält die Häuser.",
    ),
]

D_RULES: list[tuple[str, str]] = [
    ("D-01", "Fenster nur im eigenen Zug (Pre-Roll und Post-Move); kein Out-of-Turn-Fenster."),
    (
        "D-02",
        "Grundstücksauktion verdeckt in einer Runde: Passen oder Stufe 10/25/50/75/100/125/150 % des "
        "Druckpreises; Zuschlag zum Preis min(eigenes Gebot, zweithöchstes + 1); ein Gebot → Preis 1; "
        "Gleichstand: Sitzreihenfolge ab dem Ablehnenden.",
    ),
    (
        "D-03",
        "Nur der aktive Spieler bietet Handel an, zu Beginn seines Pre-Roll-Fensters, höchstens 2 pro Zug.",
    ),
    ("D-04", "Spielerzahl fest 2."),
    (
        "D-05",
        "Knappheitsauktion verdeckt: Passen oder Prämienstufe 0/10/25/50/75/100/150 % des Hauspreises "
        "des Auslöser-Ziels; Zuschlag min(eigene, zweithöchste + 1); ein Gebot → Prämie 0; Gleichstand ab P.",
    ),
    (
        "D-06",
        "(nur SHORTGAME) Nach max_rounds endet das Spiel terminal; Sieger nach kanonischer Equity, "
        "Gleichstand = Remis.",
    ),
]

H_RULES: list[tuple[str, str]] = [
    ("H-01", "Geldtopf auf dem Ruhefeld (Steuern und Strafen sammeln)."),
    ("H-02", "Doppeltes Gehalt beim Landen auf Start."),
    ("H-03", "Keine Auktion bei Kaufverzicht."),
    ("H-04", "Bauen ohne vollständige Farbgruppe oder ungleichmäßig."),
    ("H-05", "Kredite oder Schuldscheine zwischen Spielern."),
    ("H-06", "Mietfreiheit oder Immunität als Handelsgegenstand."),
    ("H-07", "Keine Miete, solange der Besitzer in Haft ist."),
    ("H-08", "Abweichendes Startgeld oder Grundstücksverteilung zu Spielbeginn."),
    ("H-09", "Kurzspiel mit Zeitlimit (nur als eigene Variante RESEARCH_2P_SHORTGAME_V1, D-06)."),
]

V_POINTS: list[tuple[str, str, str, str]] = [
    ("V1", "Fonds-Karte B12 (PAY)", "50", "ältere Ausgaben 150; configs/cards/deck_b.yaml"),
    ("V2", "Steuer-2", "100", "ältere Ausgaben 75; configs/board/board_us_neutral.yaml"),
    ("V3", "Steuer-1", "200 fest", "ältere Ausgaben 200 oder 10 %; configs/board/board_us_neutral.yaml"),
    ("V4", "Zufall-Karte A13 (PAY)", "15", "configs/cards/deck_a.yaml"),
    ("V5", "Karten je Deck", "16", "configs/cards/"),
    ("V6", "Spielerzahl", "2–8", "player_count in den Rulesets"),
]
