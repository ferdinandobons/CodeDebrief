# examples/shop — expected findings

A worked corpus: a small shop backend (Python) + frontend (Next.js/TS) with
**planted defects** and **controls**, used to validate LogicChart end-to-end and
to be candid about what the current detectors catch and miss. Regenerate with
`logicchart analyze examples/shop`.

## True positives (13 findings)

| Detector | Flow | Where | Planted |
|---|---|---|---|
| `dead_code` | `load_profile` | `backend/users_service.py` | #9 code after `return` |
| `missing_branch` | `transition` | `backend/orders_service.py` | #4 `match` with no default |
| `enum_exhaustiveness` | `transition` | `backend/orders_service.py` | #4 omits CANCELLED/DELIVERED/REFUNDED |
| `no_op_branch` | `summarize` | `backend/orders_service.py` | #10 empty refunded branch |
| `missing_branch` | `handle_result` | `backend/payments_service.py` | #5 if/elif with no else |
| `enum_exhaustiveness` | `handle_result` | `backend/payments_service.py` | #5 omits PaymentResult.FRAUD_REVIEW |
| `broad_except_swallow` | `charge` | `backend/payments_service.py` | #6 `except: pass` |
| `logging_asymmetry` | `capture_payment` | `backend/payments_service.py` | #14 silent where `refund_payment` logs |
| `missing_branch` | `change_email` | `backend/api/users_routes.py` | #3 if/elif with no else |
| `enum_exhaustiveness` | `change_email` | `backend/api/users_routes.py` | #3 omits AccountStatus ACTIVE/PENDING_VERIFICATION |
| `missing_branch` | `POST` | `frontend/app/api/orders/route.ts` | `switch` with no default |
| `missing_branch` | `OrdersPage` | `frontend/app/orders/page.tsx` | if/else-if with no else |
| `broad_except_swallow` | `processCheckout` | `frontend/app/api/checkout/route.ts` | empty `catch` |

A state-like dispatch with no fallback fires **both** `missing_branch` (no
else/default) and `enum_exhaustiveness` (the specific missing declared members);
the latter is the more actionable signal. Deduplicating the pair is a candidate
refinement.

## Controls that correctly stay silent

- `authenticate` (`users_service.py`) — handles every AccountStatus and has a final `else`.
- `GET` (`frontend/app/api/users/route.ts`) — **cross-language scoping (#15)**: the frontend
  `AccountStatus` union is a *different* closed set than the Python enum (no
  `pending_verification`); the switch is exhaustive over the union and has a default, so it is
  **not** flagged against the Python enum's extra member.
- `AccountPage` (`account/page.tsx`), `middleware.ts` — a switch with a default and a lone auth
  guard, respectively.
- `reset_password`, `get_profile` (`users_routes.py`) — single-value guards (handling one member is
  a guard, not an exhaustive dispatch, so below the ≥2 threshold).
- `cancel`, `request_refund` (`orders_routes.py`) — `not in {...}` allow-list guards are excluded
  from the positive-dispatch detectors.

## Planted defects not yet caught (deferred, with reason)

- **#2** `reset_password` omits DELETED/PENDING — a single-value guard, intentionally not flagged to
  keep false positives low.
- **#7/#8** `cancel` (404) vs `request_refund` (409) divergent refundable set and status code — both
  are `not in` guards over *different* sets, so they share no `(subject, value)`; needs a future
  guard-set-divergence / default-semantic detector.
- **#11** `ENABLE_DOUBLE_CHARGE_GUARD` always-false guard — the always-true/false-guard detector is a
  later single-flow increment.
- **#12** `purge_user` missing the `require_role` gate its sibling `delete_user` has — the
  authorization-divergence detector is **Stage 7** (gated, after the call-resolver + auth lexicon).
- **#13** `quick_order` missing the validation `create` has — the validation-divergence detector is
  **Stage 7** (gated).
