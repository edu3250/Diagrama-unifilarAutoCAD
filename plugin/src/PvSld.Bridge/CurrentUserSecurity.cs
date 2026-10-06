using System.IO.Pipes;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;

namespace PvSld.Bridge;

/// <summary>Security descriptors that admit only the current Windows user.</summary>
[SupportedOSPlatform("windows")]
public static class CurrentUserSecurity
{
    public static SecurityIdentifier CurrentUser()
    {
        using var identity = WindowsIdentity.GetCurrent();
        return identity.User ?? throw new InvalidOperationException("the current token has no user SID");
    }

    /// <summary>
    /// Protected DACL: deny the NETWORK logon group (no remote clients even with the same account),
    /// allow the current user full control; nothing is inherited, so no other principal has access.
    /// </summary>
    public static PipeSecurity Pipe()
    {
        var user = CurrentUser();
        var security = new PipeSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(user);
        security.AddAccessRule(new PipeAccessRule(
            new SecurityIdentifier(WellKnownSidType.NetworkSid, null),
            PipeAccessRights.FullControl,
            AccessControlType.Deny));
        security.AddAccessRule(new PipeAccessRule(user, PipeAccessRights.FullControl, AccessControlType.Allow));
        return security;
    }

    /// <summary>Protected DACL with a single allow rule for the current user.</summary>
    public static FileSecurity File()
    {
        var user = CurrentUser();
        var security = new FileSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(user);
        security.AddAccessRule(new FileSystemAccessRule(user, FileSystemRights.FullControl, AccessControlType.Allow));
        return security;
    }

    /// <summary>Protected DACL with a single inheritable allow rule for the current user.</summary>
    public static DirectorySecurity Directory()
    {
        var user = CurrentUser();
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(user);
        security.AddAccessRule(new FileSystemAccessRule(
            user,
            FileSystemRights.FullControl,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None,
            AccessControlType.Allow));
        return security;
    }
}
