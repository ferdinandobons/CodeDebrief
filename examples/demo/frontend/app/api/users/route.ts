export async function POST(request: Request) {
  const user = await loadUser(request);

  switch (user.status) {
    case UserStatus.ACTIVE:
      return Response.json(user);
    case UserStatus.SUSPENDED:
      return new Response("Blocked", { status: 403 });
  }
}

async function loadUser(request: Request) {
  return database.users.find(request);
}
