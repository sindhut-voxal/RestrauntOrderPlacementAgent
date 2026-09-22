import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PipecatClient, RTVIEvent } from "@pipecat-ai/client-js";
import { PipecatClientAudio, PipecatClientProvider } from "@pipecat-ai/client-react";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import "./App.css";

type CartItem = {
  name: string;
  quantity: number;
  price: number;
  subtotal: number;
};

type Customer = {
  name?: string | null;
  phone?: string | null;
  fulfillment?: string | null;
  address?: string | null;
};

type Payment = {
  payment_id?: string;
  method?: string;
  last4?: string;
  amount?: number;
} | null;

type OrderUpdate = {
  event?: string;
  cart?: CartItem[];
  total?: number;
  status?: string;
  customer?: Customer;
  order_id?: string | null;
  payment?: Payment;
};

const EMPTY_ORDER: OrderUpdate = {
  cart: [],
  total: 0,
  status: "draft",
  customer: {},
  order_id: null,
  payment: null,
};

function botEndpoint(): string {
  return `${window.location.origin}/api/offer`;
}

function formatError(message: unknown): string {
  if (typeof message === "string") {
    return message;
  }
  if (message instanceof Error) {
    return message.message;
  }
  if (message && typeof message === "object") {
    const data = (message as { data?: unknown }).data;
    if (typeof data === "string") {
      return data;
    }
    if (data && typeof data === "object") {
      const nested = data as { error?: unknown; message?: unknown };
      if (typeof nested.error === "string") {
        return nested.error;
      }
      if (typeof nested.message === "string") {
        return nested.message;
      }
    }
    const top = message as { message?: unknown; error?: unknown };
    if (typeof top.message === "string") {
      return top.message;
    }
    if (typeof top.error === "string") {
      return top.error;
    }
    try {
      return JSON.stringify(message);
    } catch {
      return "Something went wrong";
    }
  }
  return "Something went wrong";
}

function asOrderUpdate(payload: unknown): OrderUpdate | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const record = payload as Record<string, unknown>;
  if (record.event === "order_update" || record.cart || record.status) {
    return record as OrderUpdate;
  }
  if (record.data && typeof record.data === "object") {
    return asOrderUpdate(record.data);
  }
  return null;
}

function statusLabel(status?: string): string {
  switch (status) {
    case "awaiting_payment":
      return "Awaiting mock payment";
    case "paid":
      return "Paid (mock)";
    case "confirmed":
      return "Confirmed";
    default:
      return "Draft";
  }
}

export default function App() {
  const clientRef = useRef<PipecatClient | null>(null);
  const [client, setClient] = useState<PipecatClient | null>(null);
  const [transportState, setTransportState] = useState("disconnected");
  const [error, setError] = useState<string | null>(null);
  const [order, setOrder] = useState<OrderUpdate>(EMPTY_ORDER);
  const [userSpeech, setUserSpeech] = useState("");
  const [botSpeech, setBotSpeech] = useState("");

  const connected = ["connected", "ready"].includes(transportState);

  const applyOrderUpdate = useCallback((payload: unknown) => {
    const next = asOrderUpdate(payload);
    if (!next) {
      return;
    }
    if (next.event && next.event !== "order_update") {
      return;
    }
    setOrder((prev) => ({
      cart: next.cart ?? prev.cart,
      total: next.total ?? prev.total,
      status: next.status ?? prev.status,
      customer: next.customer ?? prev.customer,
      order_id: next.order_id ?? prev.order_id,
      payment: next.payment ?? prev.payment,
    }));
  }, []);

  useEffect(() => {
    const client = new PipecatClient({
      transport: new SmallWebRTCTransport({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (state) => setTransportState(state),
        onDisconnected: () => setTransportState("disconnected"),
        onError: (message) => setError(formatError(message)),
        onServerMessage: (data) => applyOrderUpdate(data),
        onUserTranscript: (data) => {
          if (data.text) {
            setUserSpeech(data.text);
          }
        },
        onBotStartedSpeaking: () => setBotSpeech(""),
        onBotTtsStarted: () => setBotSpeech(""),
        onBotOutput: (data) => {
          if (data.text) {
            setBotSpeech(data.text);
          }
        },
        onBotTtsText: (data) => {
          if (data.text) {
            setBotSpeech((prev) => prev + data.text);
          }
        },
      },
    });

    clientRef.current = client;
    setClient(client);
    void client.initDevices();

    const onServerMessage = (data: unknown) => {
      applyOrderUpdate(data);
    };
    const onBotTtsText = (data: { text?: string }) => {
      if (data.text) {
        setBotSpeech((prev) => prev + data.text);
      }
    };
    client.on(RTVIEvent.ServerMessage, onServerMessage);
    client.on(RTVIEvent.BotTtsText, onBotTtsText);

    return () => {
      client.off(RTVIEvent.ServerMessage, onServerMessage);
      client.off(RTVIEvent.BotTtsText, onBotTtsText);
      void client.disconnect();
      clientRef.current = null;
      setClient(null);
    };
  }, [applyOrderUpdate]);

  useEffect(() => {
    if (!order.order_id || order.status !== "confirmed") {
      return;
    }
    const url = `/api/orders/${order.order_id}`;
    void fetch(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((payload) => {
        if (!payload) {
          return;
        }
        applyOrderUpdate({
          event: "order_update",
          cart: payload.items,
          total: payload.total,
          status: payload.status,
          customer: {
            name: payload.customer_name,
            phone: payload.phone,
            fulfillment: payload.fulfillment,
            address: payload.address,
          },
          order_id: payload.order_id,
          payment: payload.payment,
        });
      })
      .catch(() => undefined);
  }, [order.order_id, order.status, applyOrderUpdate]);

  const handleConnect = async () => {
    setError(null);
    setOrder(EMPTY_ORDER);
    try {
      await clientRef.current?.connect({
        webrtcUrl: botEndpoint(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect");
    }
  };

  const handleDisconnect = async () => {
    await clientRef.current?.disconnect();
  };

  const items = order.cart ?? [];
  const total = order.total ?? 0;
  const customer = order.customer ?? {};

  const fulfillmentSummary = useMemo(() => {
    if (!customer.fulfillment) {
      return "Not collected yet";
    }
    if (customer.fulfillment === "delivery") {
      return `Delivery${customer.address ? ` to ${customer.address}` : ""}`;
    }
    return "Pickup";
  }, [customer]);

  return (
    <div className="page">
      {client ? (
        <PipecatClientProvider client={client}>
          <PipecatClientAudio />
        </PipecatClientProvider>
      ) : null}
      <header>
        <div>
          <p className="eyebrow">Web ordering agent</p>
          <h1>Place your order by voice</h1>
        </div>
        <div className="call">
          <span className={`pill ${connected ? "on" : ""}`}>
            {connected ? "Live" : transportState}
          </span>
          {connected ? (
            <button className="danger" onClick={handleDisconnect}>
              Hang up
            </button>
          ) : (
            <button className="primary" onClick={handleConnect}>
              Start call
            </button>
          )}
        </div>
      </header>

      {error ? <p className="error">{error}</p> : null}

      <main>
        <section className="card">
          <h2>Cart</h2>
          {items.length === 0 ? (
            <p className="muted">Your cart is empty. Start the call and order out loud.</p>
          ) : (
            <ul className="cart">
              {items.map((item) => (
                <li key={item.name}>
                  <span>
                    {item.quantity} × {item.name}
                  </span>
                  <span>₹{item.subtotal}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="total">
            Total <strong>₹{total}</strong>
          </p>
        </section>

        <section className="card">
          <h2>Order status</h2>
          <dl>
            <div>
              <dt>Status</dt>
              <dd>{statusLabel(order.status)}</dd>
            </div>
            <div>
              <dt>Name</dt>
              <dd>{customer.name || "—"}</dd>
            </div>
            <div>
              <dt>Phone</dt>
              <dd>{customer.phone || "—"}</dd>
            </div>
            <div>
              <dt>Fulfillment</dt>
              <dd>{fulfillmentSummary}</dd>
            </div>
            <div>
              <dt>Mock payment</dt>
              <dd>
                {order.payment
                  ? `${order.payment.method} •••• ${order.payment.last4}`
                  : "Not charged"}
              </dd>
            </div>
            <div>
              <dt>Order ID</dt>
              <dd className="order-id">{order.order_id || "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="card transcript">
          <h2>Live conversation</h2>
          <p>
            <span className="muted">You:</span> {userSpeech || "…"}
          </p>
          <p>
            <span className="muted">Agent:</span> {botSpeech || "…"}
          </p>
        </section>
      </main>
    </div>
  );
}
