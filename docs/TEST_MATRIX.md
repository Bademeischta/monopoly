# Testmatrix

Erzeugt mit `python tools/gen_docs.py` aus den Markern `@pytest.mark.rule(...)` und den Golden-Game-Szenarien.

## Regel-ID → Tests

| ID | Tests |
|---|---|
| R-001 | `tests/unit/test_data.py::test_starting_cash` |
| R-002 | `tests/unit/test_data.py::test_board_matches_spec` |
| R-003 | `tests/unit/test_data.py::test_player_count_official`<br>`tests/unit/test_data.py::test_player_count_out_of_range` |
| R-101 | `tests/markov/test_markov.py::test_engine_matches_exact_chain`<br>`tests/unit/test_movement_jail.py::test_roll_moves_by_sum`<br>`tests/unit/test_rng.py::test_dice_fair` |
| R-102 | `tests/unit/test_movement_jail.py::test_salary_when_passing_start`<br>`tests/unit/test_movement_jail.py::test_salary_when_landing_on_start`<br>`tests/unit/test_movement_jail.py::test_arrest_square_no_salary`<br>`tests/golden/scenarios/g10_nearest_rail.yaml` |
| R-103 | `tests/unit/test_movement_jail.py::test_doubles_roll_again_without_window`<br>`tests/golden/scenarios/g01_third_double.yaml` |
| R-104 | `tests/markov/test_markov.py::test_engine_matches_exact_chain`<br>`tests/unit/test_movement_jail.py::test_third_double_goes_to_jail_without_moving`<br>`tests/unit/test_movement_jail.py::test_third_double_movement_only_ruleset`<br>`tests/unit/test_movement_jail.py::test_both_jail_cards_deck_a_used_first`<br>`tests/golden/scenarios/g01_third_double.yaml` |
| R-105 | `tests/unit/test_movement_jail.py::test_arrest_square_no_salary` |
| R-106 | `tests/unit/test_movement_jail.py::test_jail_options_first_attempt`<br>`tests/unit/test_movement_jail.py::test_no_fine_payment_on_third_attempt_but_card_ok`<br>`tests/unit/test_movement_jail.py::test_fine_requires_cash`<br>`tests/unit/test_movement_jail.py::test_jail_doubles_frees_and_moves_once`<br>`tests/unit/test_movement_jail.py::test_jail_failed_roll_stays`<br>`tests/golden/scenarios/g02_jail_three_failures.yaml` |
| R-107 | `tests/unit/test_movement_jail.py::test_third_failure_pays_and_moves`<br>`tests/unit/test_movement_jail.py::test_third_failure_debt_phase`<br>`tests/golden/scenarios/g02_jail_three_failures.yaml` |
| R-108 | `tests/unit/test_movement_jail.py::test_jailed_owner_collects_rent_and_manages`<br>`tests/unit/test_movement_jail.py::test_jailed_player_can_build_mortgage_and_trade` |
| R-109 | `tests/unit/test_movement_jail.py::test_just_visiting` |
| R-110 | `tests/unit/test_movement_jail.py::test_turn_order_skips_bankrupt` |
| R-201 | `tests/unit/test_purchase_rent.py::test_buy_at_printed_price`<br>`tests/unit/test_purchase_rent.py::test_buy_with_exact_cash_leaves_zero`<br>`tests/unit/test_purchase_rent.py::test_buy_illegal_without_cash` |
| R-202 | `tests/unit/test_purchase_rent.py::test_decline_starts_auction_no_bids_bank_keeps`<br>`tests/unit/test_purchase_rent.py::test_auction_with_three_bidders_order_from_decliner`<br>`tests/golden/scenarios/g16_official_auction_three_bidders.yaml` |
| R-203 | `tests/unit/test_purchase_rent.py::test_buy_at_printed_price` |
| R-301 | `tests/unit/test_purchase_rent.py::test_base_rent_and_double_with_group`<br>`tests/unit/test_purchase_rent.py::test_double_rent_even_if_other_street_mortgaged` |
| R-302 | `tests/unit/test_purchase_rent.py::test_rent_with_houses_and_hotel` |
| R-303 | `tests/unit/test_purchase_rent.py::test_rail_rent` |
| R-304 | `tests/unit/test_purchase_rent.py::test_utility_rent` |
| R-305 | `tests/unit/test_purchase_rent.py::test_no_rent_on_mortgaged` |
| R-306 | `tests/unit/test_purchase_rent.py::test_no_rent_on_own_property` |
| R-307 | `tests/unit/test_movement_jail.py::test_jailed_owner_collects_rent_and_manages` |
| R-308 | `tests/unit/test_purchase_rent.py::test_tax_one` |
| R-309 | `tests/unit/test_purchase_rent.py::test_tax_two` |
| R-310 | `tests/unit/test_purchase_rent.py::test_rest_square_no_effect` |
| R-401 | `tests/unit/test_building_mortgage.py::test_build_requires_complete_unmortgaged_group` |
| R-402 | `tests/unit/test_building_mortgage.py::test_even_building` |
| R-403 | `tests/unit/test_building_mortgage.py::test_hotel_requires_four_everywhere_and_returns_houses` |
| R-404 | `tests/unit/test_building_mortgage.py::test_build_needs_bank_stock`<br>`tests/golden/scenarios/g05_house_shortage.yaml` |
| R-405 | `tests/unit/test_building_mortgage.py::test_sell_evenly_half_price` |
| R-406 | `tests/unit/test_building_mortgage.py::test_hotel_sale_back_to_four_houses`<br>`tests/golden/scenarios/g06_hotel_selldown.yaml` |
| R-407 | `tests/unit/test_building_mortgage.py::test_demand_computation`<br>`tests/unit/test_building_mortgage.py::test_scarcity_no_bids_trigger_gets_house`<br>`tests/golden/scenarios/g05_house_shortage.yaml`<br>`tests/golden/scenarios/g18_scarcity_official_foreign.yaml` |
| R-501 | `tests/unit/test_building_mortgage.py::test_mortgage_payout_and_group_block` |
| R-502 | `tests/unit/test_building_mortgage.py::test_unmortgage_cost_rounded_up` |
| R-503 | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_cards_debt.py::test_bankruptcy_to_player_transfers_mortgaged_with_interest`<br>`tests/unit/test_cards_debt.py::test_creditor_cannot_pay_interest_cascade`<br>`tests/golden/scenarios/g04_mortgaged_transfer.yaml`<br>`tests/golden/scenarios/g07_bankruptcy_to_player.yaml` |
| R-601 | `tests/fuzz/test_fuzz.py::test_rare_event_fuzz`<br>`tests/unit/test_cards_debt.py::test_advance_to_with_salary`<br>`tests/unit/test_cards_debt.py::test_cycle_mask_resets_when_all_drawn`<br>`tests/unit/test_data.py::test_decks_match_spec` |
| R-602 | `tests/unit/test_cards_debt.py::test_advance_to_with_salary`<br>`tests/unit/test_cards_debt.py::test_advance_without_passing_start`<br>`tests/unit/test_cards_debt.py::test_advance_to_start` |
| R-603 | `tests/unit/test_cards_debt.py::test_nearest_rail_double_rent`<br>`tests/unit/test_cards_debt.py::test_nearest_rail_double_rent_counts_mortgaged_rails`<br>`tests/unit/test_cards_debt.py::test_nearest_rail_over_start_unowned_buy`<br>`tests/golden/scenarios/g10_nearest_rail.yaml` |
| R-604 | `tests/unit/test_cards_debt.py::test_nearest_util_new_roll_times_ten`<br>`tests/unit/test_cards_debt.py::test_nearest_util_over_start`<br>`tests/golden/scenarios/g11_nearest_util.yaml` |
| R-605 | `tests/unit/test_cards_debt.py::test_move_back_from_36_draws_deck_b`<br>`tests/unit/test_cards_debt.py::test_move_back_never_crosses_start`<br>`tests/golden/scenarios/g12_move_back_deck_b.yaml` |
| R-606 | `tests/unit/test_cards_debt.py::test_card_send_to_jail` |
| R-607 | `tests/unit/test_cards_debt.py::test_jail_free_card_kept`<br>`tests/unit/test_movement_jail.py::test_use_card_returns_it_under_deck`<br>`tests/golden/scenarios/g03_jail_card_to_creditor.yaml` |
| R-608 | `tests/unit/test_cards_debt.py::test_collect` |
| R-609 | `tests/unit/test_cards_debt.py::test_pay` |
| R-610 | `tests/unit/test_cards_debt.py::test_pay_each`<br>`tests/unit/test_cards_debt.py::test_pay_each_bankruptcy_counts_against_bank`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| R-611 | `tests/unit/test_cards_debt.py::test_collect_each` |
| R-612 | `tests/unit/test_cards_debt.py::test_repairs_hotel_counts_as_hotel`<br>`tests/unit/test_cards_debt.py::test_repairs_without_buildings_is_free`<br>`tests/golden/scenarios/g12_move_back_deck_b.yaml`<br>`tests/golden/scenarios/g13_repairs_hotels.yaml` |
| R-701 | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_cards_debt.py::test_debt_sell_buildings` |
| R-702 | `tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/unit/test_cards_debt.py::test_bankruptcy_to_player_transfers_mortgaged_with_interest`<br>`tests/unit/test_cards_debt.py::test_creditor_cannot_pay_interest_cascade`<br>`tests/golden/scenarios/g03_jail_card_to_creditor.yaml`<br>`tests/golden/scenarios/g07_bankruptcy_to_player.yaml` |
| R-703 | `tests/unit/test_cards_debt.py::test_bankruptcy_to_bank_auctions_unmortgaged`<br>`tests/golden/scenarios/g08_bankruptcy_to_bank.yaml`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| R-704 | `tests/unit/test_cards_debt.py::test_placements_reverse_bankruptcy_order`<br>`tests/unit/test_movement_jail.py::test_turn_order_skips_bankrupt` |
| R-705 | `tests/unit/test_cards_debt.py::test_bank_never_runs_out` |
| R-801 | `tests/unit/test_trade_flow.py::test_trade_cash_for_street`<br>`tests/unit/test_trade_flow.py::test_trade_rails_utilities_and_jail_cards`<br>`tests/unit/test_trade_flow.py::test_buildings_not_tradable`<br>`tests/golden/scenarios/g09_trade_jail_card.yaml` |
| R-802 | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_trade_flow.py::test_interest_affordability`<br>`tests/golden/scenarios/g04_mortgaged_transfer.yaml` |
| R-901 | `tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/unit/test_trade_flow.py::test_last_opponent_bankrupt_while_out_of_turn_windows_pending` |
| R-902 | `tests/unit/test_cards_debt.py::test_placements_reverse_bankruptcy_order` |
| P-01 | `tests/unit/test_movement_jail.py::test_doubles_roll_again_without_window`<br>`tests/unit/test_trade_flow.py::test_official_window_sequence` |
| P-02 | `tests/unit/test_trade_flow.py::test_offer_limits_and_validation`<br>`tests/unit/test_trade_flow.py::test_stale_second_offer_dropped`<br>`tests/unit/test_trade_flow.py::test_counter_offer_in_own_window` |
| P-03 | `tests/unit/test_purchase_rent.py::test_ascending_auction_rules`<br>`tests/unit/test_purchase_rent.py::test_ascending_auction_action_cap`<br>`tests/golden/scenarios/g16_official_auction_three_bidders.yaml` |
| P-04 | `tests/unit/test_purchase_rent.py::test_base_rent_and_double_with_group`<br>`tests/unit/test_purchase_rent.py::test_rent_paid_without_owner_decision` |
| P-05 | `tests/unit/test_building_mortgage.py::test_unmortgage_cost_rounded_up` |
| P-06 | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_cards_debt.py::test_automatic_bankruptcy_to_player`<br>`tests/golden/scenarios/g07_bankruptcy_to_player.yaml` |
| P-07 | `tests/unit/test_cards_debt.py::test_pay_each_bankruptcy_counts_against_bank`<br>`tests/golden/scenarios/g14_pay_each_bankruptcy.yaml` |
| P-08 | `tests/unit/test_building_mortgage.py::test_hotel_sale_without_houses_sells_group_down`<br>`tests/unit/test_building_mortgage.py::test_group_sold_down_to_zero`<br>`tests/golden/scenarios/g06_hotel_selldown.yaml` |
| P-09 | `tests/unit/test_purchase_rent.py::test_raise_money_before_buying` |
| P-10 | `tests/unit/test_movement_jail.py::test_seat_zero_starts` |
| P-11 | `tests/unit/test_cards_debt.py::test_nearest_rail_double_rent_counts_mortgaged_rails`<br>`tests/unit/test_purchase_rent.py::test_rail_rent`<br>`tests/golden/scenarios/g10_nearest_rail.yaml` |
| P-12 | `tests/unit/test_cards_debt.py::test_bankruptcy_to_bank_auctions_unmortgaged`<br>`tests/golden/scenarios/g08_bankruptcy_to_bank.yaml` |
| P-13 | `tests/unit/test_building_mortgage.py::test_received_mortgage_interest_and_principal_option`<br>`tests/unit/test_building_mortgage.py::test_principal_only_repayment`<br>`tests/golden/scenarios/g04_mortgaged_transfer.yaml` |
| P-14 | `tests/unit/test_trade_flow.py::test_buildings_not_tradable`<br>`tests/unit/test_trade_flow.py::test_offer_limits_and_validation`<br>`tests/unit/test_trade_flow.py::test_interest_affordability` |
| P-15 | `tests/unit/test_movement_jail.py::test_round_counter` |
| P-16 | `tests/unit/test_trade_flow.py::test_window_watchdog`<br>`tests/unit/test_trade_flow.py::test_turn_event_watchdog`<br>`tests/unit/test_trade_flow.py::test_game_decision_watchdog` |
| P-17 | `tests/unit/test_movement_jail.py::test_third_failure_debt_phase`<br>`tests/unit/test_movement_jail.py::test_third_failure_bankrupt_without_assets` |
| P-18 | `tests/unit/test_movement_jail.py::test_after_fine_normal_pre_roll`<br>`tests/unit/test_movement_jail.py::test_use_card_returns_it_under_deck` |
| P-19 | `tests/unit/test_building_mortgage.py::test_demand_computation`<br>`tests/unit/test_building_mortgage.py::test_scarcity_no_bids_trigger_gets_house`<br>`tests/unit/test_building_mortgage.py::test_scarcity_trigger_wins_pays_premium`<br>`tests/unit/test_building_mortgage.py::test_scarcity_foreign_bidder_places_in_own_group`<br>`tests/unit/test_building_mortgage.py::test_scarcity_bid_limited_by_house_price`<br>`tests/unit/test_building_mortgage.py::test_no_auction_without_second_interested_player`<br>`tests/unit/test_building_mortgage.py::test_hotel_scarcity`<br>`tests/unit/test_building_mortgage.py::test_scarcity_auction_in_out_of_turn_window`<br>`tests/golden/scenarios/g05_house_shortage.yaml`<br>`tests/golden/scenarios/g18_scarcity_official_foreign.yaml`<br>`tests/golden/scenarios/g19_scarcity_research_sealed.yaml` |
| K-01 | `tests/unit/test_cards_debt.py::test_debt_phase_liquidate_and_pay`<br>`tests/unit/test_trade_flow.py::test_no_trade_offer_during_debt` |
| K-02 | `tests/unit/test_purchase_rent.py::test_ascending_auction_rules`<br>`tests/unit/test_purchase_rent.py::test_sealed_levels_limited_by_cash` |
| K-03 | `tests/unit/test_building_mortgage.py::test_demand_computation` |
| K-04 | `tests/unit/test_building_mortgage.py::test_scarcity_auction_in_out_of_turn_window`<br>`tests/unit/test_trade_flow.py::test_counter_offer_in_own_window` |
| K-05 | `tests/unit/test_building_mortgage.py::test_scarcity_auction_disabled` |
| D-01 | `tests/unit/test_trade_flow.py::test_research_windows_and_offers` |
| D-02 | `tests/unit/test_purchase_rent.py::test_sealed_auction_second_price_plus_one`<br>`tests/unit/test_purchase_rent.py::test_sealed_auction_single_bid_price_one`<br>`tests/unit/test_purchase_rent.py::test_sealed_auction_tie_goes_to_decliner_order`<br>`tests/unit/test_purchase_rent.py::test_sealed_levels_limited_by_cash`<br>`tests/golden/scenarios/g17_research_auction_tie.yaml` |
| D-03 | `tests/unit/test_trade_flow.py::test_research_windows_and_offers` |
| D-04 | `tests/unit/test_data.py::test_research_is_two_player_only` |
| D-05 | `tests/unit/test_building_mortgage.py::test_scarcity_sealed_research`<br>`tests/unit/test_building_mortgage.py::test_scarcity_sealed_single_bid_premium_zero`<br>`tests/unit/test_building_mortgage.py::test_scarcity_sealed_tie_goes_to_trigger_order`<br>`tests/golden/scenarios/g19_scarcity_research_sealed.yaml` |
| D-06 | `tests/unit/test_trade_flow.py::test_short_game_ends_by_equity`<br>`tests/unit/test_trade_flow.py::test_short_game_tie_is_draw`<br>`tests/golden/scenarios/g15_shortgame_draw.yaml` |
| H-01 | `tests/unit/test_purchase_rent.py::test_rest_square_no_effect`<br>`tests/unit/test_trade_flow.py::test_no_money_pot_on_rest_square` |
| H-02 | `tests/unit/test_cards_debt.py::test_advance_to_start`<br>`tests/unit/test_trade_flow.py::test_landing_on_start_single_salary` |
| H-03 | `tests/unit/test_purchase_rent.py::test_decline_starts_auction_no_bids_bank_keeps` |
| H-04 | `tests/unit/test_building_mortgage.py::test_build_requires_complete_unmortgaged_group`<br>`tests/unit/test_building_mortgage.py::test_even_building` |
| H-05 | `tests/unit/test_trade_flow.py::test_offer_limits_and_validation` |
| H-06 | `tests/unit/test_trade_flow.py::test_trade_objects_have_no_immunity` |
| H-07 | `tests/unit/test_trade_flow.py::test_rent_collected_while_owner_in_jail` |
| H-08 | `tests/unit/test_trade_flow.py::test_standard_start_no_distribution` |
| H-09 | `tests/unit/test_trade_flow.py::test_official_has_no_round_limit` |

## Gate → Tests und Befehle

| Gate | Kriterium | Tests / Befehl |
|---|---|---|
| G0 | Artefaktsatz liegt vor | `tests/architecture/test_docs.py` |
| G1 | jede Regel-ID getestet | `tests/architecture/test_rule_coverage.py` |
| G1 | Fuzz ohne Invariantenverletzung | `tests/fuzz/test_fuzz.py` (CI 100.000 je Ruleset), `propertyrl fuzz --decisions 10000000` (Gate) |
| G1 | Markov | `tests/markov/test_markov.py` (CI 1 Mio., 0,15 pp), `propertyrl markov-check --moves 10000000 --tolerance-pp 0.05` (Gate) |
| G1 | alle Mutanten fallen | `tests/mutation/test_mutants_killed.py` |
| G1 | archivierte Replays identisch | `tests/determinism/test_archived_replays.py` |
| G1 | Coverage-Schwellen | `pytest --cov=propertyrl --cov-branch` + `propertyrl gates --gate G1` |
| G1 | Event-Coverage | `tests/fuzz/test_fuzz.py::test_event_coverage` |
| G1 | Golden Games | `tests/golden/test_golden.py` |
| G1 | Hypothesis | `tests/property/test_state_machine.py` |
| G2 | check_env (Gymnasium, SB3), api_test | `tests/env/test_env_api.py` |
| G2 | 0 illegale Aktionen | `tests/env/test_masks.py` (CI 100.000, Gate 1 Mio. via `PROPERTYRL_MASK_STEPS=1000000`) |
| G2 | SubprocVecEnv (spawn) | `tests/env/test_vecenv.py` |
| G2 | Mehrsitz-Äquivalenz | `tests/env/test_multiseat.py` |
| G2 | Durchsatz gemessen | `propertyrl benchmark` |
| G3–G8 | Pipeline | `tests/smoke/test_pipeline.py` (`propertyrl pipeline --smoke-all`) |
