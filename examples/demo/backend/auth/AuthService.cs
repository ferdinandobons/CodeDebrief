namespace Auth;

public enum Role
{
    Admin,
    Member,
    Guest
}

public class AuthService
{
    public bool CanAccess(Role role, string resource)
    {
        switch (role)
        {
            case Role.Admin:
                return true;
            case Role.Member:
                return IsPublic(resource);
            case Role.Guest:
                return false;
            default:
                return false;
        }
    }

    private bool IsPublic(string resource)
    {
        return resource.StartsWith("public/");
    }
}
