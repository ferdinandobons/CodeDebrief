package billing;

/** Settles payments through their lifecycle states. */
public class BillingService {

    public enum PaymentState {
        AUTHORIZED,
        CAPTURED,
        REFUNDED,
        FAILED
    }

    public String settle(PaymentState state, long amountCents) {
        switch (state) {
            case AUTHORIZED:
                return capture(amountCents);
            case CAPTURED:
                return "already_settled";
            case REFUNDED:
                return "refunded";
            case FAILED:
                return "retry_payment";
            default:
                return "manual_review";
        }
    }

    private String capture(long amountCents) {
        if (amountCents <= 0) {
            return "invalid_amount";
        }
        return "captured";
    }
}
