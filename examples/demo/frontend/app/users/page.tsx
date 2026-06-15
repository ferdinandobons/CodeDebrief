export default function UsersPage({ user }: Props) {
  if (!user.isAuthorized) {
    return <LoginPrompt />;
  }

  return <UserDashboard user={user} />;
}
