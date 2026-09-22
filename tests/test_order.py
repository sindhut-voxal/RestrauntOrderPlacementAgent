from models import Order
from order_store import get_order, save_order
from tools import (
    add_to_cart,
    charge_mock_payment,
    confirm_order,
    remove_from_cart,
    search_menu,
    set_customer_details,
    update_quantity,
)


def test_search_browse_returns_full_menu():
    for query in ("", "food", "all", "menu", "what do you have"):
        payload = search_menu(query)
        names = {item["name"] for item in payload["results"]}
        assert names == {"veg burger", "french fries", "coke", "pizza"}


def test_search_unknown_includes_available():
    payload = search_menu("tacos")
    assert payload["results"] == []
    assert {item["name"] for item in payload["available"]} == {
        "veg burger",
        "french fries",
        "coke",
        "pizza",
    }


def test_search_aliases_and_fuzzy():
    fries = search_menu("fries")["results"]
    assert fries and fries[0]["name"] == "french fries"
    cola = search_menu("cola")["results"]
    assert cola and cola[0]["name"] == "coke"
    burger = search_menu("veggie burger")["results"]
    assert burger and burger[0]["name"] == "veg burger"


def test_add_and_remove_quantity():
    order = Order()
    added = add_to_cart(order, "coke", 3)
    assert added["success"] is True
    assert order.items[0].quantity == 3

    partial = remove_from_cart(order, "coke", 1)
    assert partial["success"] is True
    assert order.items[0].quantity == 2

    missing = remove_from_cart(order, "pizza")
    assert missing["success"] is False


def test_update_quantity_and_empty_cart_guards():
    order = Order()
    empty_pay = charge_mock_payment(order)
    assert empty_pay["success"] is False

    add_to_cart(order, "pizza", 1)
    updated = update_quantity(order, "pizza", 2)
    assert updated["success"] is True
    assert order.items[0].quantity == 2


def test_delivery_requires_address():
    order = Order()
    add_to_cart(order, "coke", 1)
    result = set_customer_details(
        order,
        "Alex",
        "9876543210",
        "delivery",
    )
    assert result["success"] is False

    ok = set_customer_details(
        order,
        "Alex",
        "9876543210",
        "delivery",
        "12 Main Street",
    )
    assert ok["success"] is True
    assert order.status == "awaiting_payment"


def test_mock_payment_and_sqlite_confirm(tmp_path, monkeypatch):
    import order_store

    monkeypatch.setattr(order_store, "DB_PATH", tmp_path / "orders.db")

    order = Order()
    add_to_cart(order, "veg burger", 1)
    set_customer_details(order, "Alex", "9876543210", "pickup")
    charged = charge_mock_payment(order)
    assert charged["success"] is True
    assert order.payment is not None
    assert order.payment.last4 == "4242"

    confirmed = confirm_order(order)
    assert confirmed["success"] is True
    assert order.order_id
    save_order(order)
    stored = get_order(order.order_id)
    assert stored is not None
    assert stored["status"] == "confirmed"
    assert stored["total"] == 120
