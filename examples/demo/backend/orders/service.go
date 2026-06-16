// Package orders models the order lifecycle for the demo backend.
package orders

type Status string

const (
	StatusPending   Status = "pending"
	StatusPaid      Status = "paid"
	StatusShipped   Status = "shipped"
	StatusDelivered Status = "delivered"
	StatusCancelled Status = "cancelled"
)

type Order struct {
	ID     string
	Status Status
}

// NextAction returns the operational step for an order's current status.
func (o *Order) NextAction() string {
	switch o.Status {
	case StatusPending:
		return "await_payment"
	case StatusPaid:
		return "schedule_shipment"
	case StatusShipped:
		return "track_delivery"
	case StatusDelivered:
		return "request_review"
	case StatusCancelled:
		return "issue_refund"
	default:
		return "manual_review"
	}
}

// CanFulfill reports whether a paid order can ship given current stock.
func (o *Order) CanFulfill(stockAvailable bool) bool {
	if o.Status != StatusPaid {
		return false
	}
	if !stockAvailable {
		return false
	}
	return true
}
