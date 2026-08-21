from aqt import mw
from aqt.utils import tooltip
from ..core.deck_utils import move_card_to_deck

def move_current_card(deck_name: str):
    if not mw or mw.state != "review" or not mw.reviewer or not mw.reviewer.card or not deck_name:
        tooltip("No card active.", period=1000)
        return
    card = mw.reviewer.card
    actual = move_card_to_deck(card.id, deck_name)
    tooltip(f"Moved -> {actual}", period=1000)
    mw.reviewer.nextCard()