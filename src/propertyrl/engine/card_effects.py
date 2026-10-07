"""Card drawing and effects (R-601 to R-612, P-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from propertyrl.engine import cards as K
from propertyrl.engine import constants as C
from propertyrl.engine import frames as F
from propertyrl.engine.building import count_buildings
from propertyrl.engine.movement import move_back, next_forward

if TYPE_CHECKING:
    from propertyrl.engine.game import Engine


def draw_frame(eng: Engine, frame: tuple[int, ...]) -> None:
    """OP_DRAW: R-601 draw from the front; the card goes under the deck unless kept."""
    _, seat, deck_idx = frame
    state = eng.state
    if state.bankrupt[seat]:
        return
    deck = state.deck_a if deck_idx == C.DECK_A else state.deck_b
    card = deck.pop(0)
    mask = state.deck_cycle_drawn_a if deck_idx == C.DECK_A else state.deck_cycle_drawn_b
    mask |= 1 << card
    code = eng.decks.codes[deck_idx][card]
    params = eng.decks.params[deck_idx][card]
    if code == K.E_JAIL_FREE:
        # R-607: the jail-free card stays with the player until used or bankruptcy.
        state.jail_cards[seat] |= C.DECK_BITS[deck_idx]
    else:
        deck.append(card)
    # A new cycle starts once every card currently in the deck was drawn in this cycle.
    if all((mask >> c) & 1 for c in deck):
        mask = 0
    if deck_idx == C.DECK_A:
        state.deck_cycle_drawn_a = mask
    else:
        state.deck_cycle_drawn_b = mask
    card_id = eng.decks.deck(deck_idx)[card].card_id
    eng.emit("CARD_DRAWN", seat, {"deck": deck_idx, "card": card_id})
    apply_effect(eng, seat, code, params, card_id)


def apply_effect(eng: Engine, seat: int, code: int, params: tuple[int, ...], card_id: str) -> None:
    """Apply one card effect (R-602 to R-612)."""
    state = eng.state
    eng.emit("CARD_EFFECT", seat, {"card": card_id, "effect": K.EFFECT_TYPES[code], "params": list(params)})
    if code == K.E_ADVANCE_TO:
        # R-602 advance with salary when passing START.
        eng.push((F.OP_MOVE_TO, seat, params[0], F.LAND_NORMAL))
    elif code == K.E_NEAREST_RAIL:
        # R-603 nearest rail ahead; owned -> double rent.
        target = next_forward(state.position[seat], C.RAIL_SQUARES)
        eng.push((F.OP_MOVE_TO, seat, target, F.LAND_NEAREST_RAIL))
    elif code == K.E_NEAREST_UTIL:
        # R-604 nearest utility ahead; owned -> new roll x 10.
        target = next_forward(state.position[seat], C.UTIL_SQUARES)
        eng.push((F.OP_MOVE_TO, seat, target, F.LAND_NEAREST_UTIL))
    elif code == K.E_MOVE_BACK:
        # R-605 move back, never crossing START.
        move_back(eng, seat, params[0])
    elif code == K.E_SEND_TO_JAIL:
        # R-606
        eng.push((F.OP_SEND_JAIL, seat))
    elif code == K.E_JAIL_FREE:
        # R-607 handled when drawing (card kept).
        return
    elif code == K.E_COLLECT:
        # R-608
        eng.transfer(C.BANK, seat, params[0], "CARD")
    elif code == K.E_PAY:
        # R-609
        eng.push((F.OP_PAY, seat, C.BANK, params[0], F.R_CARD, 0))
    elif code == K.E_PAY_EACH:
        # R-610 / P-07: pay every active opponent in seat order; bankruptcy counts against the bank.
        n = state.n_players
        frames = [
            (F.OP_PAY, seat, (seat + k) % n, params[0], F.R_CARD_EACH, 1)
            for k in range(1, n)
            if not state.bankrupt[(seat + k) % n]
        ]
        for fr in reversed(frames):
            eng.push(fr)
    elif code == K.E_COLLECT_EACH:
        # R-611 every active opponent pays the drawer.
        n = state.n_players
        frames = [
            (F.OP_PAY, (seat + k) % n, seat, params[0], F.R_CARD_EACH, 0)
            for k in range(1, n)
            if not state.bankrupt[(seat + k) % n]
        ]
        for fr in reversed(frames):
            eng.push(fr)
    elif code == K.E_REPAIRS:
        # R-612 per house and per hotel (a hotel counts as hotel only).
        houses, hotels = count_buildings(state, seat)
        total = houses * params[0] + hotels * params[1]
        if total:
            eng.push((F.OP_PAY, seat, C.BANK, total, F.R_REPAIRS, 0))
