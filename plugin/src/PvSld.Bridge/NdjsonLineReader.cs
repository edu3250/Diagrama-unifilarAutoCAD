namespace PvSld.Bridge;

/// <summary>Raised when a peer sends a line longer than the configured limit.</summary>
public sealed class LineTooLongException(int limit)
    : IOException($"request line exceeds {limit} bytes")
{
    public int Limit { get; } = limit;
}

/// <summary>Reads newline-delimited frames from a stream without unbounded buffering.</summary>
public sealed class NdjsonLineReader
{
    private readonly Stream _stream;
    private readonly int _maxLineBytes;
    private byte[] _buffer;
    private int _start;
    private int _end;

    public NdjsonLineReader(Stream stream, int maxLineBytes = BridgeProtocol.MaxLineBytes, int initialBuffer = 64 * 1024)
    {
        _stream = stream;
        _maxLineBytes = maxLineBytes;
        _buffer = new byte[Math.Min(initialBuffer, maxLineBytes + 1)];
    }

    /// <summary>
    /// Returns the next line without its terminator (a trailing <c>\r</c> is dropped too), or
    /// <c>null</c> at end of stream. An unterminated tail at end of stream is discarded.
    /// </summary>
    public async ValueTask<byte[]?> ReadLineAsync(CancellationToken cancellationToken = default)
    {
        var scanFrom = _start;
        while (true)
        {
            var newline = Array.IndexOf(_buffer, (byte)'\n', scanFrom, _end - scanFrom);
            if (newline >= 0)
            {
                var length = newline - _start;
                if (length > 0 && _buffer[newline - 1] == (byte)'\r')
                {
                    length--;
                }

                if (length > _maxLineBytes)
                {
                    throw new LineTooLongException(_maxLineBytes);
                }

                var line = _buffer.AsSpan(_start, length).ToArray();
                _start = newline + 1;
                return line;
            }

            if (_end - _start > _maxLineBytes)
            {
                throw new LineTooLongException(_maxLineBytes);
            }

            scanFrom = MakeRoom();
            var read = await _stream.ReadAsync(_buffer.AsMemory(_end), cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                return null;
            }

            _end += read;
        }
    }

    /// <summary>Compacts or grows the buffer; returns where scanning for a newline should resume.</summary>
    private int MakeRoom()
    {
        var pending = _end - _start;
        if (_start > 0)
        {
            Buffer.BlockCopy(_buffer, _start, _buffer, 0, pending);
            _start = 0;
            _end = pending;
        }

        if (_end == _buffer.Length)
        {
            var grown = new byte[Math.Min(_buffer.Length * 2, _maxLineBytes + 2)];
            if (grown.Length <= _buffer.Length)
            {
                throw new LineTooLongException(_maxLineBytes);
            }

            Buffer.BlockCopy(_buffer, 0, grown, 0, _end);
            _buffer = grown;
        }

        return _end;
    }
}
