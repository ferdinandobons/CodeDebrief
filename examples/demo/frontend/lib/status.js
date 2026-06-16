// Human-readable label for a user status. Unlike the API route, this helper
// handles every status including "deleted", so it never falls through.
export function statusLabel(status) {
  switch (status) {
    case "active":
      return "Active";
    case "suspended":
      return "Suspended";
    case "deleted":
      return "Deleted";
    default:
      return "Unknown";
  }
}
