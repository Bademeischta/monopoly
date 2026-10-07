# Action Schema v0

Aktionsraum `Discrete(106)`, `action_version` **a1.0**. Erzeugt mit `python tools/gen_docs.py`.

## Phasen und legale Aktionen (§3.11)

| Phase | Legale Aktionen |
|---|---|
| PRE_ROLL | ROLL, BUILD_b, SELL_BUILDING_b, MORTGAGE_p, UNMORTGAGE_p |
| JAIL_PRE_ROLL | ROLL (Pasch-Versuch), PAY_JAIL_FINE (nur jail_attempts 0 oder 1 und Bargeld ≥ 50), USE_JAIL_CARD (falls vorhanden), Managementaktionen |
| BUY | BUY (Bargeld ≥ Preis), DECLINE, MORTGAGE_p, SELL_BUILDING_b (P-09) |
| POST_MOVE, OUT_OF_TURN | END_PHASE und Managementaktionen |
| DEBT | MORTGAGE_p, SELL_BUILDING_b (P-06) |
| PLACE_BUILDING | nur BUILD_b auf legale Ziele des Auktionsgewinners |

Legalität: BUILD_b nach R-401 bis R-404 und Bargeld ≥ Hauspreis; SELL_BUILDING_b nach R-405, R-406, P-08; MORTGAGE_p nach R-501; UNMORTGAGE_p, wenn belastet und Bargeld ≥ Kosten (nur Kapital bei aktivem interest_prepaid). Jeder Entscheidungspunkt hat mindestens eine legale Aktion. Illegale Aktionen werfen `IllegalActionError`; die Maske (`action_masks()`) verhindert sie im Training.

## IDs

| ID | Name | Feld | Bedeutung |
|---|---|---|---|
| 0 | ROLL | – | Würfeln (Pre-Roll) bzw. Pasch-Versuch (Haft) |
| 1 | BUY | – | Kauf zum Druckpreis |
| 2 | DECLINE | – | Kauf ablehnen, startet die Auktion |
| 3 | END_PHASE | – | Post-Move- oder Out-of-Turn-Fenster beenden |
| 4 | PAY_JAIL_FINE | – | Kaution zahlen |
| 5 | USE_JAIL_CARD | – | Freikarte nutzen |
| 6 | BUILD_b0 | 1 (Braun-1) | Haus bzw. Hotel bauen |
| 7 | BUILD_b1 | 3 (Braun-2) | Haus bzw. Hotel bauen |
| 8 | BUILD_b2 | 6 (Hellblau-1) | Haus bzw. Hotel bauen |
| 9 | BUILD_b3 | 8 (Hellblau-2) | Haus bzw. Hotel bauen |
| 10 | BUILD_b4 | 9 (Hellblau-3) | Haus bzw. Hotel bauen |
| 11 | BUILD_b5 | 11 (Pink-1) | Haus bzw. Hotel bauen |
| 12 | BUILD_b6 | 13 (Pink-2) | Haus bzw. Hotel bauen |
| 13 | BUILD_b7 | 14 (Pink-3) | Haus bzw. Hotel bauen |
| 14 | BUILD_b8 | 16 (Orange-1) | Haus bzw. Hotel bauen |
| 15 | BUILD_b9 | 18 (Orange-2) | Haus bzw. Hotel bauen |
| 16 | BUILD_b10 | 19 (Orange-3) | Haus bzw. Hotel bauen |
| 17 | BUILD_b11 | 21 (Rot-1) | Haus bzw. Hotel bauen |
| 18 | BUILD_b12 | 23 (Rot-2) | Haus bzw. Hotel bauen |
| 19 | BUILD_b13 | 24 (Rot-3) | Haus bzw. Hotel bauen |
| 20 | BUILD_b14 | 26 (Gelb-1) | Haus bzw. Hotel bauen |
| 21 | BUILD_b15 | 27 (Gelb-2) | Haus bzw. Hotel bauen |
| 22 | BUILD_b16 | 29 (Gelb-3) | Haus bzw. Hotel bauen |
| 23 | BUILD_b17 | 31 (Grün-1) | Haus bzw. Hotel bauen |
| 24 | BUILD_b18 | 32 (Grün-2) | Haus bzw. Hotel bauen |
| 25 | BUILD_b19 | 34 (Grün-3) | Haus bzw. Hotel bauen |
| 26 | BUILD_b20 | 37 (Dunkelblau-1) | Haus bzw. Hotel bauen |
| 27 | BUILD_b21 | 39 (Dunkelblau-2) | Haus bzw. Hotel bauen |
| 28 | SELL_BUILDING_b0 | 1 (Braun-1) | Gebäude verkaufen (halber Preis) |
| 29 | SELL_BUILDING_b1 | 3 (Braun-2) | Gebäude verkaufen (halber Preis) |
| 30 | SELL_BUILDING_b2 | 6 (Hellblau-1) | Gebäude verkaufen (halber Preis) |
| 31 | SELL_BUILDING_b3 | 8 (Hellblau-2) | Gebäude verkaufen (halber Preis) |
| 32 | SELL_BUILDING_b4 | 9 (Hellblau-3) | Gebäude verkaufen (halber Preis) |
| 33 | SELL_BUILDING_b5 | 11 (Pink-1) | Gebäude verkaufen (halber Preis) |
| 34 | SELL_BUILDING_b6 | 13 (Pink-2) | Gebäude verkaufen (halber Preis) |
| 35 | SELL_BUILDING_b7 | 14 (Pink-3) | Gebäude verkaufen (halber Preis) |
| 36 | SELL_BUILDING_b8 | 16 (Orange-1) | Gebäude verkaufen (halber Preis) |
| 37 | SELL_BUILDING_b9 | 18 (Orange-2) | Gebäude verkaufen (halber Preis) |
| 38 | SELL_BUILDING_b10 | 19 (Orange-3) | Gebäude verkaufen (halber Preis) |
| 39 | SELL_BUILDING_b11 | 21 (Rot-1) | Gebäude verkaufen (halber Preis) |
| 40 | SELL_BUILDING_b12 | 23 (Rot-2) | Gebäude verkaufen (halber Preis) |
| 41 | SELL_BUILDING_b13 | 24 (Rot-3) | Gebäude verkaufen (halber Preis) |
| 42 | SELL_BUILDING_b14 | 26 (Gelb-1) | Gebäude verkaufen (halber Preis) |
| 43 | SELL_BUILDING_b15 | 27 (Gelb-2) | Gebäude verkaufen (halber Preis) |
| 44 | SELL_BUILDING_b16 | 29 (Gelb-3) | Gebäude verkaufen (halber Preis) |
| 45 | SELL_BUILDING_b17 | 31 (Grün-1) | Gebäude verkaufen (halber Preis) |
| 46 | SELL_BUILDING_b18 | 32 (Grün-2) | Gebäude verkaufen (halber Preis) |
| 47 | SELL_BUILDING_b19 | 34 (Grün-3) | Gebäude verkaufen (halber Preis) |
| 48 | SELL_BUILDING_b20 | 37 (Dunkelblau-1) | Gebäude verkaufen (halber Preis) |
| 49 | SELL_BUILDING_b21 | 39 (Dunkelblau-2) | Gebäude verkaufen (halber Preis) |
| 50 | MORTGAGE_p0 | 1 (Braun-1) | belasten |
| 51 | MORTGAGE_p1 | 3 (Braun-2) | belasten |
| 52 | MORTGAGE_p2 | 5 (Bahn-1) | belasten |
| 53 | MORTGAGE_p3 | 6 (Hellblau-1) | belasten |
| 54 | MORTGAGE_p4 | 8 (Hellblau-2) | belasten |
| 55 | MORTGAGE_p5 | 9 (Hellblau-3) | belasten |
| 56 | MORTGAGE_p6 | 11 (Pink-1) | belasten |
| 57 | MORTGAGE_p7 | 12 (Werk-1) | belasten |
| 58 | MORTGAGE_p8 | 13 (Pink-2) | belasten |
| 59 | MORTGAGE_p9 | 14 (Pink-3) | belasten |
| 60 | MORTGAGE_p10 | 15 (Bahn-2) | belasten |
| 61 | MORTGAGE_p11 | 16 (Orange-1) | belasten |
| 62 | MORTGAGE_p12 | 18 (Orange-2) | belasten |
| 63 | MORTGAGE_p13 | 19 (Orange-3) | belasten |
| 64 | MORTGAGE_p14 | 21 (Rot-1) | belasten |
| 65 | MORTGAGE_p15 | 23 (Rot-2) | belasten |
| 66 | MORTGAGE_p16 | 24 (Rot-3) | belasten |
| 67 | MORTGAGE_p17 | 25 (Bahn-3) | belasten |
| 68 | MORTGAGE_p18 | 26 (Gelb-1) | belasten |
| 69 | MORTGAGE_p19 | 27 (Gelb-2) | belasten |
| 70 | MORTGAGE_p20 | 28 (Werk-2) | belasten |
| 71 | MORTGAGE_p21 | 29 (Gelb-3) | belasten |
| 72 | MORTGAGE_p22 | 31 (Grün-1) | belasten |
| 73 | MORTGAGE_p23 | 32 (Grün-2) | belasten |
| 74 | MORTGAGE_p24 | 34 (Grün-3) | belasten |
| 75 | MORTGAGE_p25 | 35 (Bahn-4) | belasten |
| 76 | MORTGAGE_p26 | 37 (Dunkelblau-1) | belasten |
| 77 | MORTGAGE_p27 | 39 (Dunkelblau-2) | belasten |
| 78 | UNMORTGAGE_p0 | 1 (Braun-1) | Belastung ablösen |
| 79 | UNMORTGAGE_p1 | 3 (Braun-2) | Belastung ablösen |
| 80 | UNMORTGAGE_p2 | 5 (Bahn-1) | Belastung ablösen |
| 81 | UNMORTGAGE_p3 | 6 (Hellblau-1) | Belastung ablösen |
| 82 | UNMORTGAGE_p4 | 8 (Hellblau-2) | Belastung ablösen |
| 83 | UNMORTGAGE_p5 | 9 (Hellblau-3) | Belastung ablösen |
| 84 | UNMORTGAGE_p6 | 11 (Pink-1) | Belastung ablösen |
| 85 | UNMORTGAGE_p7 | 12 (Werk-1) | Belastung ablösen |
| 86 | UNMORTGAGE_p8 | 13 (Pink-2) | Belastung ablösen |
| 87 | UNMORTGAGE_p9 | 14 (Pink-3) | Belastung ablösen |
| 88 | UNMORTGAGE_p10 | 15 (Bahn-2) | Belastung ablösen |
| 89 | UNMORTGAGE_p11 | 16 (Orange-1) | Belastung ablösen |
| 90 | UNMORTGAGE_p12 | 18 (Orange-2) | Belastung ablösen |
| 91 | UNMORTGAGE_p13 | 19 (Orange-3) | Belastung ablösen |
| 92 | UNMORTGAGE_p14 | 21 (Rot-1) | Belastung ablösen |
| 93 | UNMORTGAGE_p15 | 23 (Rot-2) | Belastung ablösen |
| 94 | UNMORTGAGE_p16 | 24 (Rot-3) | Belastung ablösen |
| 95 | UNMORTGAGE_p17 | 25 (Bahn-3) | Belastung ablösen |
| 96 | UNMORTGAGE_p18 | 26 (Gelb-1) | Belastung ablösen |
| 97 | UNMORTGAGE_p19 | 27 (Gelb-2) | Belastung ablösen |
| 98 | UNMORTGAGE_p20 | 28 (Werk-2) | Belastung ablösen |
| 99 | UNMORTGAGE_p21 | 29 (Gelb-3) | Belastung ablösen |
| 100 | UNMORTGAGE_p22 | 31 (Grün-1) | Belastung ablösen |
| 101 | UNMORTGAGE_p23 | 32 (Grün-2) | Belastung ablösen |
| 102 | UNMORTGAGE_p24 | 34 (Grün-3) | Belastung ablösen |
| 103 | UNMORTGAGE_p25 | 35 (Bahn-4) | Belastung ablösen |
| 104 | UNMORTGAGE_p26 | 37 (Dunkelblau-1) | Belastung ablösen |
| 105 | UNMORTGAGE_p27 | 39 (Dunkelblau-2) | Belastung ablösen |
