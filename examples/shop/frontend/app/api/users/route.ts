import { AccountStatus } from "../../../lib/status";

// Cross-language scoping CONTROL (#15): the frontend AccountStatus union is a
// DIFFERENT closed set than the Python enum (it omits "pending_verification").
// This switch is exhaustive over the union AND has a default, so it must NOT be
// flagged for the Python enum's extra member.
export async function GET(request: Request) {
  const account: { status: AccountStatus } = await loadAccount(request);
  switch (account.status) {
    case "active":
      return Response.json(account);
    case "suspended":
      return new Response("blocked", { status: 403 });
    case "deleted":
      return new Response("gone", { status: 410 });
    default:
      return new Response("unknown", { status: 400 });
  }
}
