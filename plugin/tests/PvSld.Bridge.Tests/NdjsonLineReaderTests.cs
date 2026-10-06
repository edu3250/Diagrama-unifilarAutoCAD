using System.Text;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

public class NdjsonLineReaderTests
{
    /// <summary>A stream that returns its content in fixed-size chunks, like a pipe.</summary>
    private sealed class ChunkedStream(byte[] data, int chunk) : MemoryStream(data)
    {
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default) =>
            base.ReadAsync(buffer[..Math.Min(chunk, buffer.Length)], cancellationToken);
    }

    private static async Task<List<string>> ReadAll(string text, int chunk, int max = 1024)
    {
        var reader = new NdjsonLineReader(new ChunkedStream(Encoding.UTF8.GetBytes(text), chunk), max, initialBuffer: 4);
        var lines = new List<string>();
        while (await reader.ReadLineAsync() is { } line)
        {
            lines.Add(Encoding.UTF8.GetString(line));
        }

        return lines;
    }

    [Theory]
    [InlineData(1)]
    [InlineData(3)]
    [InlineData(4096)]
    public async Task ReadLineAsync_SplitsLinesRegardlessOfChunking(int chunk)
    {
        var lines = await ReadAll("{\"a\":1}\n{\"b\":\"ñ\"}\r\n\n{\"c\":3}\n", chunk);

        Assert.Equal(["{\"a\":1}", "{\"b\":\"ñ\"}", "", "{\"c\":3}"], lines);
    }

    [Fact]
    public async Task ReadLineAsync_DiscardsUnterminatedTailAtEof()
    {
        var lines = await ReadAll("{\"a\":1}\n{\"partial\"", 5);

        Assert.Equal(["{\"a\":1}"], lines);
    }

    [Fact]
    public async Task ReadLineAsync_LineLongerThanLimit_Throws()
    {
        var text = new string('x', 100) + "\n";

        await Assert.ThrowsAsync<LineTooLongException>(() => ReadAll(text, 7, max: 64));
    }

    [Fact]
    public async Task ReadLineAsync_LineAtLimit_IsAccepted()
    {
        var text = new string('x', 64) + "\n";

        var lines = await ReadAll(text, 7, max: 64);

        Assert.Equal(64, Assert.Single(lines).Length);
    }
}
