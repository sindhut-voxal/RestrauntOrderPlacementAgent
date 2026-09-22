from typing import Any, Optional

from loguru import logger

from models import Order


def order_ui_payload(order: Order) -> dict[str, Any]:
    snapshot = order.to_dict()
    return {
        "event": "order_update",
        "cart": snapshot["items"],
        "total": snapshot["total"],
        "status": snapshot["status"],
        "customer": {
            "name": snapshot["customer_name"],
            "phone": snapshot["phone"],
            "fulfillment": snapshot["fulfillment"],
            "address": snapshot["address"],
        },
        "order_id": snapshot["order_id"],
        "payment": snapshot["payment"],
    }


async def push_order_ui(rtvi, order: Order) -> None:
    if rtvi is None:
        return

    try:
        await rtvi.send_server_message(order_ui_payload(order))
    except Exception as exc:
        logger.warning(f"Failed to push order UI: {exc}")


async def push_order_from_state(flow_manager) -> Optional[Order]:
    order = flow_manager.state.get("order")
    if not isinstance(order, Order):
        return None

    await push_order_ui(flow_manager.state.get("rtvi"), order)
    return order
