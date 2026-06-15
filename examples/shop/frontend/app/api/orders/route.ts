import { OrderStatus } from "../../../lib/status";

// Planted: a switch on order.status with no `default` (missing_branch).
export async function POST(request: Request) {
  const order: { status: OrderStatus } = await loadOrder(request);
  switch (order.status) {
    case "cart":
      return Response.json({ stage: "cart" });
    case "paid":
      return Response.json({ stage: "paid" });
    case "shipped":
      return Response.json({ stage: "shipped" });
  }
}
