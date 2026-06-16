import { database, Order } from "../../../lib/db";

export async function GET(request: Request): Promise<Response> {
  const order = await loadOrder(request);

  switch (order.state) {
    case "open":
      return Response.json(order);
    case "paid":
      return Response.json(order);
    case "closed":
      return new Response("Closed", { status: 410 });
    default:
      return new Response("Bad state", { status: 400 });
  }
}

async function loadOrder(request: Request): Promise<Order> {
  return database.orders.find(request);
}
