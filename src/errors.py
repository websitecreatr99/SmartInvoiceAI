class TransientError(Exception):
    """A failure worth retrying later (rate limit, outage), as opposed to a bad document."""
