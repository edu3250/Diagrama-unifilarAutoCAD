using System.Diagnostics;

namespace PvSld.Bridge;

/// <summary>Posts work to the host application's main (UI) thread.</summary>
public interface IMainThreadScheduler
{
    /// <summary>Queues <paramref name="action"/> to run on the main thread; must not block.</summary>
    void Post(Action action);
}

/// <summary>
/// Runs one job at a time on the main thread. If the main thread does not pick the job up within
/// <see cref="BusyTimeout"/>, the job is abandoned (it will never run later) and a
/// <see cref="BusyException"/> is thrown, so a busy or hung AutoCAD costs the caller at most that
/// long and never receives a delayed, unexpected drawing change.
/// </summary>
public sealed class MainThreadJobRunner : IDisposable
{
    private readonly IMainThreadScheduler _scheduler;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private long _abandoned;

    public MainThreadJobRunner(IMainThreadScheduler scheduler, TimeSpan busyTimeout, TimeSpan executionTimeout)
    {
        _scheduler = scheduler;
        BusyTimeout = busyTimeout;
        ExecutionTimeout = executionTimeout;
    }

    public TimeSpan BusyTimeout { get; }

    public TimeSpan ExecutionTimeout { get; }

    /// <summary>Jobs dropped because the main thread did not start them in time.</summary>
    public long AbandonedJobs => Interlocked.Read(ref _abandoned);

    public void Dispose() => _gate.Dispose();

    public async Task<T> RunAsync<T>(Func<T> work, CancellationToken cancellationToken = default)
    {
        var clock = Stopwatch.StartNew();
        if (!await _gate.WaitAsync(BusyTimeout, cancellationToken).ConfigureAwait(false))
        {
            throw new BusyException(
                BusyReasons.BridgeBusy,
                "Another bridge request is still running in AutoCAD; retry when it has finished.");
        }

        try
        {
            var job = new Job<T>(work);
            try
            {
                _scheduler.Post(job.Execute);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                throw new BusyException(
                    BusyReasons.MainThreadUnavailable,
                    $"Could not reach AutoCAD's main thread ({ex.GetType().Name}: {ex.Message}).");
            }

            var remaining = BusyTimeout - clock.Elapsed;
            if (!await CompletesWithin(job.Started, remaining, cancellationToken).ConfigureAwait(false)
                && job.TryAbandon())
            {
                Interlocked.Increment(ref _abandoned);
                throw new BusyException(
                    BusyReasons.MainThreadUnavailable,
                    $"AutoCAD did not accept the request within {BusyTimeout.TotalSeconds:0.#} s: it is busy "
                    + "(a long command, a modal window or a script). The request was cancelled and will "
                    + "not run later. Retry when AutoCAD is idle.",
                    retryAfterMs: 2000);
            }

            if (!await CompletesWithin(job.Completion, ExecutionTimeout, cancellationToken).ConfigureAwait(false))
            {
                throw new BridgeException(
                    BridgeErrorCodes.Timeout,
                    $"The request is still running in AutoCAD after {ExecutionTimeout.TotalSeconds:0} s; "
                    + "its outcome is unknown. Check the drawing before retrying.");
            }

            return await job.Completion.ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    private static async Task<bool> CompletesWithin(Task task, TimeSpan timeout, CancellationToken cancellationToken)
    {
        if (timeout < TimeSpan.Zero)
        {
            timeout = TimeSpan.Zero;
        }

        try
        {
            await task.WaitAsync(timeout, cancellationToken).ConfigureAwait(false);
            return true;
        }
        catch (TimeoutException)
        {
            return false;
        }
        catch (Exception) when (task.IsFaulted || task.IsCanceled)
        {
            return true; // completed (with an error the caller observes when awaiting the task)
        }
    }

    private sealed class Job<T>(Func<T> work)
    {
        private const int Pending = 0;
        private const int Running = 1;
        private const int Abandoned = 2;

        // Continuations must never run on AutoCAD's main thread.
        private readonly TaskCompletionSource _started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource<T> _done = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _state = Pending;

        public Task Started => _started.Task;

        public Task<T> Completion => _done.Task;

        public bool TryAbandon() => Interlocked.CompareExchange(ref _state, Abandoned, Pending) == Pending;

        /// <summary>Runs on the main thread. Never throws: an escaping exception would surface as an
        /// unhandled-exception dialog inside AutoCAD.</summary>
        public void Execute()
        {
            if (Interlocked.CompareExchange(ref _state, Running, Pending) != Pending)
            {
                return;
            }

            _started.TrySetResult();
            try
            {
                _done.TrySetResult(work());
            }
#pragma warning disable CA1031 // Every failure is reported to the client instead of AutoCAD's message loop.
            catch (Exception ex)
#pragma warning restore CA1031
            {
                _done.TrySetException(ex);
            }
        }
    }
}
