"use server";

// Planted: the catch block swallows the failure (broad_except_swallow).
export async function processCheckout(request: Request) {
  try {
    return await charge(request);
  } catch (error) {
    // intentionally ignored
  }
  return new Response("ok");
}
