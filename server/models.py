from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

Fulfillment = Literal["pickup", "delivery"]
OrderStatus = Literal["draft", "awaiting_payment", "paid", "confirmed"]


@dataclass
class CartItem:
    name: str
    quantity: int
    price: float

    @property
    def subtotal(self) -> float:
        return self.quantity * self.price

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "price": self.price,
            "subtotal": self.subtotal,
        }


@dataclass
class Payment:
    payment_id: str
    method: str = "mock"
    last4: str = "4242"
    amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Order:
    items: List[CartItem] = field(default_factory=list)
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    fulfillment: Optional[Fulfillment] = None
    address: Optional[str] = None
    status: OrderStatus = "draft"
    order_id: Optional[str] = None
    payment: Optional[Payment] = None

    @property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)

    def add_item(self, name: str, quantity: int, price: float) -> None:
        for item in self.items:
            if item.name.lower() == name.lower():
                item.quantity += quantity
                return

        self.items.append(
            CartItem(
                name=name,
                quantity=quantity,
                price=price,
            )
        )

    def remove_item(self, name: str, quantity: Optional[int] = None) -> bool:
        for item in self.items:
            if item.name.lower() != name.lower():
                continue

            if quantity is None or quantity >= item.quantity:
                self.items = [i for i in self.items if i is not item]
            else:
                item.quantity -= quantity
            return True

        return False

    def set_quantity(self, name: str, quantity: int) -> bool:
        if quantity <= 0:
            return self.remove_item(name)

        for item in self.items:
            if item.name.lower() == name.lower():
                item.quantity = quantity
                return True
        return False

    def clear(self) -> None:
        self.items.clear()

    def details_complete(self) -> bool:
        if not self.customer_name or not self.phone or not self.fulfillment:
            return False
        if self.fulfillment == "delivery" and not self.address:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "total": self.total,
            "customer_name": self.customer_name,
            "phone": self.phone,
            "fulfillment": self.fulfillment,
            "address": self.address,
            "status": self.status,
            "order_id": self.order_id,
            "payment": self.payment.to_dict() if self.payment else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        payment_data = data.get("payment")
        payment = Payment(**payment_data) if payment_data else None
        items = [
            CartItem(
                name=item["name"],
                quantity=item["quantity"],
                price=item["price"],
            )
            for item in data.get("items", [])
        ]
        return cls(
            items=items,
            customer_name=data.get("customer_name"),
            phone=data.get("phone"),
            fulfillment=data.get("fulfillment"),
            address=data.get("address"),
            status=data.get("status", "draft"),
            order_id=data.get("order_id"),
            payment=payment,
        )
