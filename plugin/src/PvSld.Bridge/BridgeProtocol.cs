namespace PvSld.Bridge;

/// <summary>Wire constants shared with the Python client (<c>pvsld.transports.protocol</c>).</summary>
public static class BridgeProtocol
{
    /// <summary>Protocol version announced in the discovery file and the auth reply.</summary>
    public const int Version = 1;

    /// <summary>Server name announced in the auth reply.</summary>
    public const string ServerName = "pvsld-autocad-bridge";

    /// <summary>Longest accepted request line (UTF-8 bytes, newline excluded).</summary>
    public const int MaxLineBytes = 8 * 1024 * 1024;

    public static class Methods
    {
        public const string Auth = "auth";
        public const string Ping = "ping";
        public const string InsertBlock = "insert_block";
        public const string ReadAttributes = "read_attributes";
        public const string Batch = "batch";
        public const string DrawingStats = "drawing_stats";

        /// <summary>The allowlist: the bridge executes nothing else (no LISP, no commands, no code).</summary>
        public static readonly IReadOnlyList<string> All =
            [Auth, Ping, InsertBlock, ReadAttributes, Batch, DrawingStats];
    }
}

/// <summary>JSON-RPC 2.0 error codes; -32001..-32005 are this bridge's server errors.</summary>
public static class BridgeErrorCodes
{
    public const int ParseError = -32700;
    public const int InvalidRequest = -32600;
    public const int MethodNotFound = -32601;
    public const int InvalidParams = -32602;
    public const int InternalError = -32603;

    /// <summary>No valid secret was presented; the connection is closed after this error.</summary>
    public const int Unauthorized = -32001;

    /// <summary>AutoCAD cannot take the request now (modal dialog, active command, main thread busy).</summary>
    public const int Busy = -32002;

    /// <summary>The drawing operation failed and its transaction was rolled back.</summary>
    public const int OperationFailed = -32003;

    /// <summary>The operation started but did not finish in time; its outcome is unknown.</summary>
    public const int Timeout = -32004;

    /// <summary>The requested drawing is not open (or no drawing is open at all).</summary>
    public const int DocumentNotFound = -32005;
}

/// <summary>Values of <c>error.data.reason</c> for <see cref="BridgeErrorCodes.Busy"/>.</summary>
public static class BusyReasons
{
    public const string ModalDialog = "modal_dialog";
    public const string CommandActive = "command_active";
    public const string NotQuiescent = "not_quiescent";
    public const string DocumentLocked = "document_locked";
    public const string MainThreadUnavailable = "main_thread_unavailable";
    public const string BridgeBusy = "bridge_busy";
}
