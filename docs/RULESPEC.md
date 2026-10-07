# RULESPEC v0 – Regelspezifikation PropertyRL

Diese Spezifikation ist die verbindliche Regelgrundlage der Engine. Jede ID hat mindestens einen Test (geprüft durch `tests/architecture/test_rule_coverage.py`). Die Spalte „Test“ nennt bis zu drei Testfälle; die vollständige Zuordnung steht in `docs/TEST_MATRIX.md`. Erzeugt mit `python tools/gen_docs.py`.

## Rulesets

| Ruleset | Inhalt | decision_protocol | auction | trade | scarcity_auction | game_end |
|---|---|---|---|---|---|---|
| OFFICIAL_US_CLASSIC_2008 | R + P + K-01 bis K-04 | official_windows | ascending_open | window_offers | true | natural |
| RESEARCH_2P_BOUNDED_V1 | zusätzlich D-01 bis D-05 | own_turn_only | sealed_7_levels | active_player_only | true | natural |
| RESEARCH_2P_SHORTGAME_V1 | wie RESEARCH_2P_BOUNDED_V1 plus D-06 | own_turn_only | sealed_7_levels | active_player_only | true | short_game (max_rounds = kalibrierter Horizont) |
| TEST_MOVEMENT_ONLY | nur Bewegung (Markov-Test): kein Kauf, keine Miete, keine Steuern, Kartenfelder ohne Wirkung, Startgeld 1.000.000.000, Kaution immer sofort | own_turn_only | – | none (A-108) | false | natural |

Der Safety-Horizon (`safety_horizon_rounds`, Platzhalter 300) wird mit `propertyrl calibrate-horizon` gesetzt (`artifacts/frozen/horizon.json`); er beendet nie das Spiel, nur die Episode (truncated).

## Konstanten (§3.1)

Startgeld 1.500; Gehalt 200; Haft-Kaution 50; Hypothekenzins 10 % aufgerundet (P-05); Bank 32 Häuser und 12 Hotels; Steuer-1 = 200 fest, Steuer-2 = 100; Spielerzahl 2–8 (Engine), 2–4 (RL-Environments); die Bank hat unbegrenzt Geld (R-705).

## Regelkatalog R (beide Modi)

| ID | Regeltext | Quelle | Test |
|---|---|---|---|
| R-001 | Startgeld 1.500 je Spieler. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_data.py::test_starting_cash` |
| R-002 | Brett gemäß §3.2 (configs/board/board_us_neutral.yaml) mit neutralen Namen. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_data.py::test_board_matches_spec` |
| R-003 | Spielerzahl 2–8 (Engine); RL-Environments 2–4. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_data.py::test_player_count_official`<br>`tests/unit/test_data.py::test_player_count_out_of_range` |
| R-101 | Zwei faire sechsseitige Würfel; Zug im Uhrzeigersinn um die Augensumme. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/markov/test_markov.py::test_engine_matches_exact_chain`<br>`tests/unit/test_movement_jail.py::test_roll_moves_by_sum`<br>`tests/unit/test_rng.py::test_dice_fair` |
| R-102 | START überqueren oder betreten: +200; nicht beim Schicken in Haft. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_salary_when_passing_start`<br>`tests/unit/test_movement_jail.py::test_salary_when_landing_on_start`<br>`tests/unit/test_movement_jail.py::test_arrest_square_no_salary`<br>(+1) |
| R-103 | Pasch: nach Auflösung des Feldes erneut würfeln. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_doubles_roll_again_without_window`<br>`tests/golden/scenarios/g01_third_double.yaml` |
| R-104 | Dritter Pasch in Folge: sofort in Haft ohne Bewegung; Zug endet. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/markov/test_markov.py::test_engine_matches_exact_chain`<br>`tests/unit/test_movement_jail.py::test_third_double_goes_to_jail_without_moving`<br>`tests/unit/test_movement_jail.py::test_third_double_movement_only_ruleset`<br>(+2) |
| R-105 | ARREST-Feld: in Haft ohne Gehalt; Zug endet. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_arrest_square_no_salary` |
| R-106 | In Haft: vor dem Wurf Kaution zahlen (Haftzug 1 oder 2), Freikarte nutzen (in jedem Haftzug) oder auf Pasch würfeln; Pasch → frei und Bewegung um diesen Wurf, kein weiterer Wurf. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_jail_options_first_attempt`<br>`tests/unit/test_movement_jail.py::test_no_fine_payment_on_third_attempt_but_card_ok`<br>`tests/unit/test_movement_jail.py::test_fine_requires_cash`<br>(+3) |
| R-107 | Dritter erfolgloser Haftwurf: Kaution 50 zahlen (notfalls über die Schuldenphase), dann Bewegung um diesen Wurf. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_third_failure_pays_and_moves`<br>`tests/unit/test_movement_jail.py::test_third_failure_debt_phase`<br>`tests/golden/scenarios/g02_jail_three_failures.yaml` |
| R-108 | In Haft darf man Miete kassieren, bauen, belasten, handeln und bieten. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_jailed_owner_collects_rent_and_manages`<br>`tests/unit/test_movement_jail.py::test_jailed_player_can_build_mortgage_and_trade` |
| R-109 | Landen auf HAFT ohne Haftstrafe = nur zu Besuch. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_just_visiting` |
| R-110 | Reihenfolge nach Sitz im Uhrzeigersinn; bankrotte Sitze werden übersprungen. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_turn_order_skips_bankrupt` |
| R-201 | Landen auf unbesessenem Besitzrecht: Kauf zum Druckpreis möglich. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_buy_at_printed_price`<br>`tests/unit/test_purchase_rent.py::test_buy_with_exact_cash_leaves_zero`<br>`tests/unit/test_purchase_rent.py::test_buy_illegal_without_cash` |
| R-202 | Abgelehnt: Auktion unter allen aktiven Spielern inklusive Ablehnendem; ohne Gebot bleibt es bei der Bank. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_decline_starts_auction_no_bids_bank_keeps`<br>`tests/unit/test_purchase_rent.py::test_auction_with_three_bidders_order_from_decliner`<br>`tests/golden/scenarios/g16_official_auction_three_bidders.yaml` |
| R-203 | Käufer zahlt an die Bank. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_buy_at_printed_price` |
| R-301 | Straße unbebaut: Grundmiete; doppelt, wenn der Besitzer die ganze Farbgruppe hält (gilt für unbelastete Straßen auch dann, wenn eine andere Straße der Gruppe belastet ist). | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_base_rent_and_double_with_group`<br>`tests/unit/test_purchase_rent.py::test_double_rent_even_if_other_street_mortgaged` |
| R-302 | Miete mit Häusern oder Hotel laut Tabelle. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_rent_with_houses_and_hotel` |
| R-303 | Bahnmiete 25/50/100/200 je nach Zahl der Bahnen des Besitzers. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_rail_rent` |
| R-304 | Werk: 4 × Würfelsumme, mit beiden Werken 10 ×. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_utility_rent` |
| R-305 | Keine Miete auf belastete Besitzrechte. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_no_rent_on_mortgaged` |
| R-306 | Keine Miete auf eigenen Besitz. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_no_rent_on_own_property` |
| R-307 | Besitzer in Haft kassiert weiter. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_movement_jail.py::test_jailed_owner_collects_rent_and_manages` |
| R-308 | Steuer-1 zahlt 200. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_tax_one` |
| R-309 | Steuer-2 zahlt 100. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_tax_two` |
| R-310 | Ruhefeld ohne Wirkung. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_purchase_rent.py::test_rest_square_no_effect` |
| R-401 | Bauen nur mit vollständiger Farbgruppe, kein Mitglied belastet. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_build_requires_complete_unmortgaged_group` |
| R-402 | Gleichmäßig bauen: Stufendifferenz innerhalb der Gruppe höchstens 1; gebaut wird nur auf der niedrigsten Stufe. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_even_building` |
| R-403 | Hotel: alle Straßen der Gruppe auf mindestens 4; ein Hotel kostet einen Hauspreis, die 4 Häuser der Straße gehen an die Bank zurück. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_hotel_requires_four_everywhere_and_returns_houses` |
| R-404 | Bauen nur bei Bankbestand (Haus ≥ 1 bzw. Hotel ≥ 1). | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_build_needs_bank_stock`<br>`tests/golden/scenarios/g05_house_shortage.yaml` |
| R-405 | Verkauf von Gebäuden an die Bank zum halben Kaufpreis, gleichmäßig von der höchsten Stufe abwärts. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_sell_evenly_half_price` |
| R-406 | Hotelverkauf: zurück auf 4 Häuser (Erstattung halber Hauspreis), wenn die Bank 4 Häuser hat; sonst P-08. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_hotel_sale_back_to_four_houses`<br>`tests/golden/scenarios/g06_hotel_selldown.yaml` |
| R-407 | Knappheit: Übersteigt die Nachfrage mehrerer Spieler den Bankbestand, wird versteigert; Protokoll P-19. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_demand_computation`<br>`tests/unit/test_building_mortgage.py::test_scarcity_no_bids_trigger_gets_house`<br>`tests/golden/scenarios/g05_house_shortage.yaml`<br>(+1) |
| R-501 | Belasten nur unbebauter Besitzrechte; ist irgendeine Straße der Gruppe bebaut, ist Belasten für die ganze Gruppe gesperrt; Auszahlung = Hypothekenwert. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_mortgage_payout_and_group_block` |
| R-502 | Ablösen: Hypothekenwert plus 10 % Zins (P-05). | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_unmortgage_cost_rounded_up` |
| R-503 | Erwerb eines belasteten Besitzrechts (Handel, Bankrott): Empfänger zahlt sofort 10 %; danach optional Ablösung nur zum Kapital (P-13), sonst später Kapital plus erneut 10 %. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_cards_debt.py::test_bankruptcy_to_player_transfers_mortgaged_with_interest`<br>`tests/unit/test_cards_debt.py::test_creditor_cannot_pay_interest_cascade`<br>(+2) |
| R-601 | Deckmechanik: je Deck 16 Karten, zu Spielbeginn gemischt; gezogene Karte unter den Stapel; Freikarte bleibt beim Spieler bis zur Nutzung oder zum Bankrott und geht dann unter ihr Deck. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/fuzz/test_fuzz.py::test_rare_event_fuzz`<br>`tests/unit/test_cards_debt.py::test_advance_to_with_salary`<br>`tests/unit/test_cards_debt.py::test_cycle_mask_resets_when_all_drawn`<br>(+1) |
| R-602 | ADVANCE_TO(feld) mit Gehalt beim Überqueren von START. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_advance_to_with_salary`<br>`tests/unit/test_cards_debt.py::test_advance_without_passing_start`<br>`tests/unit/test_cards_debt.py::test_advance_to_start` |
| R-603 | NEAREST_RAIL: nächste Bahn vorwärts; unbesessen → Kaufentscheidung; besessen → doppelte reguläre Bahnmiete. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_nearest_rail_double_rent`<br>`tests/unit/test_cards_debt.py::test_nearest_rail_double_rent_counts_mortgaged_rails`<br>`tests/unit/test_cards_debt.py::test_nearest_rail_over_start_unowned_buy`<br>(+1) |
| R-604 | NEAREST_UTIL: nächstes Werk vorwärts; unbesessen → Kaufentscheidung; besessen → neuer Wurf × 10. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_nearest_util_new_roll_times_ten`<br>`tests/unit/test_cards_debt.py::test_nearest_util_over_start`<br>`tests/golden/scenarios/g11_nearest_util.yaml` |
| R-605 | MOVE_BACK(3): drei Felder zurück, nie über START. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_move_back_from_36_draws_deck_b`<br>`tests/unit/test_cards_debt.py::test_move_back_never_crosses_start`<br>`tests/golden/scenarios/g12_move_back_deck_b.yaml` |
| R-606 | SEND_TO_JAIL: direkt in Haft ohne Gehalt. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_card_send_to_jail` |
| R-607 | JAIL_FREE: Freikarte, behalten bis zur Nutzung. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_jail_free_card_kept`<br>`tests/unit/test_movement_jail.py::test_use_card_returns_it_under_deck`<br>`tests/golden/scenarios/g03_jail_card_to_creditor.yaml` |
| R-608 | COLLECT(betrag): Bank zahlt. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_collect` |
| R-609 | PAY(betrag): Zahlung an die Bank. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_pay` |
| R-610 | PAY_EACH(betrag): Zahlung an jeden aktiven Mitspieler. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_pay_each`<br>`tests/unit/test_cards_debt.py::test_pay_each_bankruptcy_counts_against_bank`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| R-611 | COLLECT_EACH(betrag): jeder aktive Mitspieler zahlt. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_collect_each` |
| R-612 | REPAIRS(je Haus, je Hotel): Zahlung nach Gebäudebestand; ein Hotel zählt als Hotel. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_repairs_hotel_counts_as_hotel`<br>`tests/unit/test_cards_debt.py::test_repairs_without_buildings_is_free`<br>`tests/golden/scenarios/g12_move_back_deck_b.yaml`<br>(+1) |
| R-701 | Zahlungspflicht; reicht das Bargeld nicht, wird Geld durch Gebäudeverkauf und Belasten beschafft (Schuldenphase, P-06). | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_cards_debt.py::test_debt_sell_buildings` |
| R-702 | Bankrott gegenüber einem Spieler: Gebäude zum halben Preis an die Bank, Erlös an den Gläubiger; gesamtes Bargeld, alle Besitzrechte (belastete mit R-503) und Freikarten an den Gläubiger. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/unit/test_cards_debt.py::test_bankruptcy_to_player_transfers_mortgaged_with_interest`<br>`tests/unit/test_cards_debt.py::test_creditor_cannot_pay_interest_cascade`<br>(+2) |
| R-703 | Bankrott gegenüber der Bank: Gebäude an die Bank; Besitzrechte gehen an die Bank und werden sofort einzeln in Brettreihenfolge versteigert (P-12); Freikarten zurück unter ihr Deck. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_bankruptcy_to_bank_auctions_unmortgaged`<br>`tests/golden/scenarios/g08_bankruptcy_to_bank.yaml`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| R-704 | Bankrotte Spieler scheiden aus. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_placements_reverse_bankruptcy_order`<br>`tests/unit/test_movement_jail.py::test_turn_order_skips_bankrupt` |
| R-705 | Die Bank geht nie pleite. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_bank_never_runs_out` |
| R-801 | Handel: Geld, unbebaute Besitzrechte, Bahnen, Werke und Freikarten zu beliebigen Konditionen; Gebäude sind nicht handelbar. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_trade_flow.py::test_trade_cash_for_street`<br>`tests/unit/test_trade_flow.py::test_trade_rails_utilities_and_jail_cards`<br>`tests/unit/test_trade_flow.py::test_buildings_not_tradable`<br>(+1) |
| R-802 | Belastete Besitzrechte sind handelbar (R-503). | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_trade_flow.py::test_interest_affordability`<br>`tests/golden/scenarios/g04_mortgaged_transfer.yaml` |
| R-901 | Spielende, wenn nur noch ein Spieler nicht bankrott ist; er gewinnt. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/unit/test_trade_flow.py::test_last_opponent_bankrupt_while_out_of_turn_windows_pending` |
| R-902 | Platzierung nach umgekehrter Bankrottreihenfolge. | Regelheft US Classic 2008 (neutraler Verweis, siehe docs/LEGAL.md) | `tests/unit/test_cards_debt.py::test_placements_reverse_bankruptcy_order` |

## Protokoll-Interpretationen P (beide Modi)

| ID | Regeltext | Quelle | Test |
|---|---|---|---|
| P-01 | Entscheidungsfenster OFFICIAL: (a) Pre-Roll des aktiven Spielers; (b) Post-Move nach allen Würfen; (c) Out-of-Turn-Fenster für jeden anderen aktiven Spieler in Sitzreihenfolge ab dem nächsten Sitz. Zwischen Pasch-Würfen kein Fenster. Managementaktionen: BUILD, SELL_BUILDING, MORTGAGE, UNMORTGAGE. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_movement_jail.py::test_doubles_roll_again_without_window`<br>`tests/unit/test_trade_flow.py::test_official_window_sequence` |
| P-02 | Handelsangebote zu Beginn jedes Fensters des Inhabers, höchstens 2, je an genau einen Empfänger; Antwort nur Annehmen/Ablehnen; Gegenangebot = neues Angebot im eigenen Fenster; mehr als 2 oder P-14-widrige Angebote → IllegalActionError. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_trade_flow.py::test_offer_limits_and_validation`<br>`tests/unit/test_trade_flow.py::test_stale_second_offer_dropped`<br>`tests/unit/test_trade_flow.py::test_counter_offer_in_own_window` |
| P-03 | Auktion OFFICIAL aufsteigend offen; Reihenfolge ab dem Ablehnenden; Gebot ≥ Höchstgebot + 1 (erstes ≥ 1) und ≤ eigenes Bargeld oder endgültiges Passen; Ende, wenn nach einem Gebot alle anderen gepasst haben oder alle ohne Gebot passen; nach 200 Bietaktionen Zuschlag an das Höchstgebot. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_purchase_rent.py::test_ascending_auction_rules`<br>`tests/unit/test_purchase_rent.py::test_ascending_auction_action_cap`<br>`tests/golden/scenarios/g16_official_auction_three_bidders.yaml` |
| P-04 | Miete wird automatisch kassiert. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_purchase_rent.py::test_base_rent_and_double_with_group`<br>`tests/unit/test_purchase_rent.py::test_rent_paid_without_owner_decision` |
| P-05 | Rundung: 10-%-Zins wird auf ganze Zahl aufgerundet. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_building_mortgage.py::test_unmortgage_cost_rounded_up` |
| P-06 | Schuldenphase: nur MORTGAGE und SELL_BUILDING; bei Bargeld ≥ Schuld automatische Zahlung; ohne legale Liquidationsaktion automatischer Bankrott. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/golden/scenarios/g07_bankruptcy_to_player.yaml` |
| P-07 | Mehrere Gläubiger durch eine Karte (PAY_EACH): Zahlung in Sitzreihenfolge; Bankrott währenddessen gilt gegenüber der Bank; bereits Gezahltes bleibt beim Empfänger. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_cards_debt.py::test_pay_each_bankruptcy_counts_against_bank`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| P-08 | Hotelabbau ohne 4 Häuser in der Bank: atomarer Verkauf der Gruppe bis auf die höchste gleichmäßige Stufe, die der Bankbestand zulässt; Erstattung halber Kaufpreis je Einheit. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_building_mortgage.py::test_hotel_sale_without_houses_sells_group_down`<br>`tests/unit/test_building_mortgage.py::test_group_sold_down_to_zero`<br>`tests/golden/scenarios/g06_hotel_selldown.yaml` |
| P-09 | Kaufentscheidung: vor BUY/DECLINE sind MORTGAGE und SELL_BUILDING erlaubt; BUY nur bei Bargeld ≥ Preis. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_purchase_rent.py::test_raise_money_before_buying` |
| P-10 | Startspieler ist Sitz 0; Positionsvorteil durch Sitzrotation in der Evaluation neutralisiert. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_movement_jail.py::test_seat_zero_starts` |
| P-11 | Belastete Bahnen und Werke zählen bei der Besitzzahl für die Miete mit. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_cards_debt.py::test_nearest_rail_double_rent_counts_mortgaged_rails`<br>`tests/unit/test_purchase_rent.py::test_rail_rent`<br>`tests/golden/scenarios/g10_nearest_rail.yaml` |
| P-12 | An die Bank gefallene belastete Rechte verlieren die Belastung und werden unbelastet versteigert. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_cards_debt.py::test_bankruptcy_to_bank_auctions_unmortgaged`<br>`tests/golden/scenarios/g08_bankruptcy_to_bank.yaml` |
| P-13 | Option „Ablösung nur zum Kapital“ nach R-503 gilt bis zum Ende des nächsten eigenen Managementfensters des Empfängers (Feld interest_prepaid). | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_building_mortgage.py::test_principal_only_repayment`<br>`tests/golden/scenarios/g04_mortgaged_transfer.yaml` |
| P-14 | Handel nur legal, wenn keine Straße in den Gruppen gehandelter Straßen bebaut ist, Geldbeträge ≤ Bargeld des Zahlenden, kein Beteiligter bankrott und jeder Empfänger belasteter Rechte den sofortigen Zins aus seinem Bargeld nach dem Handel zahlen kann. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_trade_flow.py::test_buildings_not_tradable`<br>`tests/unit/test_trade_flow.py::test_offer_limits_and_validation`<br>`tests/unit/test_trade_flow.py::test_interest_affordability` |
| P-15 | Runde: Zähler steigt, wenn der Zug an einen Sitz mit kleinerem oder gleichem Index übergeht. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_movement_jail.py::test_round_counter` |
| P-16 | Watchdogs: höchstens 1.000 Entscheidungen pro Fenster (inkl. Kauf- und Schuldenphase), 5.000 Events pro Zug, 2.000.000 Entscheidungen pro Spiel → EngineWatchdogError mit Spiel-Log. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_trade_flow.py::test_window_watchdog`<br>`tests/unit/test_trade_flow.py::test_turn_event_watchdog`<br>`tests/unit/test_trade_flow.py::test_game_decision_watchdog` |
| P-17 | Kaution beim dritten erfolglosen Haftwurf bei zu wenig Bargeld → Schuldenphase gegenüber der Bank. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_movement_jail.py::test_third_failure_debt_phase`<br>`tests/unit/test_movement_jail.py::test_third_failure_bankrupt_without_assets` |
| P-18 | Nach PAY_JAIL_FINE oder USE_JAIL_CARD ist der Spieler frei und im normalen Pre-Roll. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_movement_jail.py::test_after_fine_normal_pre_roll`<br>`tests/unit/test_movement_jail.py::test_use_card_returns_it_under_deck` |
| P-19 | Knappheitsauktion: Nachfrage d_H/d_T aus legalen, bezahlbaren Bauoptionen; Auslöser bei BUILD, wenn Summe der Nachfrage > Bankbestand und mindestens zwei Interessenten; Prämie zusätzlich zum Hauspreis; ohne Gebot erhält der Auslöser das Gebäude; Fremdgewinner setzt in PLACE_BUILDING. | Protokoll-Interpretation dieses Projekts (Masterplan v1.4) | `tests/unit/test_building_mortgage.py::test_demand_computation`<br>`tests/unit/test_building_mortgage.py::test_scarcity_no_bids_trigger_gets_house`<br>`tests/unit/test_building_mortgage.py::test_scarcity_trigger_wins_pays_premium`<br>(+8) |

## Bekannte Abweichungen K von OFFICIAL

| ID | Regeltext | Quelle | Test |
|---|---|---|---|
| K-01 | Kein Handel während einer Schuldenphase. | Bekannte Abweichung von OFFICIAL | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_trade_flow.py::test_no_trade_offer_during_debt` |
| K-02 | Auktionsgebote sind auf das aktuelle Bargeld begrenzt. | Bekannte Abweichung von OFFICIAL | `tests/unit/test_purchase_rent.py::test_ascending_auction_rules`<br>`tests/unit/test_purchase_rent.py::test_sealed_levels_limited_by_cash` |
| K-03 | Knappheits-Nachfrage nach P-19 berechnet statt angesagt; Spieler ohne Interesse passen. | Bekannte Abweichung von OFFICIAL | `tests/unit/test_building_mortgage.py::test_demand_computation` |
| K-04 | „Jederzeit“ bauen, belasten und handeln ist auf die diskreten Fenster nach P-01 abgebildet. | Bekannte Abweichung von OFFICIAL | `tests/unit/test_building_mortgage.py::test_scarcity_auction_in_out_of_turn_window`<br>`tests/unit/test_trade_flow.py::test_counter_offer_in_own_window` |
| K-05 | (nur scarcity_auction = false, Fallback) Keine Knappheitsauktion; wer zuerst baut, erhält die Häuser. | Bekannte Abweichung von OFFICIAL | `tests/unit/test_building_mortgage.py::test_scarcity_auction_disabled` |

## Research-Abweichungen D

| ID | Regeltext | Quelle | Test |
|---|---|---|---|
| D-01 | Fenster nur im eigenen Zug (Pre-Roll und Post-Move); kein Out-of-Turn-Fenster. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_trade_flow.py::test_research_windows_and_offers` |
| D-02 | Grundstücksauktion verdeckt in einer Runde: Passen oder Stufe 10/25/50/75/100/125/150 % des Druckpreises; Zuschlag zum Preis min(eigenes Gebot, zweithöchstes + 1); ein Gebot → Preis 1; Gleichstand: Sitzreihenfolge ab dem Ablehnenden. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_purchase_rent.py::test_sealed_auction_second_price_plus_one`<br>`tests/unit/test_purchase_rent.py::test_sealed_auction_single_bid_price_one`<br>`tests/unit/test_purchase_rent.py::test_sealed_auction_tie_goes_to_decliner_order`<br>(+2) |
| D-03 | Nur der aktive Spieler bietet Handel an, zu Beginn seines Pre-Roll-Fensters, höchstens 2 pro Zug. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_trade_flow.py::test_research_windows_and_offers` |
| D-04 | Spielerzahl fest 2. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_data.py::test_research_is_two_player_only` |
| D-05 | Knappheitsauktion verdeckt: Passen oder Prämienstufe 0/10/25/50/75/100/150 % des Hauspreises des Auslöser-Ziels; Zuschlag min(eigene, zweithöchste + 1); ein Gebot → Prämie 0; Gleichstand ab P. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_building_mortgage.py::test_scarcity_sealed_research`<br>`tests/unit/test_building_mortgage.py::test_scarcity_sealed_single_bid_premium_zero`<br>`tests/unit/test_building_mortgage.py::test_scarcity_sealed_tie_goes_to_trigger_order`<br>(+1) |
| D-06 | (nur SHORTGAME) Nach max_rounds endet das Spiel terminal; Sieger nach kanonischer Equity, Gleichstand = Remis. | Research-Abweichung (nur RESEARCH-Rulesets) | `tests/unit/test_trade_flow.py::test_short_game_ends_by_equity`<br>`tests/unit/test_trade_flow.py::test_short_game_tie_is_draw`<br>`tests/golden/scenarios/g15_shortgame_draw.yaml` |

## Bewusst nicht implementierte Hausregeln H

Für jede Hausregel prüft ein Test, dass sie **nicht** greift.

| ID | Regeltext | Quelle | Test |
|---|---|---|---|
| H-01 | Geldtopf auf dem Ruhefeld (Steuern und Strafen sammeln). | Hausregel, bewusst nicht implementiert | `tests/unit/test_purchase_rent.py::test_rest_square_no_effect`<br>`tests/unit/test_trade_flow.py::test_no_money_pot_on_rest_square` |
| H-02 | Doppeltes Gehalt beim Landen auf Start. | Hausregel, bewusst nicht implementiert | `tests/unit/test_cards_debt.py::test_advance_to_start`<br>`tests/unit/test_trade_flow.py::test_landing_on_start_single_salary` |
| H-03 | Keine Auktion bei Kaufverzicht. | Hausregel, bewusst nicht implementiert | `tests/unit/test_purchase_rent.py::test_decline_starts_auction_no_bids_bank_keeps` |
| H-04 | Bauen ohne vollständige Farbgruppe oder ungleichmäßig. | Hausregel, bewusst nicht implementiert | `tests/unit/test_building_mortgage.py::test_build_requires_complete_unmortgaged_group`<br>`tests/unit/test_building_mortgage.py::test_even_building` |
| H-05 | Kredite oder Schuldscheine zwischen Spielern. | Hausregel, bewusst nicht implementiert | `tests/unit/test_trade_flow.py::test_offer_limits_and_validation` |
| H-06 | Mietfreiheit oder Immunität als Handelsgegenstand. | Hausregel, bewusst nicht implementiert | `tests/unit/test_trade_flow.py::test_trade_objects_have_no_immunity` |
| H-07 | Keine Miete, solange der Besitzer in Haft ist. | Hausregel, bewusst nicht implementiert | `tests/unit/test_trade_flow.py::test_rent_collected_while_owner_in_jail` |
| H-08 | Abweichendes Startgeld oder Grundstücksverteilung zu Spielbeginn. | Hausregel, bewusst nicht implementiert | `tests/unit/test_trade_flow.py::test_standard_start_no_distribution` |
| H-09 | Kurzspiel mit Zeitlimit (nur als eigene Variante RESEARCH_2P_SHORTGAME_V1, D-06). | Hausregel, bewusst nicht implementiert | `tests/unit/test_trade_flow.py::test_official_has_no_round_limit` |

## V-Punkte (vom Nutzer zu verifizieren, als Konfiguration änderbar)

| V | Gegenstand | Wert | Hinweis |
|---|---|---|---|
| V1 | Fonds-Karte B12 (PAY) | 50 | ältere Ausgaben 150; configs/cards/deck_b.yaml |
| V2 | Steuer-2 | 100 | ältere Ausgaben 75; configs/board/board_us_neutral.yaml |
| V3 | Steuer-1 | 200 fest | ältere Ausgaben 200 oder 10 %; configs/board/board_us_neutral.yaml |
| V4 | Zufall-Karte A13 (PAY) | 15 | configs/cards/deck_a.yaml |
| V5 | Karten je Deck | 16 | configs/cards/ |
| V6 | Spielerzahl | 2–8 | player_count in den Rulesets |

## Zugablauf (§3.10) als Zustandsmaschine

1. Zugbeginn; Rundenzähler nach P-15.
2. Handelsangebote des aktiven Sitzes (OFFICIAL P-02, RESEARCH D-03), dann Pre-Roll-Fenster (PRE_ROLL bzw. JAIL_PRE_ROLL).
3. Wurf; in Haft R-106/R-107; sonst dritter Pasch → R-104, sonst Bewegung, Gehalt, Feldauflösung.
4. Zahlungen über dem Bargeld starten die Schuldenphase (DEBT).
5. Pasch und nicht in Haft → automatischer erneuter Wurf ohne Fenster.
6. OFFICIAL: Angebote und Post-Move-Fenster; RESEARCH: Post-Move-Fenster ohne Angebote.
7. OFFICIAL: Out-of-Turn-Fenster für jeden anderen aktiven Spieler in Sitzreihenfolge.
8. Übergabe an den nächsten aktiven Sitz; R-901 nach jedem Bankrott sofort geprüft.

Interpretationen, die über den Text hinausgehen, stehen in `docs/ASSUMPTIONS.md` (A-1xx).
