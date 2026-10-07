using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json.Nodes;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

public sealed class DiscoveryFileTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "pvsld-tests-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }

    [Fact]
    public void Write_StoresPipeSecretAndPid()
    {
        var directory = Path.Combine(_root, "bridge");
        var info = new DiscoveryInfo("pvsld-acad-1-abc", DiscoveryFile.NewSecret(), 1234, "server 0.2.0", "26.0");

        var path = DiscoveryFile.Write(directory, info);

        var json = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        Assert.Equal(DiscoveryFile.PathFor(directory, 1234), path);
        Assert.Equal(BridgeProtocol.Version, json["protocol"]!.GetValue<int>());
        Assert.Equal("pvsld-acad-1-abc", json["pipe"]!.GetValue<string>());
        Assert.Equal(info.Secret, json["secret"]!.GetValue<string>());
        Assert.Equal(1234, json["pid"]!.GetValue<int>());
        Assert.Empty(Directory.GetFiles(directory, "*.tmp"));

        DiscoveryFile.Delete(path);
        Assert.False(File.Exists(path));
    }

    [Fact]
    public void Write_OnWindows_FileAndDirectoryAreCurrentUserOnly()
    {
        if (!OperatingSystem.IsWindows())
        {
            return;
        }

        var directory = Path.Combine(_root, "bridge");
        var path = DiscoveryFile.Write(directory, new DiscoveryInfo("p", DiscoveryFile.NewSecret(), 5, "s", "v"));
        var user = CurrentUserSecurity.CurrentUser();

        foreach (var security in new FileSystemSecurity[]
                 {
                     new FileInfo(path).GetAccessControl(),
                     new DirectoryInfo(directory).GetAccessControl(),
                 })
        {
            var rules = security.GetAccessRules(true, true, typeof(SecurityIdentifier)).Cast<FileSystemAccessRule>().ToList();
            Assert.True(security.AreAccessRulesProtected);
            Assert.NotEmpty(rules);
            Assert.All(rules, r =>
            {
                Assert.Equal(AccessControlType.Allow, r.AccessControlType);
                Assert.Equal(user, r.IdentityReference);
            });
        }
    }

    [Fact]
    public void NewSecret_Is256BitUrlSafeAndUnique()
    {
        var a = DiscoveryFile.NewSecret();
        var b = DiscoveryFile.NewSecret();

        Assert.Equal(43, a.Length);
        Assert.Matches("^[A-Za-z0-9_-]+$", a);
        Assert.NotEqual(a, b);
    }

    [Fact]
    public void NewPipeName_IsUniquePerCall()
    {
        Assert.NotEqual(DiscoveryFile.NewPipeName(1), DiscoveryFile.NewPipeName(1));
        Assert.StartsWith("pvsld-acad-1-", DiscoveryFile.NewPipeName(1), StringComparison.Ordinal);
    }
}
