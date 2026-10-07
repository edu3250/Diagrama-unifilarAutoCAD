using System.Collections.Concurrent;
using System.Diagnostics;
using PvSld.Bridge;

namespace PvSld.Bridge.Tests;

/// <summary>Emulates AutoCAD's main thread: one dedicated thread draining a queue.</summary>
internal sealed class ThreadScheduler : IMainThreadScheduler, IDisposable
{
    private readonly BlockingCollection<Action> _queue = [];
    private readonly Thread _thread;

    public ThreadScheduler()
    {
        _thread = new Thread(() =>
        {
            foreach (var action in _queue.GetConsumingEnumerable())
            {
                action();
            }
        })
        { IsBackground = true, Name = "fake-main-thread" };
        _thread.Start();
    }

    public int ThreadId => _thread.ManagedThreadId;

    public void Post(Action action) => _queue.Add(action);

    public void Dispose()
    {
        _queue.CompleteAdding();
        _thread.Join(TimeSpan.FromSeconds(5));
        _queue.Dispose();
    }
}

/// <summary>A main thread that never runs anything until told to (a hung or modal AutoCAD).</summary>
internal sealed class StalledScheduler : IMainThreadScheduler
{
    private readonly ConcurrentQueue<Action> _posted = new();

    public void Post(Action action) => _posted.Enqueue(action);

    public void RunPending()
    {
        while (_posted.TryDequeue(out var action))
        {
            action();
        }
    }
}

public sealed class MainThreadJobRunnerTests : IDisposable
{
    private readonly ThreadScheduler _main = new();

    public void Dispose() => _main.Dispose();

    [Fact]
    public async Task RunAsync_RunsWorkOnTheMainThread()
    {
        using var runner = new MainThreadJobRunner(_main, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5));

        var threadId = await runner.RunAsync(() => Environment.CurrentManagedThreadId);

        Assert.Equal(_main.ThreadId, threadId);
    }

    [Fact]
    public async Task RunAsync_StalledMainThread_ThrowsBusyWithinTimeoutAndNeverRunsLater()
    {
        var stalled = new StalledScheduler();
        using var runner = new MainThreadJobRunner(stalled, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(5));
        var ran = false;
        var clock = Stopwatch.StartNew();

        var busy = await Assert.ThrowsAsync<BusyException>(() => runner.RunAsync(() => ran = true));

        Assert.Equal(BusyReasons.MainThreadUnavailable, busy.Reason);
        Assert.InRange(clock.Elapsed, TimeSpan.FromMilliseconds(150), TimeSpan.FromSeconds(2));
        stalled.RunPending(); // AutoCAD becomes idle again later
        Assert.False(ran);
        Assert.Equal(1, runner.AbandonedJobs);
    }

    [Fact]
    public async Task RunAsync_WorkThrows_ExceptionReachesCaller()
    {
        using var runner = new MainThreadJobRunner(_main, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5));

        await Assert.ThrowsAsync<InvalidOperationException>(
            () => runner.RunAsync<int>(() => throw new InvalidOperationException("boom")));
    }

    [Fact]
    public async Task RunAsync_SecondJobWhileFirstRuns_IsBusy()
    {
        using var runner = new MainThreadJobRunner(_main, TimeSpan.FromMilliseconds(200), TimeSpan.FromSeconds(5));
        using var release = new ManualResetEventSlim();
        var first = runner.RunAsync(() => release.Wait(TimeSpan.FromSeconds(5)));

        var busy = await Assert.ThrowsAsync<BusyException>(() => runner.RunAsync(() => 1));

        Assert.Equal(BusyReasons.BridgeBusy, busy.Reason);
        release.Set();
        Assert.True(await first);
    }

    [Fact]
    public async Task RunAsync_JobOverrunsExecutionTimeout_ReportsTimeout()
    {
        using var runner = new MainThreadJobRunner(_main, TimeSpan.FromSeconds(2), TimeSpan.FromMilliseconds(100));

        var error = await Assert.ThrowsAsync<BridgeException>(() => runner.RunAsync(() =>
        {
            Thread.Sleep(400);
            return 0;
        }));

        Assert.Equal(BridgeErrorCodes.Timeout, error.Code);
    }
}
