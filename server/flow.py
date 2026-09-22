from pipecat_flows import FlowManager, FlowsFunctionSchema, NodeConfig

from tools import (
    add_to_cart,
    charge_mock_payment,
    confirm_order,
    get_cart,
    remove_from_cart,
    search_menu,
    set_customer_details,
    update_quantity,
)
from ui_sync import push_order_from_state

ROLE_MESSAGE = (
    "You are a friendly restaurant voice ordering assistant. "
    "Keep replies short and natural. Never invent menu items or prices. "
    "Use tools for menu, cart, customer details, payment, and confirmation."
)


async def _push(flow_manager: FlowManager):
    await push_order_from_state(flow_manager)


def create_start_order_function():
    async def handler(args, flow_manager: FlowManager):
        await flow_manager.set_node_from_config(create_take_order_node())
        return {"success": True, "message": "Ready to take the customer's order."}

    return FlowsFunctionSchema(
        name="start_order",
        description="Start taking the customer's food order.",
        properties={},
        required=[],
        handler=handler,
    )


def create_review_function():
    async def handler(args, flow_manager: FlowManager):
        order = flow_manager.state["order"]
        cart = get_cart(order)
        if not cart["items"]:
            return {
                "success": False,
                "message": "The cart is empty. Add at least one item before reviewing.",
            }

        await flow_manager.set_node_from_config(create_review_order_node())
        return {"success": True, "message": "The order is ready to be reviewed.", "cart": cart}

    return FlowsFunctionSchema(
        name="review_order",
        description="Finish taking the order and review the customer's cart.",
        properties={},
        required=[],
        handler=handler,
    )


def create_change_order_function():
    async def handler(args, flow_manager: FlowManager):
        await flow_manager.set_node_from_config(create_take_order_node())
        return {"success": True, "message": "Ready to make changes to the order."}

    return FlowsFunctionSchema(
        name="change_order",
        description="Go back so the customer can change cart items.",
        properties={},
        required=[],
        handler=handler,
    )


def create_collect_details_function():
    async def handler(args, flow_manager: FlowManager):
        order = flow_manager.state["order"]
        cart = get_cart(order)
        if not cart["items"]:
            return {
                "success": False,
                "message": "The cart is empty. Add items before collecting details.",
            }

        await flow_manager.set_node_from_config(create_collect_details_node())
        return {"success": True, "message": "Ready to collect pickup or delivery details."}

    return FlowsFunctionSchema(
        name="collect_details",
        description="Customer confirmed the cart. Collect name, phone, and pickup or delivery details.",
        properties={},
        required=[],
        handler=handler,
    )


def _cart_functions():
    async def handle_search(args, flow_manager: FlowManager):
        return {"results": search_menu(args["query"])}

    async def handle_add(args, flow_manager: FlowManager):
        result = add_to_cart(
            flow_manager.state["order"],
            args["item_name"],
            args["quantity"],
        )
        await _push(flow_manager)
        return result

    async def handle_remove(args, flow_manager: FlowManager):
        result = remove_from_cart(
            flow_manager.state["order"],
            args["item_name"],
            args.get("quantity"),
        )
        await _push(flow_manager)
        return result

    async def handle_update(args, flow_manager: FlowManager):
        result = update_quantity(
            flow_manager.state["order"],
            args["item_name"],
            args["quantity"],
        )
        await _push(flow_manager)
        return result

    async def handle_view(args, flow_manager: FlowManager):
        return get_cart(flow_manager.state["order"])

    return [
        FlowsFunctionSchema(
            name="search_menu",
            description="Search the food menu for matching items.",
            properties={
                "query": {
                    "type": "string",
                    "description": "Food item or keyword to search for.",
                }
            },
            required=["query"],
            handler=handle_search,
        ),
        FlowsFunctionSchema(
            name="add_to_cart",
            description="Add a food item to the customer's cart.",
            properties={
                "item_name": {
                    "type": "string",
                    "description": "Name of the food item.",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Quantity of the item.",
                },
            },
            required=["item_name", "quantity"],
            handler=handle_add,
        ),
        FlowsFunctionSchema(
            name="remove_from_cart",
            description="Remove an item or quantity from the cart.",
            properties={
                "item_name": {
                    "type": "string",
                    "description": "Name of the food item to remove.",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Optional quantity to remove. Omit to remove the whole line.",
                },
            },
            required=["item_name"],
            handler=handle_remove,
        ),
        FlowsFunctionSchema(
            name="update_quantity",
            description="Set the quantity of an item already in the cart, or add it if missing.",
            properties={
                "item_name": {
                    "type": "string",
                    "description": "Name of the food item.",
                },
                "quantity": {
                    "type": "integer",
                    "description": "New quantity. Zero removes the item.",
                },
            },
            required=["item_name", "quantity"],
            handler=handle_update,
        ),
        FlowsFunctionSchema(
            name="view_cart",
            description="View the customer's current cart.",
            properties={},
            required=[],
            handler=handle_view,
        ),
    ]


def create_welcome_node() -> NodeConfig:
    return {
        "name": "welcome",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Welcome the customer and ask what they would like to order. "
                    "When they are ready, use start_order."
                ),
            }
        ],
        "functions": [create_start_order_function()],
        "pre_actions": [
            {
                "type": "tts_say",
                "text": "Hi! Welcome in. What can I get started for you today?",
            }
        ],
    }


def create_take_order_node() -> NodeConfig:
    return {
        "name": "take_order",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Take the customer's food order. Use search_menu if you are unsure "
                    "an item exists. Ask for quantity if needed. After adding an item, "
                    "acknowledge it and ask if they want anything else. "
                    "When they are finished, use review_order. "
                    "Do not collect address or payment yet."
                ),
            }
        ],
        "functions": [
            *_cart_functions(),
            create_review_function(),
        ],
    }


def create_review_order_node() -> NodeConfig:
    async def handle_view(args, flow_manager: FlowManager):
        return get_cart(flow_manager.state["order"])

    return {
        "name": "review_order",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "First use view_cart. Read back each item, quantity, price, and total. "
                    "Ask if everything is correct. If they want changes, use change_order. "
                    "If they confirm, use collect_details. Do not collect payment yet."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="view_cart",
                description="View the customer's current cart.",
                properties={},
                required=[],
                handler=handle_view,
            ),
            create_change_order_function(),
            create_collect_details_function(),
        ],
    }


def create_collect_details_node() -> NodeConfig:
    async def handle_details(args, flow_manager: FlowManager):
        result = set_customer_details(
            flow_manager.state["order"],
            args["name"],
            args["phone"],
            args["fulfillment"],
            args.get("address"),
        )
        await _push(flow_manager)
        if result.get("success"):
            await flow_manager.set_node_from_config(create_mock_payment_node())
        return result

    return {
        "name": "collect_details",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Collect the customer's name, phone number, and whether this is "
                    "pickup or delivery. If delivery, also collect an address. "
                    "When you have everything, call set_customer_details."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="set_customer_details",
                description="Save name, phone, and pickup or delivery details.",
                properties={
                    "name": {"type": "string", "description": "Customer name."},
                    "phone": {"type": "string", "description": "Customer phone number."},
                    "fulfillment": {
                        "type": "string",
                        "enum": ["pickup", "delivery"],
                        "description": "pickup or delivery.",
                    },
                    "address": {
                        "type": "string",
                        "description": "Delivery address. Required for delivery.",
                    },
                },
                required=["name", "phone", "fulfillment"],
                handler=handle_details,
            ),
            create_change_order_function(),
        ],
    }


def create_mock_payment_node() -> NodeConfig:
    async def handle_charge(args, flow_manager: FlowManager):
        result = charge_mock_payment(flow_manager.state["order"])
        await _push(flow_manager)
        if not result.get("success"):
            return result

        confirmed = confirm_order(flow_manager.state["order"])
        await _push(flow_manager)
        if confirmed.get("success"):
            await flow_manager.set_node_from_config(
                create_confirmed_node(flow_manager.state["order"])
            )
        return confirmed

    return {
        "name": "mock_payment",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    "Tell the customer the total and that you will place a mock payment. "
                    "When they agree, call charge_mock_payment. This is not a real card charge."
                ),
            }
        ],
        "functions": [
            FlowsFunctionSchema(
                name="charge_mock_payment",
                description="Charge a mock payment for the current cart total and confirm the order.",
                properties={},
                required=[],
                handler=handle_charge,
            ),
            create_change_order_function(),
        ],
    }


def create_confirmed_node(order) -> NodeConfig:
    fulfillment = order.fulfillment or "pickup"
    destination = (
        f"delivered to {order.address}"
        if fulfillment == "delivery"
        else "ready for pickup"
    )
    goodbye = (
        f"Your order {order.order_id} is confirmed. "
        f"It will be {destination}. Thanks for ordering. Enjoy your meal!"
    )
    return {
        "name": "confirmed",
        "role_message": ROLE_MESSAGE,
        "task_messages": [
            {
                "role": "system",
                "content": (
                    f"The order {order.order_id} is already confirmed and spoken. "
                    "Do not take more items."
                ),
            }
        ],
        "functions": [],
        "respond_immediately": False,
        "pre_actions": [{"type": "tts_say", "text": goodbye}],
        "post_actions": [{"type": "end_conversation"}],
    }
