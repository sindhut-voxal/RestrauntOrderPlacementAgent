import re
import uuid
from difflib import get_close_matches
from typing import Optional

from models import Order, Payment
from order_store import save_order

MENU = {
    "veg burger": {
        "price": 120,
        "description": "Vegetarian burger with fresh vegetables",
    },
    "french fries": {
        "price": 80,
        "description": "Crispy salted french fries",
    },
    "coke": {
        "price": 50,
        "description": "Chilled Coca-Cola",
    },
    "pizza": {
        "price": 250,
        "description": "Medium vegetable pizza",
    },
}

MENU_ALIASES = {
    "burger": "veg burger",
    "veggie burger": "veg burger",
    "hamburger": "veg burger",
    "fries": "french fries",
    "french fry": "french fries",
    "cola": "coke",
    "coca cola": "coke",
    "coke cola": "coke",
    "soda": "coke",
    "soft drink": "coke",
}

MENU_KEYTERMS = list(MENU.keys()) + list(MENU_ALIASES.keys())


def _menu_item_dict(name: str) -> dict:
    item = MENU[name]
    return {
        "name": name,
        "price": item["price"],
        "description": item["description"],
    }


def resolve_menu_item(query: str) -> Optional[str]:
    query = (query or "").lower().strip()
    if not query:
        return None

    if query in MENU:
        return query

    if query in MENU_ALIASES:
        return MENU_ALIASES[query]

    substring_hits = [name for name in MENU if query in name or name in query]
    if len(substring_hits) == 1:
        return substring_hits[0]
    if substring_hits:
        return substring_hits[0]

    close = get_close_matches(query, list(MENU.keys()) + list(MENU_ALIASES.keys()), n=1, cutoff=0.72)
    if not close:
        return None

    match = close[0]
    return MENU_ALIASES.get(match, match)


def _all_menu_items():
    return [_menu_item_dict(name) for name in MENU]


BROWSE_QUERIES = {
    "",
    "food",
    "menu",
    "all",
    "everything",
    "items",
    "eat",
    "options",
    "dishes",
}

BROWSE_PHRASES = (
    "what do you have",
    "what's on the menu",
    "whats on the menu",
    "what is on the menu",
)


def search_menu(query: str):
    query = (query or "").lower().strip()
    available = _all_menu_items()

    if query in BROWSE_QUERIES or any(phrase in query for phrase in BROWSE_PHRASES):
        return {"results": available, "available": available}

    resolved = resolve_menu_item(query)
    results = []
    seen = set()

    if resolved:
        results.append(_menu_item_dict(resolved))
        seen.add(resolved)

    for name, item in MENU.items():
        if name in seen:
            continue
        if query in name or query in item["description"].lower():
            results.append(_menu_item_dict(name))
            seen.add(name)

    if not results:
        return {
            "results": [],
            "available": available,
            "message": "No exact match. Offer only items from available.",
        }

    return {"results": results}


def add_to_cart(order: Order, item_name: str, quantity: int):
    resolved = resolve_menu_item(item_name)
    if not resolved:
        return {
            "success": False,
            "message": f"{item_name} is not available.",
        }

    if quantity <= 0:
        return {
            "success": False,
            "message": "Quantity must be greater than zero.",
        }

    order.add_item(
        name=resolved,
        quantity=quantity,
        price=MENU[resolved]["price"],
    )

    return {
        "success": True,
        "message": f"Added {quantity} {resolved} to the cart.",
        "cart": get_cart(order),
    }


def remove_from_cart(order: Order, item_name: str, quantity: Optional[int] = None):
    resolved = resolve_menu_item(item_name) or (item_name or "").lower().strip()
    removed = order.remove_item(resolved, quantity=quantity)

    if not removed:
        return {
            "success": False,
            "message": f"{item_name} is not in the cart.",
            "cart": get_cart(order),
        }

    if quantity is None:
        message = f"Removed {resolved} from the cart."
    else:
        message = f"Removed {quantity} {resolved} from the cart."

    return {
        "success": True,
        "message": message,
        "cart": get_cart(order),
    }


def update_quantity(order: Order, item_name: str, quantity: int):
    resolved = resolve_menu_item(item_name)
    if not resolved:
        return {
            "success": False,
            "message": f"{item_name} is not available.",
        }

    if quantity <= 0:
        return remove_from_cart(order, resolved)

    if not order.set_quantity(resolved, quantity):
        return add_to_cart(order, resolved, quantity)

    return {
        "success": True,
        "message": f"Updated {resolved} quantity to {quantity}.",
        "cart": get_cart(order),
    }


def get_cart(order: Order):
    return {
        "items": [item.to_dict() for item in order.items],
        "total": order.total,
        "status": order.status,
    }


def ensure_cart_not_empty(order: Order):
    if not order.items:
        return {
            "success": False,
            "message": "The cart is empty. Add at least one item first.",
        }
    return None


def set_customer_details(
    order: Order,
    name: str,
    phone: str,
    fulfillment: str,
    address: Optional[str] = None,
):
    empty = ensure_cart_not_empty(order)
    if empty:
        return empty

    name = (name or "").strip()
    phone_digits = re.sub(r"\D", "", phone or "")
    fulfillment = (fulfillment or "").lower().strip()
    address = (address or "").strip() or None

    if not name:
        return {"success": False, "message": "A name is required."}

    if len(phone_digits) < 10 or len(phone_digits) > 15:
        return {
            "success": False,
            "message": "Please provide a valid phone number with 10 to 15 digits.",
        }

    if fulfillment not in ("pickup", "delivery"):
        return {
            "success": False,
            "message": "Fulfillment must be pickup or delivery.",
        }

    if fulfillment == "delivery" and not address:
        return {
            "success": False,
            "message": "An address is required for delivery.",
        }

    order.customer_name = name
    order.phone = phone_digits
    order.fulfillment = fulfillment
    order.address = address if fulfillment == "delivery" else None
    order.status = "awaiting_payment"

    return {
        "success": True,
        "message": "Saved customer details.",
        "details": {
            "customer_name": order.customer_name,
            "phone": order.phone,
            "fulfillment": order.fulfillment,
            "address": order.address,
        },
    }


def charge_mock_payment(order: Order):
    empty = ensure_cart_not_empty(order)
    if empty:
        return empty

    if not order.details_complete():
        return {
            "success": False,
            "message": "Collect name, phone, and pickup or delivery details before payment.",
        }

    order.payment = Payment(
        payment_id=f"pay_{uuid.uuid4().hex[:10]}",
        method="mock",
        last4="4242",
        amount=order.total,
    )
    order.status = "paid"

    return {
        "success": True,
        "message": f"Mock payment of {order.total} succeeded.",
        "payment": order.payment.to_dict(),
    }


def confirm_order(order: Order):
    empty = ensure_cart_not_empty(order)
    if empty:
        return empty

    if not order.details_complete():
        return {
            "success": False,
            "message": "Customer details are incomplete.",
        }

    if order.status != "paid" or not order.payment:
        return {
            "success": False,
            "message": "Payment is required before confirming the order.",
        }

    if not order.order_id:
        order.order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    order.status = "confirmed"
    save_order(order)

    return {
        "success": True,
        "message": f"Order {order.order_id} is confirmed.",
        "order": order.to_dict(),
    }
