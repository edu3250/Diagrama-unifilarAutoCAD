using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace PvSld.Bridge;

/// <summary>What a client needs to reach a running bridge (written once per AutoCAD start).</summary>
public sealed record DiscoveryInfo(string PipeName, string Secret, int Pid, string Server, string HostVersion)
{
    public JsonObject ToJson() => new()
    {
        ["protocol"] = BridgeProtocol.Version,
        ["pipe"] = PipeName,
        ["secret"] = Secret,
        ["pid"] = Pid,
        ["server"] = Server,
        ["host_version"] = HostVersion,
        ["started_utc"] = DateTime.UtcNow.ToString("O", System.Globalization.CultureInfo.InvariantCulture),
    };
}

/// <summary>
/// Writes the per-start secret to <c>%LOCALAPPDATA%\pvsld\bridge\autocad-&lt;pid&gt;.json</c>. The
/// directory and the file carry a protected DACL for the current user only, so other accounts
/// cannot read the secret.
/// </summary>
public static class DiscoveryFile
{
    public static string DefaultDirectory =>
        Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "pvsld",
            "bridge");

    public static string PathFor(string directory, int pid) => Path.Combine(directory, $"autocad-{pid}.json");

    /// <summary>256 random bits, base64url without padding.</summary>
    public static string NewSecret() =>
        Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');

    /// <summary>A pipe name that is unique per start, so another process cannot pre-create it.</summary>
    public static string NewPipeName(int pid) =>
        $"pvsld-acad-{pid}-{Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(6))}";

    public static string Write(string directory, DiscoveryInfo info)
    {
        EnsureDirectory(directory);
        var path = PathFor(directory, info.Pid);
        var temp = path + "." + Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(4)) + ".tmp";
        var bytes = Encoding.UTF8.GetBytes(info.ToJson().ToJsonString());
        using (var stream = CreatePrivateFile(temp))
        {
            stream.Write(bytes);
        }

        File.Move(temp, path, overwrite: true);
        return path;
    }

    public static void Delete(string path)
    {
        try
        {
            File.Delete(path);
        }
        catch (IOException)
        {
            // Best effort on shutdown; a stale file is detected by its dead pid.
        }
        catch (UnauthorizedAccessException)
        {
        }
    }

    private static void EnsureDirectory(string directory)
    {
        if (Directory.Exists(directory))
        {
            return;
        }

        if (OperatingSystem.IsWindows())
        {
            var parent = Path.GetDirectoryName(directory);
            if (!string.IsNullOrEmpty(parent))
            {
                Directory.CreateDirectory(parent);
            }

            CurrentUserSecurity.Directory().CreateDirectory(directory);
        }
        else
        {
            Directory.CreateDirectory(directory, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }
    }

    private static FileStream CreatePrivateFile(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            return new FileInfo(path).Create(
                FileMode.CreateNew,
                System.Security.AccessControl.FileSystemRights.Write | System.Security.AccessControl.FileSystemRights.ReadData,
                FileShare.None,
                4096,
                FileOptions.None,
                CurrentUserSecurity.File());
        }

        return new FileStream(path, new FileStreamOptions
        {
            Mode = FileMode.CreateNew,
            Access = FileAccess.Write,
            UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite,
        });
    }
}
