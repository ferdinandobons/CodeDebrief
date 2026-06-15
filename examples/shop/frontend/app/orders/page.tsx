// Planted: an if / else-if chain on order.status with no final else (missing_branch).
export default function OrdersPage({ order }: { order: { status: string } }) {
  if (order.status === "cart") {
    return <CartView />;
  } else if (order.status === "paid") {
    return <PaidView />;
  }
}
